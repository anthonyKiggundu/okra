import json
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional
from config import REDIS_HOST_ORCHRA

import redis.asyncio as redis

from models import UEInfo
from clients import SliceClient, FlexRANClient, UPFClient

logger = logging.getLogger("orchestrator")
MAX_RETRIES = 3
RETRY_DELAY = 1


async def retry(coro_fn, *args, retries=MAX_RETRIES, delay=RETRY_DELAY, **kwargs):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            logger.warning("Attempt %d/%d failed: %s", attempt, retries, e)
            if attempt < retries:
                await asyncio.sleep(delay)
    raise last_exc


class RedisStore:
    #def __init__(self, redis_url: str):
    #    self.redis_url = redis_url
    #    self.redis_client = None

    def __init__(self, redis_url: str):
        # self.redis_client = redis.Redis(host=REDIS_HOST_ORCHRA, port=6379, decode_responses=True)
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None

    async def connect(self):
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        await self.redis_client.ping()

    async def close(self):
        if self.redis_client:
            await self.redis_client.close()

    async def set_context(self, key: str, val: Dict, ex=300):
        if not self.redis_client:
            raise RuntimeError("Redis client is not connected")
        await self.redis_client.set(key, json.dumps(val), ex=ex)

    async def get_context(self, key: str):
        if not self.redis_client:
            raise RuntimeError("Redis client is not connected")
        value = await self.redis_client.get(key)

        return json.loads(value) if value else None

        #val = await self.redis_client.get(key)
        #return json.loads(val) if val else None

    async def set_migration_state(self, ue_id: str, state: str, data: Dict = None):
        payload = {"state": state, "updated_at": str(asyncio.get_event_loop().time())}
        if data:
            payload["metadata"] = data
        await self.redis_client.set(f"migrate_state:{ue_id}", json.dumps(payload), ex=300)

    async def store_metric(self, ue_id: str, metric_name: str, value: float):
        await self.redis_client.set(f"metric:{ue_id}:{metric_name}", value, ex=3600)
        await self.redis_client.lpush(f"stats:history:{metric_name}", value)
        await self.redis_client.ltrim(f"stats:history:{metric_name}", 0, 9)

    async def add_migration_history(self, record: Dict[str, Any]):
        await self.redis_client.lpush("stats:history", json.dumps(record))
        await self.redis_client.ltrim("stats:history", 0, 4)


class Orchestrator:
    def __init__(
        self,
        slice_a_client: SliceClient,
        slice_b_client: SliceClient,
        redis_store: RedisStore,
        flexran: FlexRANClient,
        upf: UPFClient,
    ):
        self.slice_a = slice_a_client
        self.slice_b = slice_b_client
        self.redis = redis_store
        self.flexran = flexran
        self.upf = upf

    async def migrate_ue_seamless(self, ue: UEInfo, pdu_id: int):
        ue_id = ue.ue_id
        try:
            await self.redis.set_migration_state(ue_id, "INIT")

            # Source side context
            source_ctx = await self.slice_a.get_ue_context(ue_id)

            await self.redis.set_migration_state(ue_id, "PREPARING")

            # Create SM context on target side
            target_sm_res = await self.slice_b.nsmf_pdusession_create(ue_id, source_ctx)

            # IMPORTANT: preserve the exact SMF Location URI returned by SMF
            sm_context_uri = target_sm_res.get("sm_context_location")
            if not sm_context_uri:
                raise RuntimeError(
                    "SMF did not return sm_context_location; cannot continue safely"
                )

            await self.redis.set_context(
                f"ue:{ue_id}:target_sm_context",
                {
                    "sm_context_uri": sm_context_uri,
                    "sm_context_response": target_sm_res,
                },
            )

            # AMF/UE context from source
            context = await self.slice_a.namf_comm_get_context(ue_id)
            await self.redis.set_context(f"ue:{ue_id}:context", context)

            # If your downstream service needs the SM context URI, use it there too
            # and stop reconstructing /sm-contexts/<supi>/<id>.
            # await self.slice_b.nsmf_pdusession_import_notification(ue_id)
            await self.slice_b.nsmf_pdusession_import_notification(ue_id, sm_context_uri)

            await self.redis.set_migration_state(ue_id, "UPF_CONFIGURING")
            try:
                # If UPFClient builds any SMF-related endpoint internally, it should
                # also receive sm_context_uri and reuse it instead of recomputing one.
                await self.upf.create_shadow_tunnel(ue_id, pdu_id, target_sm_res)
            except Exception as e:
                logger.error(f"Step 3 Failed: {e}. Initiating Rollback.")
                await self.handle_rollback(ue, pdu_id, "UPF_CONFIGURING")
                return

            start_hit = time.perf_counter()

            await self.flexran.notify_slice_change(ue_id, ue.target_slice)
            await self.upf.reconfigure_tunnels(ue_id, pdu_id, context)

            # If these two methods internally reconstruct the SM context endpoint,
            # they should be changed to consume sm_context_uri instead.
            #await self.slice_b.confirm_binding(ue_id)
            #await self.slice_b.commit_session(ue_id, pdu_id)
            await self.slice_b.confirm_binding(ue_id, sm_context_uri)
            await self.slice_b.commit_session(ue_id, pdu_id, sm_context_uri)

            end_hit = time.perf_counter()
            hit_ms = (end_hit - start_hit) * 1000

            await self.redis.store_metric(ue_id, "handover_interruption_ms", hit_ms)
            await self.redis.set_migration_state(ue_id, "COMMITTED")
            await self.slice_a.namf_comm_release(ue_id)

            history_record = {
                "ue_id": ue_id,
                "status": "SUCCESS",
                "hit": hit_ms,
                "target_slice": ue.target_slice,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }
            await self.redis.add_migration_history(history_record)
            await self.redis.redis_client.set("stats:latest_hit", hit_ms)
            await self.redis.redis_client.lpush("stats:hit_trend", hit_ms)
            await self.redis.redis_client.ltrim("stats:hit_trend", 0, 9)

        except Exception as e:
            logger.critical(f"Unexpected system failure: {e}")
            await self.handle_rollback(ue, pdu_id, "UNKNOWN")

    async def handle_rollback(self, ue: UEInfo, pdu_id: int, failed_step: str):
        logger.warning(f"Initiating Rollback for {ue.ue_id} at step: {failed_step}")
        await self.redis.set_migration_state(ue.ue_id, "ROLLBACK_COMPLETE")

        history_record = {
            "ue_id": ue.ue_id,
            "status": "FAILED",
            "hit": None,
            "target_slice": ue.target_slice,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
        await self.redis.add_migration_history(history_record)

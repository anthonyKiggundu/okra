import asyncio
import logging
from datetime import datetime

from .models import UEInfo


RETRY_DELAY = 1
MAX_RETRIES = 3

logger = logging.getLogger("orchestrator")


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


class Orchestrator:
    def __init__(self, slice_a_client, slice_b_client, redis_store, flexran, upf):
        self.slice_a = slice_a_client
        self.slice_b = slice_b_client
        self.redis = redis_store
        self.flexran = flexran
        self.upf = upf

    async def monitor_and_maybe_migrate(self, ue: UEInfo) -> None:
        logger.info("Monitor: UE=%s current_slice=%s", ue.ue_id, ue.current_slice)
        if not ue.target_slice or ue.target_slice == ue.current_slice:
            logger.info("No migration needed for UE=%s", ue.ue_id)
            return
        logger.info("Decided to migrate UE=%s -> %s", ue.ue_id, ue.target_slice)
        await self.migrate_ue(ue)

    async def migrate_ue(self, ue: UEInfo) -> None:
        ue_id = ue.ue_id
        try:
            await self.redis.set_migration_state(ue_id, "INIT")

            logger.info("Step 1: Fetching UE context from source slice %s", ue.current_slice)
            context = await retry(self.slice_a.get_ue_context, ue_id)
            ue.context = context

            logger.info("Step 2: Storing context in Redis")
            await retry(self.redis.set_context, f"ue:{ue_id}:context", context, retries=2)

            logger.info("Step 3: Posting context to target slice %s", ue.target_slice)
            await retry(self.slice_b.post_ue_context, ue_id, context)

            logger.info("Step 4: Notifying FlexRAN about slice change")
            await retry(self.flexran.notify_slice_change, ue_id, ue.target_slice)

            logger.info("Step 5: Reconfiguring UPF tunnels")
            pfcp_params = {
                "new_slice": ue.target_slice,
                "ue_context": context.get("upf_info", {}),
            }
            await retry(self.upf.reconfigure_tunnels, ue_id, pfcp_params)

            logger.info("Step 6: Releasing old context on source slice")
            await self.slice_a.namf_comm_release(ue_id)

            hit_ms = 2.0
            await self.redis.store_metric(ue_id, "handover_interruption_ms", hit_ms)
            await self.redis.set_migration_state(ue_id, "COMMITTED")

            record = {
                "ue_id": ue_id,
                "status": "SUCCESS",
                "hit": hit_ms,
                "target_slice": ue.target_slice,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }
            await self.redis.add_migration_history(record)

            logger.info("Migration complete for UE=%s -> %s", ue_id, ue.target_slice)

        except Exception as e:
            logger.exception("Migration failed for UE=%s: %s", ue_id, e)
            await self.redis.set_migration_state(ue_id, "FAILED", {"error": str(e)})

            record = {
                "ue_id": ue_id,
                "status": "FAILED",
                "hit": None,
                "target_slice": ue.target_slice,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }
            await self.redis.add_migration_history(record)
            raise

import json
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
import async_timeout
import redis.asyncio as redis


HTTP_TIMEOUT = 5


class SliceClient:
    def __init__(self, base_url: str, session: aiohttp.ClientSession):
        self.base_url = base_url.rstrip("/")
        self.session = session

    async def get_ue_context(self, ue_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/ue-context/{ue_id}"
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def post_ue_context(self, ue_id: str, context: Dict[str, Any]) -> None:
        url = f"{self.base_url}/ue-context/{ue_id}"
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.post(url, json=context) as resp:
                resp.raise_for_status()

    async def namf_comm_get_context(self, ue_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/namf-comm/v1/ue-contexts/{ue_id}"
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def namf_comm_release(self, ue_id: str) -> bool:
        url = f"{self.base_url}/namf-comm/v1/ue-contexts/{ue_id}/release"
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.post(
                url, json={"cause": "SLICE_MIGRATION_COMPLETE"}
            ) as resp:
                return resp.status == 204


class FlexRANClient:
    def __init__(self, base_url: str, session: aiohttp.ClientSession):
        self.base_url = base_url.rstrip("/")
        self.session = session

    async def notify_slice_change(self, ue_id: str, new_slice: str) -> None:
        url = f"{self.base_url}/slice-change"
        payload = {"ue_id": ue_id, "new_slice": new_slice}
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.post(url, json=payload) as resp:
                resp.raise_for_status()


class UPFClient:
    def __init__(self, base_url: str, session: aiohttp.ClientSession):
        self.base_url = base_url.rstrip("/")
        self.session = session

    async def reconfigure_tunnels(self, ue_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/pfcp/reconfigure"
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.post(url, json={"ue_id": ue_id, **params}) as resp:
                resp.raise_for_status()
                return await resp.json()


class RedisStore:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client = None

    async def connect(self):
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)

    async def close(self):
        if self.redis_client:
            await self.redis_client.close()

    async def set_context(self, key: str, value: Dict[str, Any], ex: int = 300):
        await self.redis_client.set(key, json.dumps(value), ex=ex)

    async def get_context(self, key: str) -> Optional[Dict[str, Any]]:
        val = await self.redis_client.get(key)
        return json.loads(val) if val else None

    async def set_migration_state(self, ue_id: str, state: str, data: Optional[Dict] = None):
        payload = {
            "state": state,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        if data:
            payload["metadata"] = data
        await self.redis_client.set(f"migrate_state:{ue_id}", json.dumps(payload), ex=300)

    async def get_migration_state(self, ue_id: str):
        val = await self.redis_client.get(f"migrate_state:{ue_id}")
        return json.loads(val) if val else None

    async def store_metric(self, ue_id: str, metric_name: str, value: float):
        await self.redis_client.set(f"metric:{ue_id}:{metric_name}", value, ex=3600)
        await self.redis_client.set("stats:latest_hit", value, ex=3600)
        await self.redis_client.lpush("stats:hit_trend", value)
        await self.redis_client.ltrim("stats:hit_trend", 0, 9)

    async def add_migration_history(self, record: Dict[str, Any]):
        await self.redis_client.lpush("stats:history", json.dumps(record))
        await self.redis_client.ltrim("stats:history", 0, 4)

    async def get_migration_history(self):
        history = await self.redis_client.lrange("stats:history", 0, 4)
        return [json.loads(item) for item in history]

    async def get_dashboard_stats(self):
        history = await self.get_migration_history()
        latest_hit = await self.redis_client.get("stats:latest_hit")
        trend_raw = await self.redis_client.lrange("stats:hit_trend", 0, 9)
        trend = [float(v) for v in trend_raw][::-1]
        return {
            "history": history,
            "latest_hit_ms": float(latest_hit) if latest_hit else 0.0,
            "trend": trend,
        }

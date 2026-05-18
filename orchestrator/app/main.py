import os
import json
import logging
import asyncio
from datetime import datetime
import uvicorn
import aiohttp
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from models import MigrateRequest, UEInfo
from clients import SliceClient, FlexRANClient, UPFClient
from services import RedisStore, Orchestrator
from dashboard import HTML_DASHBOARD_TEMPLATE

REDIS_URL = os.getenv("REDIS_URL", "redis://redis-master.5g-core.svc.cluster.local:6379")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator")

app = FastAPI(title="Inter-slice Orchestrator")

# Global instances managed via lifecycle hooks
redis_store: RedisStore = None
orchestrator: Orchestrator = None
http_session: aiohttp.ClientSession = None

@app.on_event("startup")
async def app_startup():
    global redis_store, orchestrator, http_session
    redis_store = RedisStore(REDIS_URL)
    await redis_store.connect()
    
    http_session = aiohttp.ClientSession()
    slice_a = SliceClient("http://localhost:8001", http_session)
    slice_b = SliceClient("http://localhost:8002", http_session)
    flexran = FlexRANClient("http://localhost:9000", http_session)
    upf = UPFClient("http://localhost:7000", http_session)
    
    orchestrator = Orchestrator(slice_a, slice_b, redis_store, flexran, upf)
    logger.info(f"Connected to Redis at {REDIS_URL} and initialized runtime environment components.")

@app.on_event("shutdown")
async def app_shutdown():
    await redis_store.close()
    await http_session.close()
    logger.info("Cleaned up application connections.")

@app.get("/stats")
async def get_stats():
    history_raw = await redis_store.redis_client.lrange("stats:history", 0, 4)
    history = [json.loads(h) for h in history_raw]
    
    latest_hit = await redis_store.redis_client.get("stats:latest_hit")
    hit = float(latest_hit) if latest_hit else 0.0
    
    trend_raw = await redis_store.redis_client.lrange("stats:hit_trend", 0, 9)
    trend = [float(val) for val in trend_raw][::-1]

    return {
        "latest_hit_ms": round(hit, 2),
        "history": history,
        "trend": trend,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }

@app.get("/health")
async def health():
    try:
        await redis_store.redis_client.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "service": "orchestrator",
        "redis": redis_status,
        "redis_url": REDIS_URL
    }

@app.get("/example")
async def example():
    await redis_store.set_context("test_key", {"foo": "bar", "timestamp": str(asyncio.get_event_loop().time())}, ex=300)
    return await redis_store.get_context("test_key")

@app.post("/trigger-migration")
async def trigger(req: MigrateRequest):
    ue_context = UEInfo(ue_id=req.ue_id, current_slice=req.current_slice, target_slice=req.target_slice)
    asyncio.create_task(orchestrator.migrate_ue_seamless(ue_context, pdu_id=1))
    return {"status": "migration_triggered", "ue_id": req.ue_id}

@app.get("/context/{ue_id}")
async def get_context(ue_id: str):
    context = await redis_store.get_context(f"ue:{ue_id}:context")
    if not context:
        raise HTTPException(status_code=404, detail=f"No context found for UE {ue_id}")
    return context

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return HTML_DASHBOARD_TEMPLATE

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

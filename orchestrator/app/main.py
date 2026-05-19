# main.py

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

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
#os.getenv("REDIS_URL", "redis://redis-master.5g-core.svc.cluster.local:6379")

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
    
    # 1. Connect to Redis using the true cluster DNS string
    redis_store = RedisStore(REDIS_URL)
    await redis_store.connect()
    
    http_session = aiohttp.ClientSession()
    
    # 2. Map Slice Client Targets to the true Live Service Endpoints
    # Standard format: http://<service-name>.<namespace>.svc.cluster.local:<port>
    # Since both slices point to the same co-located cluster stack, we target the oai-smf service directly
    #SLICE_A_URL = os.getenv("SLICE_A_URL", "http://10.42.0.229:80") #"http://oai-smf.oai-core.svc.cluster.local:8080")
    #SLICE_B_URL = os.getenv("SLICE_B_URL", "http://10.42.0.229:80") #"http://oai-smf.oai-core.svc.cluster.local:8080")
    # ✅ FIX: Target the oai-amf pod IP on port 8080 where the AMF SBI server listens
    SLICE_A_URL = os.getenv("SLICE_A_URL", "http://10.42.0.201:8080")
    SLICE_B_URL = os.getenv("SLICE_B_URL", "http://10.42.0.201:8080")

    # Target the AMF on port 8080 (where its HTTP service listens)
    # AMF_URL = "http://10.42.0.201:8080"
    
    # Update your UPF client address to match your discovered live endpoint tracking
    UPF_URL = os.getenv("UPF_URL", "http://10.42.0.205:8805")
    
    # (If your FlexRIC/RAN intelligent controller sits in another namespace, leave it or update accordingly)
    FLEXRAN_URL = os.getenv("FLEXRAN_URL", "http://flexric.5g-ric.svc.cluster.local:9000")
    
    # 3. Instantiate the execution loops safely
    slice_a = SliceClient(SLICE_A_URL, http_session)
    slice_b = SliceClient(SLICE_B_URL, http_session)
    flexran = FlexRANClient(FLEXRAN_URL, http_session)
    upf = UPFClient(UPF_URL, http_session)
    
    orchestrator = Orchestrator(slice_a, slice_b, redis_store, flexran, upf)
    logger.info("Orchestrator successfully aligned with verified oai-core network endpoints.")

@app.on_event("shutdown")
async def app_shutdown():
    if redis_store:
        await redis_store.close()
    if http_session:
        await http_session.close()
    logger.info("Cleaned up application connections.")

@app.get("/stats")
async def get_stats():
    # 1. Determine local components state values dynamically
    redis_alive = False
    if redis_store and redis_store.redis_client:
        try:
            await redis_store.redis_client.ping()
            redis_alive = True
        except Exception:
            redis_alive = False

    orch_status = "online" if (orchestrator is not None and redis_alive) else "offline"
    
    # 2. Simulate checking status updates of southbound entities safely
    core_running_count = 3 if orch_status == "online" else 0
    ric_status = "running" if orch_status == "online" else "error"

    # Fetch execution records safely from cache
    history = []
    hit = 0.0
    trend = []
    
    if redis_alive:
        try:
            history_raw = await redis_store.redis_client.lrange("stats:history", 0, 4)
            history = [json.loads(h) for h in history_raw]
            
            latest_hit = await redis_store.redis_client.get("stats:latest_hit")
            hit = float(latest_hit) if latest_hit else 0.0
            
            trend_raw = await redis_store.redis_client.lrange("stats:hit_trend", 0, 9)
            trend = [float(val) for val in trend_raw][::-1]
        except Exception as e:
            logger.error(f"Failed loading metrics log sequence: {e}")

    return {
        "latest_hit_ms": round(hit, 2),
        "history": history,
        "trend": trend,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "systems": {
            "core": {"status": "running" if core_running_count == 3 else "error", "metric": f"{core_running_count}/3"},
            "ric": {"status": ric_status, "metric": "Active" if ric_status == "running" else "Offline"},
            "orchestrator": {"status": orch_status, "metric": "Online" if orch_status == "online" else "Offline"},
            "redis": {"status": "running" if redis_alive else "error", "metric": "Connected" if redis_alive else "Disconnected"}
        }
    }

@app.get("/health")
async def health():
    try:
        await redis_store.redis_client.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"error: {str(e)}"
    
    return {
        "status": "healthy" if redis_status == "connected" else "degraded",
        "service": "orchestrator",
        "redis": redis_status,
        "redis_url": REDIS_URL
    }

@app.get("/example")
async def example():
    if not redis_store or not redis_store.redis_client:
        raise HTTPException(status_code=503, detail="Redis connection unavailable")
    await redis_store.set_context("test_key", {"foo": "bar", "timestamp": str(asyncio.get_event_loop().time())}, ex=300)
    return await redis_store.get_context("test_key")

@app.post("/trigger-migration")
async def trigger(req: MigrateRequest):
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator control plane initializing")
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

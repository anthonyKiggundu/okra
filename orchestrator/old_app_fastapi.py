#!/usr/bin/env python3
"""
Inter-Slice Orchestrator API
----------------------------
FastAPI-based microservice implementing:
  - GET /ue-context/{imsi}
  - POST /ue-context/{imsi}
  - POST /bind
Includes TLS, Redis-backed mock DB, and PFCP adapter placeholder.

# Store a UE context
curl -k -X POST https://localhost:8443/ue-context/001010123456789 \
  -H "Content-Type: application/json" \
  -d '{
    "imsi": "001010123456789",
    "nas_context": {"sec_alg": "128-EEA2"},
    "pdu_sessions": {"id": 10, "apn": "internet"},
    "qos_flows": {"qfi": 9, "priority": "high"}
  }'

# Retrieve it
curl -k https://localhost:8443/ue-context/001010123456789

# Trigger binding
curl -k -X POST https://localhost:8443/bind \
  -H "Content-Type: application/json" \
  -d '{"imsi":"001010123456789","target_slice":"sliceB","upf_target":"upf-b"}'

"""

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import redis
import ssl
import uvicorn
import json
import os
from typing import Dict, Any

# --------------------------------------------------------
# Configuration
# --------------------------------------------------------

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
TLS_CERT = os.getenv("TLS_CERT", "/certs/server.crt")
TLS_KEY = os.getenv("TLS_KEY", "/certs/server.key")
PFCP_ADAPTER_URL = os.getenv("PFCP_ADAPTER_URL", "http://pfcp-adapter:8081")

# Initialize FastAPI app
app = FastAPI(title="5G Inter-Slice Orchestrator", version="1.0")

# Connect to Redis (mock DB)
try:
    rdb = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    rdb.ping()
    print(f"[+] Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except redis.ConnectionError:
    print("[!] Warning: Could not connect to Redis. Running in mock mode.")
    rdb = None

# --------------------------------------------------------
# Models
# --------------------------------------------------------

class UEContext(BaseModel):
    imsi: str
    nas_context: Dict[str, Any]
    pdu_sessions: Dict[str, Any]
    qos_flows: Dict[str, Any]

class BindRequest(BaseModel):
    imsi: str
    target_slice: str
    upf_target: str

# --------------------------------------------------------
# Utility Functions
# --------------------------------------------------------

def redis_set_json(key: str, value: dict):
    if rdb:
        rdb.set(key, json.dumps(value))
    else:
        print(f"[MOCK REDIS] SET {key} -> {value}")

def redis_get_json(key: str) -> dict:
    if rdb:
        data = rdb.get(key)
        return json.loads(data) if data else None
    print(f"[MOCK REDIS] GET {key}")
    return {"mock": "data"}

# --------------------------------------------------------
# API Endpoints
# --------------------------------------------------------

@app.get("/ue-context/{imsi}", response_model=UEContext)
async def get_ue_context(imsi: str):
    """
    Retrieve UE context (mocked or from Redis).
    """
    data = redis_get_json(f"ue:{imsi}")
    if not data:
        raise HTTPException(status_code=404, detail=f"UE {imsi} not found.")
    return UEContext(imsi=imsi, **data)

@app.post("/ue-context/{imsi}", status_code=status.HTTP_201_CREATED)
async def post_ue_context(imsi: str, context: UEContext):
    """
    Store/Import UE context into target slice.
    """
    redis_set_json(f"ue:{imsi}", context.dict())
    return {"message": f"UE {imsi} context stored successfully."}

@app.post("/bind", status_code=status.HTTP_200_OK)
async def bind_ue_to_slice(request: BindRequest):
    """
    Instruct target SMF/UPF to bind UE to target slice and reconfigure PFCP tunnel.
    """
    ue_data = redis_get_json(f"ue:{request.imsi}")
    if not ue_data:
        raise HTTPException(status_code=404, detail=f"UE {request.imsi} not found.")

    # Mock PFCP adapter interaction
    print(f"[+] Binding UE {request.imsi} -> Slice {request.target_slice}, UPF {request.upf_target}")
    # TODO: call PFCP adapter microservice for real reconfiguration

    return {"status": "success", "details": f"UE {request.imsi} bound to slice {request.target_slice}"}

@app.get("/")
async def root():
    return {"status": "running", "service": "Inter-Slice Orchestrator API"}

# --------------------------------------------------------
# 🛡️ TLS Launch
# --------------------------------------------------------

if __name__ == "__main__":
    # Ensure TLS certs exist
    if not os.path.exists(TLS_CERT) or not os.path.exists(TLS_KEY):
        print(f"[!] TLS certificates missing. Generate them with ./scripts/generate-certs.sh")
        exit(1)

    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile=TLS_CERT, keyfile=TLS_KEY)

    uvicorn.run(
        "app_fastapi:app",
        host="0.0.0.0",
        port=6443, #8443,
        ssl_certfile=TLS_CERT,
        ssl_keyfile=TLS_KEY,
    )


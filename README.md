# okra

````markdown name=README.md
# Okra Orchestrator API

This service is the REST API entry point for session migration and inter-slice orchestration in the Okra project.

The API is implemented in `orchestrator/app/main.py` and is built with FastAPI. It connects to Redis on startup, exposes health and dashboard endpoints, and provides endpoints for testing and triggering migration workflows.

## What this service does

The orchestrator is responsible for:

- exposing a REST API for session migration workflows
- storing and retrieving UE context in Redis
- coordinating interactions with slice components
- providing a simple dashboard and health endpoints
- tracking migration and handover-interruption metrics

## Entry point

The main entry point is:

```bash
orchestrator/app/main.py
```

The application starts a FastAPI app and runs Uvicorn on port `8000`.

## Main endpoints

### Health and utility

- `GET /health`  
  Check whether the orchestrator is up and whether Redis is reachable.

- `GET /example`  
  Simple Redis connectivity test.

- `GET /context/{ue_id}`  
  Fetch stored UE context from Redis.

### UI

- `GET /`
- `GET /dashboard`  
  Open the built-in HTML dashboard.

- `GET /docs`  
  FastAPI Swagger UI documentation.

### Migration-related

- `POST /trigger-migration`  
  Trigger a simulated migration event for dashboard testing.

- `POST /migrate`  
  Trigger migration logic through the API.

## Prerequisites

Before starting, make sure you have:

- Python 3.10+ recommended
- `pip`
- a running Redis instance
- network connectivity to any slice/core services you want the orchestrator to call

## Redis configuration

By default, the app uses:

```bash
redis://redis-master.5g-core.svc.cluster.local:6379
```

You can override this with the `REDIS_URL` environment variable.

Example:

```bash
export REDIS_URL=redis://localhost:6379
```

For local development, using local Redis is usually easiest.

## Getting started

### 1. Clone the repo

```bash
git clone https://github.com/anthonyKiggundu/okra.git
cd okra
```

### 2. Go to the app directory

```bash
cd orchestrator/app
```

### 3. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install dependencies

If you have a requirements file, install from it:

```bash
pip install -r requirements.txt
```

If not, install the packages used by `main.py` directly:

```bash
pip install fastapi uvicorn aiohttp redis async-timeout pydantic
```

## Run Redis locally

If you already have Redis, skip this step.

Using Docker:

```bash
docker run --name okra-redis -p 6379:6379 redis:7
```

Then point the app to local Redis:

```bash
export REDIS_URL=redis://localhost:6379
```

## Start the API

From `orchestrator/app`:

```bash
python main.py
```

Alternatively, run with uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Verify the service

Once started, open:

- API root/dashboard: `http://localhost:8000/`
- Swagger docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

Example:

```bash
curl http://localhost:8000/health
```

Expected response shape:

```json
{
  "status": "healthy",
  "service": "orchestrator",
  "redis": "connected",
  "redis_url": "redis://localhost:6379"
}
```

## Test Redis connectivity

```bash
curl http://localhost:8000/example
```

This writes a test key to Redis and reads it back.

## Trigger a sample migration

Example request:

```bash
curl -X POST http://localhost:8000/trigger-migration \
  -H "Content-Type: application/json" \
  -d '{
    "ue_id": "UE-101",
    "current_slice": "EMBB",
    "target_slice": "URLLC"
  }'
```

## Notes for real integration

The file shows placeholder/default endpoints for external systems such as:

- source slice API
- target slice API
- FlexRAN
- UPF

If you want real migration flows to work end-to-end, you will need to:

- make sure those services are reachable
- configure the correct base URLs
- ensure Redis is shared with the components that exchange UE context

## Known caveats

`main.py` currently appears to mix dashboard code, migration logic, and some duplicate/incomplete sections. Before production use, it would be a good idea to:

- split the file into smaller modules
- define a clear `requirements.txt`
- remove duplicate code blocks
- validate all endpoints
- standardize Redis client usage and naming
- confirm the final `/migrate` request schema

## Suggested development workflow

```bash
cd okra/orchestrator/app
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn aiohttp redis async-timeout pydantic
export REDIS_URL=redis://localhost:6379
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Then visit:

```bash
http://localhost:8000/docs
```

## Project structure

```text
orchestrator/app/
  main.py
  dashboard.py
  broken_main.py
  ZeroRTT_Latency_Collector_Script.py
  analyse_zero_rtt_performance.py
  plot_ZeroRTT_effect.py
  zero_rtt_xapp.py
```

## Next steps

A good next improvement would be to add:

- a `requirements.txt`
- a Dockerfile for the orchestrator
- environment variable documentation for all dependent services
- example migration payloads for the real `/migrate` endpoint
````

One important caveat: `main.py` appears to contain duplicated sections and some inconsistent symbols/usages, so I’d treat this README as a **getting-started/developer README**, not as proof that every endpoint is production-ready. For example, the file includes duplicate blocks and some references that look inconsistent, which suggests the app may need cleanup before all documented flows work exactly as written. ```python name=main.py url=https://github.com/anthonyKiggundu/okra/blob/53f983d18c6870b096ab9b3e3cb729851b9e6aa5/orchestrator/app/main.py#L1005-L1006
if __name__ == "__main__":
    asyncio.run(main())import os
``` 

If you want, I can also turn this into:
1. a **short polished README for end users**, or
2. a **developer-focused README plus requirements.txt draft**.

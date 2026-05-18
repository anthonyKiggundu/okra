# Okra Orchestrator API

`orchestrator/app/main.py` is the entry point for the Okra REST API used for session migration and inter-slice orchestration.

It is a FastAPI service that:

- starts an HTTP API on port `8000`
- connects to Redis on startup
- exposes health and test endpoints
- provides a simple dashboard
- supports migration-related API flows

## Key endpoints

- `GET /health` — service and Redis health check
- `GET /example` — basic Redis read/write test
- `GET /dashboard` or `GET /` — HTML dashboard
- `GET /docs` — Swagger/OpenAPI docs
- `GET /context/{ue_id}` — fetch UE context from Redis
- `POST /trigger-migration` — trigger a simulated migration
- `POST /migrate` — trigger migration flow

## Prerequisites

- Python 3.10+
- Redis
- `pip`

## Local setup

Clone the repo and move into the app directory:

```bash
git clone https://github.com/anthonyKiggundu/okra.git
cd okra/orchestrator/app
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install fastapi uvicorn aiohttp redis async-timeout pydantic
```

## Redis configuration

By default, the app uses:

```bash
redis://redis-master.5g-core.svc.cluster.local:6379
```

For local development, override it:

```bash
export REDIS_URL=redis://localhost:6379
```

If you need a local Redis instance quickly:

```bash
docker run --name okra-redis -p 6379:6379 redis:7
```

## Run the API

You can start it either way:

```bash
python main.py
```

or:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Verify it works

Health check:

```bash
curl http://localhost:8000/health
```

Open in browser:

- `http://localhost:8000/docs`
- `http://localhost:8000/dashboard`

Redis test:

```bash
curl http://localhost:8000/example
```

## Example migration trigger

```bash
curl -X POST http://localhost:8000/trigger-migration \
  -H "Content-Type: application/json" \
  -d '{
    "ue_id": "UE-101",
    "current_slice": "EMBB",
    "target_slice": "URLLC"
  }'
```

## Developer notes

- Redis is required for context storage and dashboard stats.
- `main.py` currently mixes API routes, dashboard HTML, orchestration logic, and client helpers in one file.
- External integrations such as SMF/AMF, FlexRAN, and UPF use placeholder/default URLs in code and may need environment-based configuration before real deployment.

# Orchra

Based on the paper: _Orchra: Stateful-aware Cross-slice Workload Migrations in the 6G Control Plane_

Orchra is a 5G orchestration and experimentation repository that combines:

- **Customized OAI core components** under `component/`
- A **Python FastAPI orchestrator** under `orchestrator/`
- **Kubernetes and Helm-based deployment assets** under `k8s/`
- **Helper automation scripts** under `scripts/` and the repo root

The repository is no longer just a standalone REST API service. It now packages the orchestration layer together with OAI AMF/SMF changes, cluster deployment resources, and operational scripts used to stand up and test the environment.

## Repository structure

- `component/oai-amf/` — OAI AMF source modifications
- `component/oai-smf/` — OAI SMF source modifications
- `orchestrator/` — containerized FastAPI orchestration service
- `k8s/` — Helmfile, charts, manifests, and values for deployment
- `scripts/` — utility scripts for syncing components, cleanup, cert generation, and test calls
- `provision-and-deploy.sh` — end-to-end bootstrap script for local k3s + Helm/Helmfile deployment

## What the orchestrator does

The orchestrator entry point is:

- `orchestrator/app/main.py`

It starts a FastAPI service that:

- exposes orchestration and health endpoints
- serves a dashboard UI
- checks Kubernetes cluster and service health
- interacts with Redis for context and state handling
- coordinates migration-related flows across **baseline** and **Orchra** environments
- integrates with external control-plane helpers such as FlexRIC, UPF, and slice-control endpoints

Supporting modules include:

- `orchestrator/app/clients.py` — external client wrappers
- `orchestrator/app/services.py` — orchestration and Redis-backed service logic
- `orchestrator/app/models.py` — request/response models
- `orchestrator/app/config.py` — environment-specific service and namespace settings
- `orchestrator/app/dashboard.py` — embedded HTML dashboard template

## Naming note: Okra vs Orchra

The repository name is **Okra**, but parts of the implementation still use **Orchra** internally.

Examples include:

- route names such as `POST /trigger-orchra-migration`
- config variables such as `K8S_NAMESPACE_ORCHRA` and `REDIS_HOST_ORCHRA`
- dashboard labels such as `Orchra Production Diagnostics`
- OAI component files and symbols such as `orchra_context.*` and `orchra_redis.*`

For now, this README uses:

- **Okra** for the repository/project name
- **Orchra** when referring to names that currently exist in code

## Current API surface

Based on the current application code, the main routes now include:

- `GET /health` — health check for baseline, Orchra, or both clusters
- `GET /stats` — orchestrator runtime statistics
- `GET /k8s-check` — Kubernetes connectivity/status check
- `GET /context/{ue_id}` — fetch UE context
- `GET /dashboard` and `GET /` — dashboard UI
- `POST /trigger-mosaic-migration` — trigger Mosaic migration flow
- `POST /trigger-orchra-migration` — trigger Orchra migration flow

OpenAPI docs remain available at:

- `GET /docs`

## Orchestrator runtime and ports

The repository currently reflects two common ways the service is run:

- **Local development** from `orchestrator/app/main.py`, typically with Uvicorn on port `8000`
- **Container deployment** via `orchestrator/Dockerfile`, exposing port `8080`

The Docker image:

- uses `python:3.11-slim`
- installs dependencies from `orchestrator/requirements.txt`
- copies `orchestrator/app/` into the container
- exposes port `8080`
- launches `uvicorn app.main:app --host 0.0.0.0 --port 8080`

## Python dependencies

Current Python requirements are defined in `orchestrator/requirements.txt`:

- `fastapi==0.103.2`
- `uvicorn==0.23.2`
- `httpx==0.25.0`
- `redis>=5.0.0`
- `pydantic>=2.4.0,<3.0.0`
- `aiohttp==3.9.0`

You will also need Kubernetes access for the cluster-aware endpoints because the service initializes Kubernetes clients and inspects in-cluster resources.

## Configuration

Configuration is currently driven mostly from `orchestrator/app/config.py` and environment variables.

Important settings include:

- `K8S_NAMESPACE_BASE` — defaults to `oai-core-vanilla`
- `K8S_NAMESPACE_ORCHRA` — defaults to `base-chart`
- `K8S_NAMESPACE_RIC` — set to `5g-ric`
- `REDIS_HOST_ORCHRA` — derived from the Orchra namespace
- `MOSAIC_CONTROLLER_URL` — currently set to a direct HTTP endpoint in code
- `REDIS_URL` — currently set in code to `redis://127.0.0.1:6380/0`

> [!IMPORTANT]
> Some runtime values are still hard-coded for experimentation, including controller and Redis connection details. Review `orchestrator/app/config.py` before deploying to a different environment.

## Namespace note

The repo currently contains **mixed namespace assumptions** between the Python service, Helmfile deployment, and some chart values.

Examples:

- `orchestrator/app/config.py` defaults to:
  - baseline namespace: `oai-core-vanilla`
  - Orchra namespace: `base-chart`
  - RIC namespace: `5g-ric`
- `k8s/helmfile.yaml` deploys releases into:
  - `5g-core`
  - `5g-ric`
  - `5g-orchestrator`
- `scripts/cleanup.sh` deletes:
  - `5g-core`
  - `5g-ran`
  - `5g-ric`
  - `5g-orchestrator`

This means the runtime defaults in Python do **not** currently line up perfectly with the namespaces used by Helmfile.

## Redis connectivity note

Redis settings are also not fully aligned across the repo yet.

Current examples in the codebase include:

- `orchestrator/app/config.py` uses `redis://127.0.0.1:6380/0` for local testing via port-forward
- `component/oai-amf/amf_n1.cpp` initializes Redis with `tcp://redis-master.base-chart.svc.cluster.local:6379`
- `k8s/helmfile.yaml` deploys Redis in namespace `5g-core`
- `k8s/values/orchestrator-values.yaml` references `redis-master.5g.svc.cluster.local:6379`

Before using this in a shared or production-like cluster, standardize Redis hostnames, namespace references, and URL formatting.

## Local development

Clone the repository:

```bash
git clone https://github.com/anthonyKiggundu/okra.git
cd okra
```

Create a virtual environment and install orchestrator dependencies:

```bash
cd orchestrator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the API locally:

```bash
cd app
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

If you are testing with the current Redis configuration, note that the code presently expects:

```bash
redis://127.0.0.1:6380/0
```

The comments in `config.py` indicate this is intended to work with a Kubernetes port-forward, for example:

```bash
kubectl port-forward -n base-chart svc/redis-master 6380:6379
```

## Container build

Build the orchestrator image from the repository root:

```bash
docker build -t okra-orchestrator ./orchestrator
```

Run it locally:

```bash
docker run --rm -p 8080:8080 okra-orchestrator
```

## Kubernetes deployment

The repo now includes a Kubernetes deployment stack in `k8s/`.

Notable files:

- `k8s/helmfile.yaml` — orchestrates release deployment
- `k8s/charts/oai-core/` — OAI core chart
- `k8s/charts/flexric/` — FlexRIC chart
- `k8s/charts/orchestrator/` — orchestrator chart
- `k8s/charts/pfcp-adapter/` — PFCP adapter chart
- `k8s/charts/redis/` — Redis chart assets
- `k8s/manifests/` — additional raw manifests
- `k8s/values/` — deployment values files

The Helmfile currently defines releases for:

- `redis` in namespace `5g-core`
- `oai-core` in namespace `5g-core`
- `flexric` in namespace `5g-ric`
- `orchestrator` in namespace `5g-orchestrator`

## Provisioning flow

The root script `provision-and-deploy.sh` automates a full bootstrap flow that:

1. installs k3s if needed
2. prepares kubeconfig for the current user
3. installs Helm if missing
4. installs Helmfile if missing
5. installs the `helm-diff` plugin if missing
6. adds Helm repositories
7. applies manifests from `k8s/manifests/`
8. deploys the stack with `helmfile -f k8s/helmfile.yaml apply`

Run it with:

```bash
bash provision-and-deploy.sh
```

## OAI component changes

The `component/` tree contains customized OAI code, including AMF and SMF changes related to Orchra context handling and Redis-backed state exchange.

Examples visible in the repository include:

- Redis integration hooks in AMF and SMF code
- Orchra-specific context transfer helpers
- SMF build updates to include Orchra source files
- API/model additions related to context transfer
- internal AMF/SMF changes marked as `OKRA` or `ORCHRA` in comments and symbols

This means Okra should be treated as a combined platform repo, not just a Python control service.

## Utility scripts

The `scripts/` directory currently contains:

- `cleanup.sh`
- `generate-certs.sh`
- `syncComponents.sh`
- `test-ue-switch.sh`

These support environment cleanup, certificate generation, component synchronization, and basic test invocation.

## Quick verification

Examples:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/stats
curl http://localhost:8000/k8s-check
```

If running the containerized service:

```bash
curl http://localhost:8080/health
```

## Notes

- The previous README described the repo primarily as an "Okra Orchestrator API". That is now incomplete because the repository also includes OAI component modifications and cluster deployment assets.
- Naming is still evolving across the codebase; expect both **Okra** and **Orchra** references until the repo is normalized.
- Namespace, Redis, and service-host settings are not yet fully standardized across Python code, Helm values, and helper scripts.
- Before production use, review hard-coded endpoints, namespace defaults, Redis connectivity assumptions, and deployment values.

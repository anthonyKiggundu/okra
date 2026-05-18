import os
import uuid
import asyncio
import logging
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional

import aiohttp
import redis.asyncio as redis
import async_timeout
from dataclasses import dataclass

import uvicorn  # Add this for running the app directly

# -------------------------
# Configuration & constants
# -------------------------
# Redis is deployed in 5g-core namespace, NOT default!
REDIS_URL = os.getenv("REDIS_URL", "redis://redis-master.5g-core.svc.cluster.local:6379")
HTTP_TIMEOUT = 5  # seconds
RETRY_DELAY = 1  # seconds
MAX_RETRIES = 3

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator")

# FastAPI App
app = FastAPI(title="Inter-slice Orchestrator")

@app.on_event("startup")
async def app_startup():
    global redis_store
    redis_store = RedisStore(REDIS_URL)
    await redis_store.connect()
    logger.info(f"Connected to Redis at {REDIS_URL}")


@app.on_event("shutdown")
async def app_shutdown():
    await redis_store.close()
    logger.info("Closed Redis connection")


@app.get("/stats")
async def get_stats():
    """Fetches real-time metrics, history, and trend data"""
    # Migration History
    history_raw = await redis_client.lrange("stats:history", 0, 4)
    history = [json.loads(h) for h in history_raw]
    
    # Latest Metric
    latest_hit = await redis_client.get("stats:latest_hit")
    
    # Trend Data (Last 10 HIT values for the chart)
    # We store these in a separate list 'stats:hit_trend'
    trend_raw = await redis_client.lrange("stats:hit_trend", 0, 9)
    trend = [float(val) for val in trend_raw][::-1] # Reverse to show chronological order

    return {
        "latest_hit_ms": round(hit, 2),
        "history": history,
        "timestamp": asyncio.get_event_loop().time()
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    try:
        # Test Redis connection
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
    """Test Redis connection"""
    await redis_store.set_context("test_key", {"foo": "bar", "timestamp": str(asyncio.get_event_loop().time())}, ex=300)
    return await redis_store.get_context("test_key")


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Dashboard UI"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>5G Network Slicing Dashboard</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container { 
                max-width: 1400px; 
                margin: 0 auto; 
            }
            .header { 
                text-align: center; 
                padding: 30px; 
                background: rgba(255, 255, 255, 0.95); 
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                margin-bottom: 30px;
            }
            .header h1 { 
                font-size: 36px; 
                color: #667eea; 
                margin-bottom: 10px;
            }
            .header p { 
                color: #666; 
                font-size: 16px;
            }
            .grid { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); 
                gap: 20px; 
                margin-bottom: 30px;
            }
            .card { 
                background: rgba(255, 255, 255, 0.95); 
                padding: 25px; 
                border-radius: 12px; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                border-left: 5px solid #667eea;
                transition: transform 0.3s ease, box-shadow 0.3s ease;
            }
            .card:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 40px rgba(0,0,0,0.3);
            }
            .card.core { border-left-color: #2196F3; }
            .card.ran { border-left-color: #FF9800; }
            .card.ric { border-left-color: #9C27B0; }
            .card.orchestrator { border-left-color: #4CAF50; }
            .card.redis { border-left-color: #DC382D; }
            .status { 
                display: inline-block; 
                padding: 6px 14px; 
                border-radius: 20px; 
                font-size: 12px; 
                font-weight: bold;
                margin-top: 10px; 
                text-transform: uppercase;
            }
            .status.running { background: #4CAF50; color: white; }
            .status.pending { background: #FF9800; color: white; }
            .status.error { background: #f44336; color: white; }
            h2 { 
                margin: 10px 0; 
                font-size: 22px; 
                color: #333;
            }
            .card p { 
                margin: 8px 0; 
                color: #666;
                font-size: 14px;
            }
            .metric { 
                font-size: 32px; 
                font-weight: bold; 
                color: #667eea;
                margin-top: 15px;
                display: block;
            }
            .actions {
                background: rgba(255, 255, 255, 0.95);
                padding: 25px;
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }
            .actions h2 {
                margin-bottom: 20px;
                color: #333;
            }
            button { 
                padding: 12px 24px; 
                margin: 5px; 
                background: #667eea; 
                color: white; 
                border: none; 
                border-radius: 6px; 
                cursor: pointer;
                font-size: 14px;
                font-weight: bold;
                transition: all 0.3s ease;
            }
            button:hover { 
                background: #5568d3;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            button.health { background: #2196F3; }
            button.health:hover { background: #1976D2; }
            button.logs { background: #9C27B0; }
            button.logs:hover { background: #7B1FA2; }
            #output { 
                margin-top: 20px; 
                padding: 20px; 
                background: #1e1e1e; 
                border-radius: 8px; 
                font-family: 'Courier New', monospace; 
                white-space: pre-wrap;
                color: #4CAF50;
                max-height: 400px;
                overflow-y: auto;
                font-size: 13px;
                line-height: 1.5;
            }
            .timestamp {
                color: #999;
                font-size: 12px;
                display: block;
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🌐 5G Network Slicing Orchestration Platform</h1>
                <p>Real-time Monitoring & Slice Management Dashboard</p>
                <span class="timestamp" id="currentTime"></span>
            </div>
            
            <div class="grid">
                <div class="card core">
                    <h2>📡 5G Core Network</h2>
                    <div class="status running">● RUNNING</div>
                    <p><strong>AMF:</strong> oai-amf.5g-core.svc</p>
                    <p><strong>SMF:</strong> oai-smf.5g-core.svc</p>
                    <p><strong>UPF:</strong> oai-upf.5g-core.svc</p>
                    <span class="metric">3/3</span>
                    <p style="margin-top: 10px; font-size: 12px;">Components Active</p>
                </div>
                
                <div class="card ric">
                    <h2>🎛️ RAN Intelligent Controller</h2>
                    <div class="status running">● RUNNING</div>
                    <p><strong>Service:</strong> flexric.5g-ric.svc</p>
                    <p><strong>Port:</strong> 4560 (E2 Interface)</p>
                    <p><strong>Status:</strong> Monitoring RAN</p>
                    <span class="metric">Active</span>
                </div>
                
                <div class="card orchestrator">
                    <h2>🎯 Slice Orchestrator</h2>
                    <div class="status running">● RUNNING</div>
                    <p><strong>API:</strong> slice-orchestrator.5g-orchestrator.svc</p>
                    <p><strong>Port:</strong> 8080</p>
                    <p><strong>Function:</strong> UE Migration & Context Management</p>
                    <span class="metric">Online</span>
                </div>
                
                <div class="card redis">
                    <h2>💾 Context Storage (Redis)</h2>
                    <div class="status running" id="redisStatus">● CHECKING</div>
                    <p><strong>Host:</strong> redis-master.5g-core.svc</p>
                    <p><strong>Port:</strong> 6379</p>
                    <p><strong>Type:</strong> In-Memory Key-Value Store</p>
                    <span class="metric" id="redisMetric">—</span>
                </div>
            </div>
            
            <div class="actions">
                <h2>📊 Quick Actions & Tests</h2>
                <button onclick="testRedis()">🔴 Test Redis Connection</button>
                <button onclick="checkHealth()" class="health">❤️ Check Orchestrator Health</button>
                <button onclick="viewDocs()" class="logs">📖 API Documentation</button>
                <div id="output"></div>
            </div>

            <div class="actions" style="margin-top: 30px;">
                <h2>📜 Recent Migration History</h2>
                <table style="width: 100%; border-collapse: collapse; color: #333; text-align: left;">
                    <thead>
                        <tr style="border-bottom: 2px solid #667eea;">
                            <th style="padding: 12px;">UE ID</th>
                            <th>Status</th>
                            <th>HIT (ms)</th>
                            <th>Target Slice</th>
                            <th>Time</th>
                        </tr>
                    </thead>
                    <tbody id="historyBody">
                        </tbody>
                </table>
            </div>

            <div class="card analytics">
                <h3>⏱️ Latest HIT (Latency)</h3>
                <span class="metric"><span id="hitVal">0.00</span> <small style="font-size:14px">ms</small></span>
                <p>Handover Interruption Time</p>
            </div>
            <div class="card analytics">
                <h3>🟢 System Status</h3>
                <div style="color: green; font-weight: bold; margin-top:10px">● ACTIVE</div>
                <p style="margin-top:10px">N4, N2, N11 Interfaces Online</p>
                <p>SBA Architecture Verified</p>
            </div>
            <div class="card analytics">
                <h3>🚀 Manual Trigger</h3>
                <p style="margin-bottom:15px">Force inter-slice migration test</p>
                <button onclick="triggerMigration()" style="width:100%; background:#E91E63">Start Test Migration</button>
            </div>
        </div>
        
        <script>
            async function triggerMigration() {
                await fetch('/trigger-migration', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ue_id: "UE-" + Math.floor(Math.random()*1000), current_slice: "EMBB", target_slice: "URLLC"})
                });
                updateStats();
            }
            // Update timestamp
            function updateTime() {
                const now = new Date();
                document.getElementById('currentTime').textContent = 
                    'Last updated: ' + now.toLocaleString();
            }
            updateTime();
            setInterval(updateTime, 1000);
            
            // Check Redis on load
            window.onload = async function() {
                await checkHealth();
            };
            
            async function testRedis() {
                const output = document.getElementById('output');
                output.textContent = '⏳ Testing Redis connection...\\n';
                
                try {
                    const response = await fetch('/example');
                    const data = await response.json();
                    output.textContent = '✅ Redis Test Successful!\\n\\n' + 
                        JSON.stringify(data, null, 2);
                    updateRedisStatus('CONNECTED', '✅');
                } catch (error) {
                    output.textContent = '❌ Redis Test Failed!\\n\\nError: ' + error.message;
                    updateRedisStatus('ERROR', '❌');
                }
            }
            
            async function checkHealth() {
                const output = document.getElementById('output');
                output.textContent = '⏳ Checking orchestrator health...\\n';
                
                try {
                    const response = await fetch('/health');
                    const data = await response.json();
                    output.textContent = '✅ Health Check Complete!\\n\\n' + 
                        JSON.stringify(data, null, 2);
                    
                    // Update Redis status based on health check
                    if (data.redis === 'connected') {
                        updateRedisStatus('CONNECTED', '✅');
                    } else {
                        updateRedisStatus('ERROR', '❌');
                    }
                } catch (error) {
                    output.textContent = '❌ Health Check Failed!\\n\\nError: ' + error.message;
                }
            }

            async function updateMetrics() {
                try {
                    const response = await fetch('/stats');
                    const data = await response.json();
        
                    // Update the HIT counter
                    document.getElementById('hitMetric').textContent = data.latest_hit_ms;
        
                    // Update the History Table
                    const tbody = document.getElementById('historyBody');
                    tbody.innerHTML = ''; // Clear current rows
        
                    data.history.forEach(item => {
                        const row = tbody.insertRow();
                        row.style.borderBottom = "1px solid #eee";
                        row.style.fontSize = "14px";
            
                        const statusColor = item.status === 'SUCCESS' ? '#4CAF50' : '#f44336';
            
                        row.innerHTML = `
                             <td style="padding: 12px; font-weight: bold;">${item.ue_id}</td>
                             <td style="color: ${statusColor}; font-weight: bold;">${item.status}</td>
                             <td>${item.hit !== null ? item.hit.toFixed(2) + ' ms' : 'N/A'}</td>
                             <td>${item.target_slice}</td>
                             <td style="color: #999; font-size: 12px;">${item.timestamp}</td>
                        `;
                    });
                } catch (e) {
                    console.error("Failed to fetch metrics", e);
                }
            }
            // Poll every 2 seconds
            setInterval(updateMetrics, 2000);

            
            function updateRedisStatus(status, metric) {
                const statusEl = document.getElementById('redisStatus');
                const metricEl = document.getElementById('redisMetric');
                
                statusEl.textContent = '● ' + status;
                statusEl.className = 'status ' + (status === 'CONNECTED' ? 'running' : 'error');
                metricEl.textContent = metric;
            }
            
            function viewDocs() {
                window.open('/docs', '_blank');
            }

            let hitChart;

            function initChart() {
                const ctx = document.getElementById('hitChart').getContext('2d');
                hitChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: ['', '', '', '', '', '', '', '', '', ''],
                        datasets: [{
                            label: 'HIT (ms)',
                            data: [],
                            borderColor: '#667eea',
                            backgroundColor: 'rgba(102, 126, 234, 0.1)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 0
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { display: false },
                            y: { beginAtZero: true, grid: { display: false }, ticks: { font: { size: 10 } } }
                        }
                    }
                });
            }

            window.onload = () => {
                initChart();
                setInterval(() => {
                    document.getElementById('currentTime').textContent = 'System Time: ' + new Date().toLocaleString();
                    updateStats();
                }, 2000);
                updateStats();
                checkHealth();
            };
            
        </script>
    </body>
    </html>
    """


# -------------------------
# Retry Helper
# -------------------------
async def retry(coro_fn, *args, retries=MAX_RETRIES, delay=RETRY_DELAY, **kwargs):
    """Simple retry helper for async operations."""
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


# -------------------------
# Clients & Helpers
# -------------------------
class SliceClient:
    """Client for interacting with an OAI-like SMF/AMF Slice API."""

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

    async def nsmf_pdusession_create(self, ue_id: str, source_context: Dict):
        """
        Simulates Namf_Communication -> Nsmf_PDUSession_CreateSMContext.
        The target SMF receives the old context and allocates a new N3 TEID.
        """
        url = f"{self.base_url}/nsmf-pdusession/v1/sm-contexts"
        # 3GPP mapping: Map source context to Target S-NSSAI
        payload = {
            "ue_id": ue_id,
            "s_nssai": {"sst": 1, "sd": "000001"},
            "source_smf_uri": source_context["smf_uri"],
            "pdu_session_id": source_context["pdu_id"]
        }
        async with self.session.post(url, json=payload) as resp:
            resp.raise_for_status()
            # Returns target_teid and target_upf_address
            return await resp.json()

    async def namf_comm_release(self, ue_id: str):
        """
        Simulates Namf_Communication_UEContextRelease.
        Triggered only after the target slice confirms the UE is active.
        """
        url = f"{self.base_url}/namf-comm/v1/ue-contexts/{ue_id}/release"
        async with self.session.post(url, json={"cause": "SLICE_MIGRATION_COMPLETE"}) as resp:
            return resp.status == 204

    async def namf_comm_get_context(self, ue_id: str) -> Dict:
        """Step 3: Orchestrator -> Slice A (GET context)"""
        async with self.session.get(f"{self.base_url}/namf-comm/v1/ue-contexts/{ue_id}") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def nsmf_pdusession_import_notification(self, ue_id: str):
        """Step 4 & 5: Notify target slice B to fetch context from Redis & Bind"""
        url = f"{self.base_url}/nsmf-pdusession/v1/import-context"
        async with self.session.post(url, json={"ue_id": ue_id, "source": "redis"}) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def confirm_binding(self, ue_id: str):
        """Step 8: Final ACK from target slice"""
        async with self.session.get(f"{self.base_url}/confirm/{ue_id}") as resp:
            return resp.status == 200


class RedisStore:
    """Wrapper around the redis.asyncio library to store/retrieve contexts."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client = None

    async def connect(self):
        """Initialize the Redis connection."""
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)

    async def close(self):
        """Close the Redis connection."""
        if self.redis_client:
            await self.redis_client.close()

    async def set_context(self, key: str, val: Dict, ex=300):
        await self.redis.set(key, json.dumps(val), ex=ex)

    async def get_context(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a value from Redis."""
        val = await self.redis_client.get(key)
        if val is not None:
            # Deserialize the value (use JSON if necessary)
            return json.loads(val)  # Avoid `eval` in production; use something safer like `json.loads`
        return None

    async def set_migration_state(self, ue_id: str, state: str, data: Dict = None):
        """States: INIT, PREPARED, UPF_CONFIGURED, COMMITTED, ROLLBACK"""
        payload = {"state": state, "updated_at": str(asyncio.get_event_loop().time())}
        if data:
            payload["metadata"] = data
        await self.redis_client.set(f"migrate_state:{ue_id}", json.dumps(payload), ex=300)

    async def get_migration_state(self, ue_id: str):
        val = await self.redis_client.get(f"migrate_state:{ue_id}")
        return json.loads(val) if val else None

    async def store_metric(self, ue_id: str, metric_name: str, value: float):
        # Store individual UE result
        await self.redis_client.set(f"metric:{ue_id}:{metric_name}", value, ex=3600)
        # Add to a list for global dashboard stats (e.g., last 10 handovers)
        await self.redis_client.lpush(f"stats:history:{metric_name}", value)
        await self.redis_client.ltrim(f"stats:history:{metric_name}", 0, 9)

    async def get_latest_metrics(self):
        """Helper for the dashboard API"""
        history = await self.redis_client.lrange("stats:history:handover_interruption_ms", 0, -1)
        if not history:
            return 0.0
        # Return the latest value
        return float(history[0])

    async def add_migration_history(self, record: Dict[str, Any]):
        """Appends a migration result and trims the list to the last 5 entries."""
        # record: {"ue_id": "U123", "status": "SUCCESS", "hit": 4.5, "timestamp": "..."}
        await self.redis_client.lpush("stats:migration_history", json.dumps(record))
        await self.redis_client.ltrim("stats:migration_history", 0, 4)

    async def get_migration_history(self):
        """Fetches the history list from Redis."""
        history = await self.redis_client.lrange("stats:migration_history", 0, -1)
        return [json.loads(item) for item in history]    

    async def get_dashboard_stats(self):
        history = await self.redis.lrange("stats:history", 0, -1)
        hit = await self.redis.get("stats:latest_hit")
        return {
            "history": [json.loads(h) for h in history],
            "latest_hit": float(hit) if hit else 0.0
        }


class FlexRANClient:
    """Client to notify FlexRAN about slice/QoS mapping changes."""
    def __init__(self, base_url: str, session: aiohttp.ClientSession):
        self.session = session
        self.base_url = base_url.rstrip("/")

    async def notify_slice_change(self, ue_id: str, new_slice: str) -> None:
        url = f"{self.base_url}/slice-change"
        payload = {"ue_id": ue_id, "new_slice": new_slice}
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.post(url, json=payload) as resp:
                resp.raise_for_status()

class UPFClient:
    """UPF client (PFCP or REST) to request tunnel reconfiguration."""
    def __init__(self, base_url: str, session: aiohttp.ClientSession):
        self.session = session
        self.base_url = base_url.rstrip("/")

    async def reconfigure_tunnels(self, ue_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/pfcp/reconfigure"
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.post(url, json={"ue_id": ue_id, **params}) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def create_shadow_tunnel(self, ue_id: str, pdu_id: int, target_params: Dict):
        """
        Refined PFCP-like payload for seamless TEID swapping.
        We instruct the UPF to recognize a new 'Local TEID' while 
        maintaining the old one until a DELETE command is sent.
        """
        payload = {
            "node_id": "upf-core-01",
            "pdu_session_id": pdu_id,
            "operations": [
                {
                    "type": "CREATE_PDR",
                    "pdr_id": 2, # New PDR for the target slice
                    "precedence": 10,
                    "pdi": {
                        "source_interface": "ACCESS",
                        "local_teid": target_params["target_teid"],
                        "ue_ip_address": target_params["ue_ip"]
                    },
                    "far_id": 2
                },
                {
                   "type": "CREATE_FAR",
                   "far_id": 2,
                   "apply_action": "FORWARD",
                   "forwarding_parameters": {
                        "destination_interface": "CORE",
                        "network_instance": target_params["target_slice_dnn"]
                    }
                }
            ]
        }
        async with self.session.post(f"{self.base_url}/n4/sessions/{ue_id}/modify", json=payload) as resp:
            if resp.status != 200:
                raise Exception("UPF Shadow Tunnel Allocation Failed")
            return await resp.json()

  
@dataclass
class UEInfo:
    ue_id: str
    current_slice: str
    target_slice: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class SliceInfo(BaseModel):
    sst: int  # Slice/Service Type
    sd: Optional[str] = None  # Slice Differentiator


class MigrateRequest(BaseModel):
    ue_id: str
    source_snssai: SliceInfo
    target_snssai: SliceInfo
    pdu_session_id: int


@dataclass
class MigrationRecord:
    ue_id: str
    status: str
    hit: Optional[float]
    target_slice: str
    timestamp: str


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

    async def monitor_and_maybe_migrate(self, ue: UEInfo) -> None:
        """
        High-level monitoring callback. In a real system this might be driven by metrics/alerting.
        Here, we assume the decision is already made externally and passed in ue.target_slice.
        """
        logger.info("Monitor: UE=%s current_slice=%s", ue.ue_id, ue.current_slice)
        if not ue.target_slice or ue.target_slice == ue.current_slice:
            logger.info("No migration needed for UE=%s", ue.ue_id)
            return

        logger.info("Decided to migrate UE=%s -> %s", ue.ue_id, ue.target_slice)
        # await self.migrate_ue(ue)
        await migrate_ue_seamless(ue)


    async def migrate_ue_seamless(self, ue: UEInfo, pdu_id: int):
        ue_id = ue.ue_id
        try:
            # Step 1: INIT
            await self.redis.set_migration_state(ue_id, "INIT")
            source_ctx = await self.slice_a.get_ue_context(ue_id)
        
            # Step 2: PREPARE (Target SMF allocates resources)
            await self.redis.set_migration_state(ue_id, "PREPARING")
            target_sm_res = await self.slice_b.nsmf_pdusession_create(ue_id, source_ctx)


            # Step 3: GET Context from Slice A and Store in Redis
            context = await self.slice_a.namf_comm_get_context(ue_id)
            await self.redis.set_context(f"ue:{ue_id}:context", context)

            # Step 4 & 5: Instruct Slice B to fetch from Redis and Bind
            await self.slice_b.nsmf_pdusession_import_notification(ue_id)
        
            # Step 3: UPF RECONFIG (The potential failure point)
            await self.redis.set_migration_state(ue_id, "UPF_CONFIGURING")
            try:
                # We pass the new TEID received from Slice B to the UPF
                await self.upf.create_shadow_tunnel(ue_id, pdu_id, target_sm_res)
            except Exception as e:
                logger.error(f"Step 3 Failed: {e}. Initiating Rollback.")
                await self.handle_rollback(ue, pdu_id)
                return

            # --- START MEASURING Handover Interruption Time (HIT) ---
            # The "Critical Instant" starts here
            start_hit = time.perf_counter() 

            # Step 4: COMMIT (RAN Switch)
            await self.flexran.notify_slice_change(ue_id, ue.target_slice)

            # Step 7: Update UPF (PFCP)
            await self.upf.reconfigure_tunnels(ue_id, pdu_id, context)

            # Step 8: Final ACK
            await self.slice_b.confirm_binding(ue_id)

            # Step 5: Target Confirmation (Binding completion)
            await self.slice_b.commit_session(ue_id, pdu_id)

            end_hit = time.perf_counter()
            # --- END MEASURING HIT ---

            hit_ms = (end_hit - start_hit) * 1000 # Convert to milliseconds

            # Store metric in Redis for the dashboard
            await self.redis.store_metric(ue_id, "handover_interruption_ms", hit_ms)

            await self.redis.set_migration_state(ue_id, "COMMITTED")
                    
            # Step 6: CLEANUP
            await self.slice_a.namf_comm_release(ue_id)
            logger.info(f"Migration successful for {ue_id}")

            history_record = {
                "ue_id": ue_id,
                "status": "SUCCESS",
                "hit": hit_ms,
                "target_slice": ue.target_slice,
                "timestamp": time.strftime("%H:%M:%S")
            }

            await self.redis.add_migration_history(history_record)

        except Exception as e:
            logger.critical(f"Unexpected system failure: {e}")
            await self.handle_rollback(ue, pdu_id)

    async def handle_rollback(self, ue: UEInfo, pdu_id: int, failed_step: str):
        logger.warning(f"Initiating Rollback for {ue.ue_id} at step: {failed_step}")
    
        # 1. Update State to ROLLBACK
        await self.redis.set_migration_state(ue.ue_id, "ROLLBACK_IN_PROGRESS")

        # 2. Cleanup Target UPF Resources (if Step 3 was attempted)
        if failed_step in ["UPF_CONFIGURING", "RAN_SWITCHING"]:
            await self.upf.remove_target_pdr(ue.ue_id, pdu_id)

        # 3. Release Target SMF Context (if Step 2 was completed)
        await self.slice_b.nsmf_pdusession_release(ue.ue_id, pdu_id)

        # 4. Finalize state
        await self.redis.set_migration_state(ue.ue_id, "ROLLBACK_COMPLETE")
        logger.info(f"Rollback complete. UE {ue.ue_id} remains on Slice {ue.current_slice}")

        history_record = {
            "ue_id": ue.ue_id,
            "status": "FAILED",
            "hit": None,
            "target_slice": ue.target_slice,
            "timestamp": time.strftime("%H:%M:%S")
        }
        await self.redis.add_migration_history(history_record)


    async def migrate_ue(self, ue: UEInfo) -> None:
        """Perform inter-slice migration steps referencing the diagram's flow."""
        ue_id = ue.ue_id

        # 3. GET context from source slice (Slice A)
        logger.info("Step 3: Fetching UE context from source slice %s", ue.current_slice)
        context = await retry(self.slice_a.get_ue_context, ue_id)
        ue.context = context
        logger.debug("Fetched context for %s: %s", ue_id, context)

        # store in redis (diagram: OAI A -> Redis)
        logger.info("Storing context in Redis for handover")
        await retry(self.redis.set_context, f"ue:{ue_id}:context", context, retries=2)

        # 4. POST/import context to target slice (Slice B)
        logger.info("Step 4: Posting context to target slice %s", ue.target_slice)
        await retry(self.slice_b.post_ue_context, ue_id, context)

        # have target slice fetch/import context from Redis if they prefer that pattern
        # (diagram shows Redis <- Slice B fetch)
        # In this sample, we assume step is either done by our post or by the slice pulling from Redis.

        # 5. Instruct slice B to bind UE with imported context
        logger.info("Step 5: Instructing target slice to bind UE")
        await retry(self.slice_b.bind_ue, ue_id, context)

        # 6. Notify FlexRAN of slice change
        logger.info("Step 6: Notifying FlexRAN about slice change")
        await retry(self.flexran.notify_slice_change, ue_id, ue.target_slice)

        # 7. Update UPF tunnels (PFCP reconfiguration)
        logger.info("Step 7: Reconfiguring UPF tunnels for UE")
        pfcp_params = {"new_slice": ue.target_slice, "ue_context": context.get("upf_info", {})}
        upf_resp = await retry(self.upf.reconfigure_tunnels, ue_id, pfcp_params)
        logger.debug("UPF response: %s", upf_resp)

        # 8. Confirm completion (ack)
        logger.info("Step 8: Confirming completion and cleaning up")
        # Example: store migration metadata or call back to source slice to release old context
        # Here we send a simple cleanup post (not implemented on client for brevity)
        # Optionally instruct source slice to remove old UE binding (not shown)

        logger.info("Migration complete for UE=%s -> %s", ue_id, ue.target_slice)

# -------------------------
# FastAPI Endpoints
# -------------------------
class MigrateRequest(BaseModel):
    ue_id: str
    current_slice: str
    target_slice: str
    slice_baseurl: str  # Base URL for slice API



@app.post("/trigger-migration")
async def trigger(ue: UEInfo):
    # Simulated migration logic
    hit_ms = 2.0 + (time.time() % 5) # Simulating variable latency
    record = {
        "ue_id": ue.ue_id,
        "status": "SUCCESS",
        "hit": hit_ms,
        "target_slice": ue.target_slice,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }
    await redis_client.lpush("stats:history", json.dumps(record))
    await redis_client.ltrim("stats:history", 0, 4)
    await redis_client.set("stats:latest_hit", hit_ms)
    # Push to trend list
    await redis_client.lpush("stats:hit_trend", hit_ms)
    await redis_client.ltrim("stats:hit_trend", 0, 9)
    return {"status": "ok"}


@app.postold("/migrate")
async def migrate(req: MigrateRequest):
    """API endpoint to trigger migration."""
    async with aiohttp.ClientSession() as session:
        slice_client = SliceClient(req.slice_baseurl, session)
        redis_store = RedisStore(redis_url=REDIS_URL)
        await redis_store.connect()

        orchestrator = Orchestrator(slice_client, redis_store)
        ue = UEInfo(
            ue_id=req.ue_id,
            current_slice=req.current_slice,
            target_slice=req.target_slice,
        )

        await orchestrator.migrate_ue(ue)
        return {"status": "success", "ue_id": ue.ue_id, "target_slice": req.target_slice}


@app.get("/context/{ue_id}")
async def get_context(ue_id: str):
    """Fetch the UE context from Redis."""
    redis_store = RedisStore(redis_url=REDIS_URL)
    await redis_store.connect()

    # Set a value in Redis
    await redis_store.set_context("key", {"example": "data"}, ex=300)

    context = await redis_store.get_context(f"ue:{ue_id}:context")
    if not context:
        raise HTTPException(status_code=404, detail=f"No context found for UE {ue_id}")

    await redis_store.close()
    return context


# -------------------------
# Main Entry Point
# -------------------------
async def main():
    """Run the Uvicorn server."""
    uvicorn.run(app, host="0.0.0.0", port=8000)

    # create HTTP session for all clients
    async with aiohttp.ClientSession() as session:
        # instantiate clients with example endpoints (replace with real addresses)
        slice_a_client = SliceClient("http://localhost:8001", session)
        slice_b_client = SliceClient("http://localhost:8002", session)
        flexran = FlexRANClient("http://localhost:9000", session)
        upf = UPFClient("http://localhost:7000", session)

        # connect to redis
        redis_store = RedisStore(REDIS_URL)
        await redis_store.connect()

        orch = Orchestrator(slice_a_client, slice_b_client, redis_store, flexran, upf)

        # simulate a decision to migrate UE 'U123' from sliceA -> sliceB
        ue = UEInfo(ue_id="U123", current_slice="sliceA", target_slice="sliceB")

        try:
            await orch.monitor_and_maybe_migrate(ue)
        finally:
            await redis_store.close()


if __name__ == "__main__":
    asyncio.run(main())import os
import uuid
import asyncio
import logging
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional

import aiohttp
import redis.asyncio as redis
import async_timeout
from dataclasses import dataclass

import uvicorn  # Add this for running the app directly

# -------------------------
# Configuration & constants
# -------------------------
# Redis is deployed in 5g-core namespace, NOT default!
REDIS_URL = os.getenv("REDIS_URL", "redis://redis-master.5g-core.svc.cluster.local:6379")
HTTP_TIMEOUT = 5  # seconds
RETRY_DELAY = 1  # seconds
MAX_RETRIES = 3

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator")

# FastAPI App
app = FastAPI(title="Inter-slice Orchestrator")

@app.on_event("startup")
async def app_startup():
    global redis_store
    redis_store = RedisStore(REDIS_URL)
    await redis_store.connect()
    logger.info(f"Connected to Redis at {REDIS_URL}")


@app.on_event("shutdown")
async def app_shutdown():
    await redis_store.close()
    logger.info("Closed Redis connection")


@app.get("/health")
async def health():
    """Health check endpoint"""
    try:
        # Test Redis connection
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
    """Test Redis connection"""
    await redis_store.set_context("test_key", {"foo": "bar", "timestamp": str(asyncio.get_event_loop().time())}, ex=300)
    return await redis_store.get_context("test_key")


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Dashboard UI"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>5G Network Slicing Dashboard</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container { 
                max-width: 1400px; 
                margin: 0 auto; 
            }
            .header { 
                text-align: center; 
                padding: 30px; 
                background: rgba(255, 255, 255, 0.95); 
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                margin-bottom: 30px;
            }
            .header h1 { 
                font-size: 36px; 
                color: #667eea; 
                margin-bottom: 10px;
            }
            .header p { 
                color: #666; 
                font-size: 16px;
            }
            .grid { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); 
                gap: 20px; 
                margin-bottom: 30px;
            }
            .card { 
                background: rgba(255, 255, 255, 0.95); 
                padding: 25px; 
                border-radius: 12px; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                border-left: 5px solid #667eea;
                transition: transform 0.3s ease, box-shadow 0.3s ease;
            }
            .card:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 40px rgba(0,0,0,0.3);
            }
            .card.core { border-left-color: #2196F3; }
            .card.ran { border-left-color: #FF9800; }
            .card.ric { border-left-color: #9C27B0; }
            .card.orchestrator { border-left-color: #4CAF50; }
            .card.redis { border-left-color: #DC382D; }
            .status { 
                display: inline-block; 
                padding: 6px 14px; 
                border-radius: 20px; 
                font-size: 12px; 
                font-weight: bold;
                margin-top: 10px; 
                text-transform: uppercase;
            }
            .status.running { background: #4CAF50; color: white; }
            .status.pending { background: #FF9800; color: white; }
            .status.error { background: #f44336; color: white; }
            h2 { 
                margin: 10px 0; 
                font-size: 22px; 
                color: #333;
            }
            .card p { 
                margin: 8px 0; 
                color: #666;
                font-size: 14px;
            }
            .metric { 
                font-size: 32px; 
                font-weight: bold; 
                color: #667eea;
                margin-top: 15px;
                display: block;
            }
            .actions {
                background: rgba(255, 255, 255, 0.95);
                padding: 25px;
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }
            .actions h2 {
                margin-bottom: 20px;
                color: #333;
            }
            button { 
                padding: 12px 24px; 
                margin: 5px; 
                background: #667eea; 
                color: white; 
                border: none; 
                border-radius: 6px; 
                cursor: pointer;
                font-size: 14px;
                font-weight: bold;
                transition: all 0.3s ease;
            }
            button:hover { 
                background: #5568d3;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            button.health { background: #2196F3; }
            button.health:hover { background: #1976D2; }
            button.logs { background: #9C27B0; }
            button.logs:hover { background: #7B1FA2; }
            #output { 
                margin-top: 20px; 
                padding: 20px; 
                background: #1e1e1e; 
                border-radius: 8px; 
                font-family: 'Courier New', monospace; 
                white-space: pre-wrap;
                color: #4CAF50;
                max-height: 400px;
                overflow-y: auto;
                font-size: 13px;
                line-height: 1.5;
            }
            .timestamp {
                color: #999;
                font-size: 12px;
                display: block;
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🌐 5G Network Slicing Orchestration Platform</h1>
                <p>Real-time Monitoring & Slice Management Dashboard</p>
                <span class="timestamp" id="currentTime"></span>
            </div>
            
            <div class="grid">
                <div class="card core">
                    <h2>📡 5G Core Network</h2>
                    <div class="status running">● RUNNING</div>
                    <p><strong>AMF:</strong> oai-amf.5g-core.svc</p>
                    <p><strong>SMF:</strong> oai-smf.5g-core.svc</p>
                    <p><strong>UPF:</strong> oai-upf.5g-core.svc</p>
                    <span class="metric">3/3</span>
                    <p style="margin-top: 10px; font-size: 12px;">Components Active</p>
                </div>
                
                <div class="card ric">
                    <h2>🎛️ RAN Intelligent Controller</h2>
                    <div class="status running">● RUNNING</div>
                    <p><strong>Service:</strong> flexric.5g-ric.svc</p>
                    <p><strong>Port:</strong> 4560 (E2 Interface)</p>
                    <p><strong>Status:</strong> Monitoring RAN</p>
                    <span class="metric">Active</span>
                </div>
                
                <div class="card orchestrator">
                    <h2>🎯 Slice Orchestrator</h2>
                    <div class="status running">● RUNNING</div>
                    <p><strong>API:</strong> slice-orchestrator.5g-orchestrator.svc</p>
                    <p><strong>Port:</strong> 8080</p>
                    <p><strong>Function:</strong> UE Migration & Context Management</p>
                    <span class="metric">Online</span>
                </div>
                
                <div class="card redis">
                    <h2>💾 Context Storage (Redis)</h2>
                    <div class="status running" id="redisStatus">● CHECKING</div>
                    <p><strong>Host:</strong> redis-master.5g-core.svc</p>
                    <p><strong>Port:</strong> 6379</p>
                    <p><strong>Type:</strong> In-Memory Key-Value Store</p>
                    <span class="metric" id="redisMetric">—</span>
                </div>
            </div>
            
            <div class="actions">
                <h2>📊 Quick Actions & Tests</h2>
                <button onclick="testRedis()">🔴 Test Redis Connection</button>
                <button onclick="checkHealth()" class="health">❤️ Check Orchestrator Health</button>
                <button onclick="viewDocs()" class="logs">📖 API Documentation</button>
                <div id="output"></div>
            </div>
        </div>
        
        <script>
            // Update timestamp
            function updateTime() {
                const now = new Date();
                document.getElementById('currentTime').textContent = 
                    'Last updated: ' + now.toLocaleString();
            }
            updateTime();
            setInterval(updateTime, 1000);
            
            // Check Redis on load
            window.onload = async function() {
                await checkHealth();
            };
            
            async function testRedis() {
                const output = document.getElementById('output');
                output.textContent = '⏳ Testing Redis connection...\\n';
                
                try {
                    const response = await fetch('/example');
                    const data = await response.json();
                    output.textContent = '✅ Redis Test Successful!\\n\\n' + 
                        JSON.stringify(data, null, 2);
                    updateRedisStatus('CONNECTED', '✅');
                } catch (error) {
                    output.textContent = '❌ Redis Test Failed!\\n\\nError: ' + error.message;
                    updateRedisStatus('ERROR', '❌');
                }
            }
            
            async function checkHealth() {
                const output = document.getElementById('output');
                output.textContent = '⏳ Checking orchestrator health...\\n';
                
                try {
                    const response = await fetch('/health');
                    const data = await response.json();
                    output.textContent = '✅ Health Check Complete!\\n\\n' + 
                        JSON.stringify(data, null, 2);
                    
                    // Update Redis status based on health check
                    if (data.redis === 'connected') {
                        updateRedisStatus('CONNECTED', '✅');
                    } else {
                        updateRedisStatus('ERROR', '❌');
                    }
                } catch (error) {
                    output.textContent = '❌ Health Check Failed!\\n\\nError: ' + error.message;
                }
            }
            
            function updateRedisStatus(status, metric) {
                const statusEl = document.getElementById('redisStatus');
                const metricEl = document.getElementById('redisMetric');
                
                statusEl.textContent = '● ' + status;
                statusEl.className = 'status ' + (status === 'CONNECTED' ? 'running' : 'error');
                metricEl.textContent = metric;
            }
            
            function viewDocs() {
                window.open('/docs', '_blank');
            }
        </script>
    </body>
    </html>
    """


# -------------------------
# Retry Helper
# -------------------------
async def retry(coro_fn, *args, retries=MAX_RETRIES, delay=RETRY_DELAY, **kwargs):
    """Simple retry helper for async operations."""
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


# -------------------------
# Clients & Helpers
# -------------------------
class SliceClient:
    """Client for interacting with an OAI-like SMF/AMF Slice API."""

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


class RedisStore:
    """Wrapper around the redis.asyncio library to store/retrieve contexts."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client = None

    async def connect(self):
        """Initialize the Redis connection."""
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)

    async def close(self):
        """Close the Redis connection."""
        if self.redis_client:
            await self.redis_client.close()

    async def set_context(self, key: str, value: Dict[str, Any], ex: Optional[int] = None):
        """Set a value in Redis with an optional expiration time."""
        await self.redis_client.set(key, json.dumps(value), ex=ex)

    async def get_context(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a value from Redis."""
        val = await self.redis_client.get(key)
        if val is not None:
            # Deserialize the value (use JSON if necessary)
            return json.loads(val)  # Avoid `eval` in production; use something safer like `json.loads`
        return None


class FlexRANClient:
    """Client to notify FlexRAN about slice/QoS mapping changes."""
    def __init__(self, base_url: str, session: aiohttp.ClientSession):
        self.session = session
        self.base_url = base_url.rstrip("/")

    async def notify_slice_change(self, ue_id: str, new_slice: str) -> None:
        url = f"{self.base_url}/slice-change"
        payload = {"ue_id": ue_id, "new_slice": new_slice}
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.post(url, json=payload) as resp:
                resp.raise_for_status()

class UPFClient:
    """UPF client (PFCP or REST) to request tunnel reconfiguration."""
    def __init__(self, base_url: str, session: aiohttp.ClientSession):
        self.session = session
        self.base_url = base_url.rstrip("/")

    async def reconfigure_tunnels(self, ue_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/pfcp/reconfigure"
        async with async_timeout.timeout(HTTP_TIMEOUT):
            async with self.session.post(url, json={"ue_id": ue_id, **params}) as resp:
                resp.raise_for_status()
                return await resp.json()


@dataclass
class UEInfo:
    ue_id: str
    current_slice: str
    target_slice: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


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

    async def monitor_and_maybe_migrate(self, ue: UEInfo) -> None:
        """
        High-level monitoring callback. In a real system this might be driven by metrics/alerting.
        Here, we assume the decision is already made externally and passed in ue.target_slice.
        """
        logger.info("Monitor: UE=%s current_slice=%s", ue.ue_id, ue.current_slice)
        if not ue.target_slice or ue.target_slice == ue.current_slice:
            logger.info("No migration needed for UE=%s", ue.ue_id)
            return

        logger.info("Decided to migrate UE=%s -> %s", ue.ue_id, ue.target_slice)
        await self.migrate_ue(ue)

    async def migrate_ue(self, ue: UEInfo) -> None:
        """Perform inter-slice migration steps referencing the diagram's flow."""
        ue_id = ue.ue_id

        # 3. GET context from source slice (Slice A)
        logger.info("Step 3: Fetching UE context from source slice %s", ue.current_slice)
        context = await retry(self.slice_a.get_ue_context, ue_id)
        ue.context = context
        logger.debug("Fetched context for %s: %s", ue_id, context)

        # store in redis (diagram: OAI A -> Redis)
        logger.info("Storing context in Redis for handover")
        await retry(self.redis.set_context, f"ue:{ue_id}:context", context, retries=2)

        # 4. POST/import context to target slice (Slice B)
        logger.info("Step 4: Posting context to target slice %s", ue.target_slice)
        await retry(self.slice_b.post_ue_context, ue_id, context)

        # have target slice fetch/import context from Redis if they prefer that pattern
        # (diagram shows Redis <- Slice B fetch)
        # In this sample, we assume step is either done by our post or by the slice pulling from Redis.

        # 5. Instruct slice B to bind UE with imported context
        logger.info("Step 5: Instructing target slice to bind UE")
        await retry(self.slice_b.bind_ue, ue_id, context)

        # 6. Notify FlexRAN of slice change
        logger.info("Step 6: Notifying FlexRAN about slice change")
        await retry(self.flexran.notify_slice_change, ue_id, ue.target_slice)

        # 7. Update UPF tunnels (PFCP reconfiguration)
        logger.info("Step 7: Reconfiguring UPF tunnels for UE")
        pfcp_params = {"new_slice": ue.target_slice, "ue_context": context.get("upf_info", {})}
        upf_resp = await retry(self.upf.reconfigure_tunnels, ue_id, pfcp_params)
        logger.debug("UPF response: %s", upf_resp)

        # 8. Confirm completion (ack)
        logger.info("Step 8: Confirming completion and cleaning up")
        # Example: store migration metadata or call back to source slice to release old context
        # Here we send a simple cleanup post (not implemented on client for brevity)
        # Optionally instruct source slice to remove old UE binding (not shown)

        logger.info("Migration complete for UE=%s -> %s", ue_id, ue.target_slice)

# -------------------------
# FastAPI Endpoints
# -------------------------
class MigrateRequest(BaseModel):
    ue_id: str
    current_slice: str
    target_slice: str
    slice_baseurl: str  # Base URL for slice API


@app.post("/migrate")
async def migrate(req: MigrateRequest):
    """API endpoint to trigger migration."""
    async with aiohttp.ClientSession() as session:
        slice_client = SliceClient(req.slice_baseurl, session)
        redis_store = RedisStore(redis_url=REDIS_URL)
        await redis_store.connect()

        orchestrator = Orchestrator(slice_client, redis_store)
        ue = UEInfo(
            ue_id=req.ue_id,
            current_slice=req.current_slice,
            target_slice=req.target_slice,
        )

        await orchestrator.migrate_ue(ue)
        return {"status": "success", "ue_id": ue.ue_id, "target_slice": req.target_slice}


@app.get("/context/{ue_id}")
async def get_context(ue_id: str):
    """Fetch the UE context from Redis."""
    redis_store = RedisStore(redis_url=REDIS_URL)
    await redis_store.connect()

    # Set a value in Redis
    await redis_store.set_context("key", {"example": "data"}, ex=300)

    context = await redis_store.get_context(f"ue:{ue_id}:context")
    if not context:
        raise HTTPException(status_code=404, detail=f"No context found for UE {ue_id}")

    await redis_store.close()
    return context


# -------------------------
# Main Entry Point
# -------------------------
async def main():
    """Run the Uvicorn server."""
    uvicorn.run(app, host="0.0.0.0", port=8000)

    # create HTTP session for all clients
    async with aiohttp.ClientSession() as session:
        # instantiate clients with example endpoints (replace with real addresses)
        slice_a_client = SliceClient("http://localhost:8001", session)
        slice_b_client = SliceClient("http://localhost:8002", session)
        flexran = FlexRANClient("http://localhost:9000", session)
        upf = UPFClient("http://localhost:7000", session)

        # connect to redis
        redis_store = RedisStore(REDIS_URL)
        await redis_store.connect()

        orch = Orchestrator(slice_a_client, slice_b_client, redis_store, flexran, upf)

        # simulate a decision to migrate UE 'U123' from sliceA -> sliceB
        ue = UEInfo(ue_id="U123", current_slice="sliceA", target_slice="sliceB")

        try:
            await orch.monitor_and_maybe_migrate(ue)
        finally:
            await redis_store.close()


if __name__ == "__main__":
    asyncio.run(main())

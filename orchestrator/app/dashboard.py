# dashboard.py

HTML_DASHBOARD_TEMPLATE = """
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
        .container { max-width: 1400px; margin: 0 auto; }
        .header { text-align: center; padding: 30px; background: rgba(255, 255, 255, 0.95); border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); margin-bottom: 30px; }
        .header h1 { font-size: 36px; color: #667eea; margin-bottom: 10px; }
        .header p { color: #666; font-size: 16px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card { background: rgba(255, 255, 255, 0.95); padding: 25px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); border-left: 5px solid #667eea; }
        .card.core { border-left-color: #2196F3; }
        .card.ran { border-left-color: #FF9800; }
        .card.ric { border-left-color: #9C27B0; }
        .card.orchestrator { border-left-color: #4CAF50; }
        .card.redis { border-left-color: #DC382D; }
        .status { display: inline-block; padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: bold; margin-top: 10px; text-transform: uppercase; }
        .status.running { background: #4CAF50; color: white; }
        .status.error { background: #f44336; color: white; }
        h2 { margin: 10px 0; font-size: 22px; color: #333; }
        .card p { margin: 8px 0; color: #666; font-size: 14px; }
        .metric { font-size: 32px; font-weight: bold; color: #667eea; margin-top: 15px; display: block; }
        .actions { background: rgba(255, 255, 255, 0.95); padding: 25px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); margin-top: 20px; }
        button { padding: 12px 24px; margin: 5px; background: #667eea; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: bold; }
        button:hover { background: #5568d3; }
        #output { margin-top: 20px; padding: 20px; background: #1e1e1e; border-radius: 8px; font-family: 'Courier New', monospace; white-space: pre-wrap; color: #4CAF50; max-height: 200px; overflow-y: auto; }
        .timestamp { color: #999; font-size: 12px; display: block; margin-top: 10px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 10px; border-bottom: 1px solid #ddd; text-align: left; }
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
                <div class="status error" id="coreStatus">● CHECKING</div>
                <p>AMF: oai-amf.5g-core.svc</p>
                <p>SMF: oai-smf.5g-core.svc</p>
                <p>UPF: oai-upf.5g-core.svc</p>
                <span class="metric" id="coreMetric">0/3</span>
            </div>
            <div class="card ric">
                <h2>🎛️ RAN Intelligent Controller</h2>
                <div class="status error" id="ricStatus">● CHECKING</div>
                <p>Service: flexric.5g-ric.svc</p>
                <p>Status: Monitoring RAN</p>
                <span class="metric" id="ricMetric">—</span>
            </div>
            <div class="card orchestrator">
                <h2>🎯 Slice Orchestrator</h2>
                <div class="status error" id="orchStatus">● CHECKING</div>
                <p>Function: Context Relocation Engine</p>
                <span class="metric" id="orchMetric">—</span>
            </div>
            <div class="card redis">
                <h2>💾 Context Storage (Redis)</h2>
                <div class="status error" id="redisStatus">● CHECKING</div>
                <p>Host: redis-master.5g-core.svc</p>
                <span class="metric" id="redisMetric">—</span>
            </div>
        </div>

        <div class="grid">
            <div class="card text-center">
                <h3>⏱️ Handover Interruption Time</h3>
                <span class="metric"><span id="hitVal">0.00</span> <small style="font-size:14px">ms</small></span>
            </div>
            <div class="card">
                <h3>🚀 Manual Migration Driver</h3>
                <button onclick="triggerMigration()" style="width:100%; background:#E91E63; margin-top:15px;">Start Test Migration</button>
            </div>
        </div>
        
        <div class="actions">
            <h2>📊 Diagnostics</h2>
            <button onclick="testRedis()">🔴 Test Redis Sync</button>
            <button onclick="checkHealth()">❤️ Control Plane Health</button>
            <div id="output"></div>
        </div>

        <div class="actions">
            <h2>📜 Execution History Log</h2>
            <table>
                <thead>
                    <tr>
                        <th>UE ID</th>
                        <th>Status</th>
                        <th>Latency (HIT)</th>
                        <th>Target Slice</th>
                        <th>Timestamp</th>
                    </tr>
                </thead>
                <tbody id="historyBody"></tbody>
            </table>
        </div>
    </div>
    
    <script>
        function updateStatusElement(elementId, metricId, statusData) {
            const statusEl = document.getElementById(elementId);
            const metricEl = document.getElementById(metricId);
            if (!statusEl) return;

            if (statusData.status === "running" || statusData.status === "healthy" || statusData.status === "online") {
                statusEl.className = "status running";
                statusEl.textContent = "● " + statusData.status.toUpperCase();
            } else {
                statusEl.className = "status error";
                statusEl.textContent = "● " + (statusData.status || "ERROR").toUpperCase();
            }
            if (metricEl && statusData.metric !== undefined) {
                metricEl.textContent = statusData.metric;
            }
        }

        async function triggerMigration() {
            const randomUeId = "UE-" + Math.floor(Math.random() * 1000);
            await fetch('/trigger-migration', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    ue_id: randomUeId, 
                    current_slice: "EMBB", 
                    target_slice: "URLLC", 
                    slice_baseurl: "http://localhost:8001"
                })
            });
            setTimeout(updateMetrics, 500);
        }
        
        async function testRedis() {
            const output = document.getElementById('output');
            try {
                const response = await fetch('/example');
                const data = await response.json();
                output.textContent = '✅ Cache Line Active:\\n' + JSON.stringify(data, null, 2);
            } catch (error) {
                output.textContent = '❌ Fail: ' + error.message;
            }
        }
        
        async function checkHealth() {
            const output = document.getElementById('output');
            try {
                const response = await fetch('/health');
                const data = await response.json();
                output.textContent = '✅ Health Matrix Status:\\n' + JSON.stringify(data, null, 2);
                await updateMetrics();
            } catch (error) {
                output.textContent = '❌ Systems Check Unresponsive';
            }
        }

        async function updateMetrics() {
            try {
                const response = await fetch('/stats');
                const data = await response.json();
                
                // Update modern dynamic metrics card states
                updateStatusElement("coreStatus", "coreMetric", data.systems.core);
                updateStatusElement("ricStatus", "ricMetric", data.systems.ric);
                updateStatusElement("orchStatus", "orchMetric", data.systems.orchestrator);
                updateStatusElement("redisStatus", "redisMetric", data.systems.redis);

                document.getElementById('hitVal').textContent = data.latest_hit_ms;
                document.getElementById('currentTime').textContent = "Last Updated: " + data.timestamp;
                
                const tbody = document.getElementById('historyBody');
                tbody.innerHTML = '';
                data.history.forEach(item => {
                    const row = tbody.insertRow();
                    row.innerHTML = `
                        <td><b>${item.ue_id}</b></td>
                        <td style="color:${item.status === 'SUCCESS' ? 'green':'red'}">${item.status}</td>
                        <td>${item.hit ? item.hit.toFixed(2) + ' ms' : '0 ms'}</td>
                        <td>${item.target_slice}</td>
                        <td>${item.timestamp}</td>
                    `;
                });
            } catch (e) { console.error(e); }
        }

        setInterval(updateMetrics, 2000);
        window.onload = () => { updateMetrics(); };
    </script>
</body>
</html>
"""

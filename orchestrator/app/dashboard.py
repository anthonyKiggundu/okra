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
                <h2>📡 Baseline 5G Core Network</h2>
                <div class="status error" id="coreStatus">● CHECKING</div>
                <p id="coreNamespace">Namespace: -</p>
                <p id="amfHost">AMF: -</p>
                <p id="smfHost">SMF: -</p>
                <p id="upfHost">UPF: -</p>
                <p id="mysqlHost">MySQL: -</p>
                <p id="ausfHost">AUSF: -</p>
                <p id="udmHost">UDM: -</p>
                <p id="udrHost">UDR: -</p>
                <span class="metric" id="coreMetric">0/7</span>
            </div>

            <div class="card ric">
                <h2>🎛️ Mosaic Controller</h2>
                <div class="status error" id="ricStatus">● CHECKING</div>
                <p>Service: flexric.5g-ric.svc</p>
                <p>Status: Monitoring RAN</p>
                <span class="metric" id="ricMetric">—</span>
            </div>

            <div class="card orchestrator">
                <h2>🎯 Slice Orchestrator</h2>
                <div class="status error" id="orchStatus">● CHECKING</div>
                <p id="orchNamespace">Namespace: -</p>
                <p id="orchRedisHost">Redis: -</p>
                <p>Function: Context Relocation Engine</p>
                <span class="metric" id="orchMetric">—</span>
            </div>

            <div class="card redis">
                <h2>📡 Orchra 5G Core Network</h2>
                <div class="status error" id="redisStatus">● CHECKING</div>
                <p id="orchraNamespace">Namespace: oai-orchra</p>
                <p id="orchraAmfHost">AMF: -</p>
                <p id="orchraSmfHost">SMF: -</p>
                <p id="orchraUpfHost">UPF: -</p>
                <p id="orchraMysqlHost">MySQL: -</p>
                <p id="orchraAusfHost">AUSF: -</p>
                <p id="orchraUdmHost">UDM: -</p>
                <p id="orchraUdrHost">UDR: -</p>
                <span class="metric" id="redisMetric">—</span>
            </div>
        </div>

        <div class="grid">
            <div class="card text-center">
                <h3>⏱️ Baseline Mosaic Migration Driver</h3>
                <span class="metric"><span id="hitVal">0.00</span> <small style="font-size:14px">ms</small></span>
                <button onclick="triggerMosaicMigration()">Start Mosaic Migration</button>
            </div>
            <div class="card">
                <h3>🚀 Orchra Migration Driver</h3>
                <span class="metric"><span id="hitValOrchra">0.00</span> <small style="font-size:14px">ms</small></span>
                <button onclick="triggerOrchraMigration()" style="width:100%; background:#E91E63; margin-top:15px;">Start Test Migration</button>
            </div>
        </div>

        <div class="actions">
            <h2>📊 Diagnostics</h2>
            <button onclick="healthBaseline()">Baseline Cluster Health</button>
            <button onclick="healthOrchra()">Orchra Cluster Health</button>
            <div id="output">System ready. Run automated health scans or fire explicit curl commands.</div>
        </div>

        <div class="actions">
            <h2>📜 Execution History Log - Baseline</h2>
            <table>
                <thead>
                    <tr>
                        <th>UE ID</th>
                        <th>Status</th>
                        <th>Latency (HIT)</th>
                        <th>Source Slice</th>
                        <th>Target Slice</th>
                        <th>Timestamp</th>
                    </tr>
                </thead>
                <tbody id="historyBody"></tbody>
            </table>
        </div>

        <div class="actions">
            <h2>📜 Execution History Log - Orchra</h2>
            <table>
                <thead>
                    <tr>
                        <th>UE ID</th>
                        <th>Status</th>
                        <th>Latency (HIT)</th>
                        <th>Source Slice</th>
                        <th>Target Slice</th>
                        <th>Timestamp</th>
                    </tr>
                </thead>
                <tbody id="historyBodyOrchra"></tbody>
            </table>
        </div>
    </div>
    
    <script>
        function updateStatusElement(elementId, metricId, statusData) {
            const statusEl = document.getElementById(elementId);
            const metricEl = document.getElementById(metricId);
            if (!statusEl) return;

            if (statusData && (statusData.status === "running" || statusData.status === "healthy" || statusData.status === "online")) {
                statusEl.className = "status running";
                statusEl.textContent = "● " + statusData.status.toUpperCase();
            } else {
                statusEl.className = "status error";
                statusEl.textContent = "● " + ((statusData && statusData.status) ? statusData.status : "ERROR").toUpperCase();
            }
            if (metricEl && statusData && statusData.metric !== undefined) {
                metricEl.textContent = statusData.metric;
            }
        }

        async function triggerMosaicMigration() {
            const out = document.getElementById('output');
            try {
                const response = await fetch('/trigger-mosaic-migration', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        ue_id: "imsi-208950000000035",
                        current_slice: "EMBB",
                        target_slice: "URLLC",
                        slice_baseurl: "http://oai-amf.base-chart.svc.cluster.local:8080"
                    })
                });
                const data = await response.json();
                out.textContent = "✅ Action Route Acknowledged. History logs updating.";
                await updateMetrics();
            } catch (error) {
                out.textContent = '❌ Mosaic Migration payload breakdown: ' + error.message;
            }
        }

        async function triggerOrchraMigration() {
            const out = document.getElementById('output');
            try {
                const response = await fetch('/trigger-orchra-migration', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        ue_id: "imsi-208950000000035",
                        current_slice: "EMBB",
                        target_slice: "URLLC",
                        slice_baseurl: "http://oai-amf.oai-orchra.svc.cluster.local:8080"
                    })
                });
                const data = await response.json();
                out.textContent = "✅ Action Route B Acknowledged. History logs updating.";
                await updateMetrics();
            } catch (error) {
                out.textContent = '❌ Orchra Migration payload breakdown: ' + error.message;
            }
        } 

        async function healthBaseline() {
            const output = document.getElementById('output');
            try {
                const response = await fetch('/example');
                const data = await response.json();
                output.textContent = '✅ Cache Line Diagnostics (Baseline):\\n' + JSON.stringify(data, null, 2);
            } catch (error) {
                output.textContent = '❌ Verification error: ' + error.message;
            }
        }
        
        async function healthOrchra() {
            const output = document.getElementById('output');
            try {
                const response = await fetch('/health');
                const data = await response.json();
                output.textContent = '✅ Health Matrix Diagnostics (Orchra):\\n' + JSON.stringify(data, null, 2);
                await updateMetrics();
            } catch (error) {
                output.textContent = '❌ Systems verification timeout';
            }
        }

        async function updateMetrics() {
            try {
                const response = await fetch('/stats');
                if (!response.ok) return;
                const data = await response.json();

                if (!data || !data.systems) return;
        
                // 1. Core Card Updates
                updateStatusElement("coreStatus", "coreMetric", data.systems.core_baseline);
                updateStatusElement("redisStatus", "redisMetric", data.systems.core_orchra); 
                updateStatusElement("ricStatus", "ricMetric", data.systems.ric);
                updateStatusElement("orchStatus", "orchMetric", data.systems.orchestrator);

                // 2. Global Latencies
                document.getElementById('hitVal').textContent = data.latest_mosaic_hit_ms || "0.00";
                document.getElementById('hitValOrchra').textContent = data.latest_orchra_hit_ms || "0.00";
                document.getElementById('currentTime').textContent = "Last Sync Boundary: " + data.timestamp;

                // 3. Baseline Elements Mapping
                const cb = data.systems.core_baseline || {};
                document.getElementById('coreNamespace').textContent = `Namespace: ${cb.namespace || '-'}`;
                document.getElementById('amfHost').textContent = `AMF: ${cb.amf_host || '-'}`;
                document.getElementById('smfHost').textContent = `SMF: ${cb.smf_host || '-'}`;
                document.getElementById('upfHost').textContent = `UPF: ${cb.upf_host || '-'}`;
                document.getElementById('mysqlHost').textContent = `MySQL: ${cb.mysql_host || '-'}`;
                document.getElementById('ausfHost').textContent = `AUSF: ${cb.ausf_host || '-'}`;
                document.getElementById('udmHost').textContent = `UDM: ${cb.udm_host || '-'}`;
                document.getElementById('udrHost').textContent = `UDR: ${cb.udr_host || '-'}`;

                // 4. Orchra Elements Mapping
                const co = data.systems.core_orchra || {};
                document.getElementById('orchraNamespace').textContent = `Namespace: ${co.namespace || '-'}`;
                document.getElementById('orchraAmfHost').textContent = `AMF: ${co.amf_host || '-'}`;
                document.getElementById('orchraSmfHost').textContent = `SMF: ${co.smf_host || '-'}`;
                document.getElementById('orchraUpfHost').textContent = `UPF: ${co.upf_host || '-'}`;
                document.getElementById('orchraMysqlHost').textContent = `MySQL: ${co.mysql_host || '-'}`;
                document.getElementById('orchraAusfHost').textContent = `AUSF: ${co.ausf_host || '-'}`;
                document.getElementById('orchraUdmHost').textContent = `UDM: ${co.udm_host || '-'}`;
                document.getElementById('orchraUdrHost').textContent = `UDR: ${co.udr_host || '-'}`;

                // 5. Orchestrator Settings Mapping
                const orch = data.systems.orchestrator || {};
                document.getElementById('orchNamespace').textContent = `Namespace: ${orch.namespace || '-'}`;
                document.getElementById('orchRedisHost').textContent = `Redis: ${orch.redis_host || '-'}`;

                // 6. Append Logs to History Log - Baseline
                const historyBody = document.getElementById('historyBody');
                historyBody.innerHTML = '';
                if(data.history_mosaic && data.history_mosaic.length > 0) {
                    data.history_mosaic.forEach(row => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><b>${row.ue_id}</b></td>
                            <td><span class="status running" style="background:#FF9800;">● STATELESS</span></td>
                            <td>${row.latency_ms} ms</td>
                            <td>${row.current_slice || 'EMBB'}</td>
                            <td>${row.target_slice}</td>
                            <td>${row.timestamp}</td>
                        `;
                        historyBody.appendChild(tr);
                    });
                } else {
                    historyBody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#999;">No stateless migrations routed yet.</td></tr>';
                }

                // 7. Append Logs to History Log - Orchra
                const historyBodyOrchra = document.getElementById('historyBodyOrchra');
                historyBodyOrchra.innerHTML = '';
                if(data.history_orchra && data.history_orchra.length > 0) {
                    data.history_orchra.forEach(row => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><b>${row.ue_id}</b></td>
                            <td><span class="status running">● ACTIVE</span></td>
                            <td>${row.latency_ms} ms</td>
                            <td>${row.current_slice || 'EMBB'}</td>
                            <td>${row.target_slice}</td>
                            <td>${row.timestamp}</td>
                        `;
                        historyBodyOrchra.appendChild(tr);
                    });
                } else {
                     historyBodyOrchra.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#999;">No stateful migrations routed yet.</td></tr>';
                }

            } catch (error) {
                console.error("Dashboard parser execution fault: ", error);
            }
        }

        setInterval(updateMetrics, 2000);
        window.onload = () => { updateMetrics(); };
    </script>
</body>
</html>
"""

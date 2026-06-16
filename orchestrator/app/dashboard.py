# dashboard.py

HTML_DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>5G Core Cloud-Native Orchestration Plane</title>
    <style>
        :root {
            --bg-color: #0d1117;
            --card-bg: #161b22;
            --border-color: #30363d;
            --text-main: #c9d1d9;
            --text-muted: #8b949e;
            --accent-blue: #58a6ff;
            --success: #2ea44f;
            --danger: #da3633;
            --text-bright: #ffffff;
        }

        /* Force details text inside metadata and components boxes to be bold and shining white */
        .text-bright, .meta-item span:not(.meta-label) {
            color: var(--text-bright) !important;
            font-weight: 600;
            text-shadow: 0 0 2px rgba(255, 255, 255, 0.3); /* Subtle brightness glow */
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 25px;
            font-size: 14px;
            line-height: 1.6;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            font-size: 24px;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
            font-weight: 800;
        }
        h2 {
            font-size: 18px;
            margin: 0 0 15px 0;
            color: var(--accent-blue);
            font-weight: 700;
        }
        
        /* Layout Grid System */
        .grid-3-col {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-bottom: 25px;
        }
        .grid-2-col {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            margin-bottom: 25px;
        }
        
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 20px;
        }
        
        /* Metadata definitions */
        .meta-item {
            font-size: 12px;
            margin-bottom: 8px;
            font-family: monospace;
        }
        .meta-label {
            color: var(--text-muted);
        }
        
        /* Execution History Enhancements */
        .log-header-actions {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 12px;
        }
        
        /* Form & Trigger Buttons styling */
        .inline-trigger-form {
            display: flex;
            gap: 12px;
            align-items: center;
        }
        input, select, button {
            background: #21262d;
            border: 1px solid var(--border-color);
            color: var(--text-main);
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 14px;
        }
        button {
            background: var(--accent-blue);
            color: #fff;
            border: none;
            cursor: pointer;
            font-weight: 600;
            transition: background 0.2s;
        }
        button:hover {
            opacity: 0.9;
        }
        button.btn-orchra {
            background: var(--success);
        }

        /* Metrics Summaries Text */
        .latency-summary {
            font-size: 15px; /* Increased from 13px */
            margin-bottom: 15px;
            color: var(--text-muted);
        }

        /* Tables layout */
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 15px;
            text-align: left;
        }
        th, td {
            padding: 8px 10px;
            border-bottom: 1px solid var(--border-color);
        }
        th {
            color: var(--text-muted);
            font-weight: 500;
        }
        
        /* Enlarged Diagnostics typography */
        .health-indicator-large {
            font-size: 1.6rem;
            font-weight: 900;
            margin: 15px 0;
            font-family: monospace;
        }
        .details-box {
            font-size: 14px; /* Increased from 12px */
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
            color: var(--text-bright);
            line-height: 1.7;
            background: rgba(0, 0, 0, 0.2);
            padding: 15px;
            border-radius: 6px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .text-success { color: #56d364; }
        .text-danger { color: #f85149; }
        .text-muted { color: var(--text-muted); }
        
        #console-output {
            background: #040d16;
            color: #39ff14;
            padding: 16px;
            font-family: monospace;
            border-radius: 6px;
            max-height: 220px;
            overflow-y: auto;
            font-size: 14px;
            border: 1px solid var(--border-color);
            line-height: 1.5;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📡 5G Slice iMigration Control </h1>
        <div style="font-size:12px; margin-bottom:20px; color:var(--text-muted);" id="currentTime">Sync Tracking Boundary: Loading...</div>

        <div class="grid-3-col">
            <div class="card">
                <h2>📦 Baseline Stack Architecture</h2>
                <div class="meta-item"><span class="meta-label">Namespace:</span> <span id="coreNamespace">-</span></div>
                <div class="meta-item"><span class="meta-label">AMF Target SBI:</span> <span id="amfHost">-</span></div>
                <div class="meta-item"><span class="meta-label">SMF Target SBI:</span> <span id="smfHost">-</span></div>
                <div class="meta-item"><span class="meta-label">UPF N4 Link:</span> <span id="upfHost">-</span></div>
                <div class="meta-item"><span class="meta-label">Data Registry:</span> <span id="mysqlHost">-</span></div>
                <div class="meta-item"><span class="meta-label">Pod Status Ratio:</span> <span id="coreMetric" style="font-weight:bold;">-</span></div>
            </div>

            <div class="card">
                <h2>🚀 Orchra Production Stack</h2>
                <div class="meta-item"><span class="meta-label">Namespace:</span> <span id="orchraNamespace">-</span></div>
                <div class="meta-item"><span class="meta-label">AMF Target SBI:</span> <span id="orchraAmfHost">-</span></div>
                <div class="meta-item"><span class="meta-label">SMF Target SBI:</span> <span id="orchraSmfHost">-</span></div>
                <div class="meta-item"><span class="meta-label">UPF N4 Link:</span> <span id="orchraUpfHost">-</span></div>
                <div class="meta-item"><span class="meta-label">Data Registry:</span> <span id="orchraMysqlHost">-</span></div>
                <div class="meta-item"><span class="meta-label">Pod Status Ratio:</span> <span id="redisMetric" style="font-weight:bold;">-</span></div>
            </div>

            <div class="card">
                <h2>⚙️ Intelligent Controller Matrix</h2>
                <div class="meta-item"><span class="meta-label">RIC Namespace:</span> <span id="ricNamespace">5g-ric</span></div>
                <div class="meta-item"><span class="meta-label">RIC Pod Ratio:</span> <span id="ricMetric" style="font-weight:bold;">-</span></div>
                <div class="meta-item"><span class="meta-label">Orchra Engine:</span> <span id="orchNamespace">-</span></div>
                <div class="meta-item"><span class="meta-label">Redis Distributed Node:</span> <span id="orchRedisHost">-</span></div>
                <div class="meta-item"><span class="meta-label">Orchra Orchestrator Status:</span> <span id="orchMetric" style="font-weight:bold;">-</span></div>
            </div>
        </div>

        <div class="card" style="margin-bottom: 20px;">
            <div class="log-header-actions">
                <h2>📜 Execution History Log - Baseline (Mosaic)</h2>
                <div class="inline-trigger-form">
                    <input type="text" id="mosaic_ue_id" value="imsi-208950000000035" placeholder="UE IMSI ID">
                    <select id="mosaic_target">
                        <option value="URLLC">Target: URLLC</option>
                        <option value="EMBB">Target: EMBB</option>
                    </select>
                    <button onclick="executeMigration('mosaic')">Run Baseline Mosaic Migration</button>
                </div>
            </div>
            <div style="font-size: 13px; margin-bottom: 10px; color: var(--text-muted)">
                Last Handshake Latency: <span id="hitVal" style="color:var(--accent-blue); font-weight:bold;">0.00</span> ms
            </div>
            <table>
                <thead>
                    <tr>
                        <th>UE ID</th>
                        <th>Topology Type</th>
                        <th>Switch Delay Latency</th>
                        <th>Source Profile</th>
                        <th>Target Profile</th>
                        <th>Timestamp Execution</th>
                    </tr>
                </thead>
                <tbody id="historyBody"></tbody>
            </table>
        </div>

        <div class="card" style="margin-bottom: 20px;">
            <div class="log-header-actions">
                <h2>📜 Execution History Log - Orchra (Stateful)</h2>
                <div class="inline-trigger-form">
                    <input type="text" id="orchra_ue_id" value="imsi-208950000000035" placeholder="UE IMSI ID">
                    <select id="orchra_target">
                        <option value="URLLC">Target: URLLC</option>
                        <option value="EMBB">Target: EMBB</option>
                    </select>
                    <button class="btn-orchra" onclick="executeMigration('orchra')">Run Orchra Migration</button>
                </div>
            </div>
            <div style="font-size: 13px; margin-bottom: 10px; color: var(--text-muted)">
                Last Handshake Latency: <span id="hitValOrchra" style="color:var(--success); font-weight:bold;">0.00</span> ms
            </div>
            <table>
                <thead>
                    <tr>
                        <th>UE ID</th>
                        <th>Topology Type</th>
                        <th>Switch Delay Latency</th>
                        <th>Source Profile</th>
                        <th>Target Profile</th>
                        <th>Timestamp Execution</th>
                    </tr>
                </thead>
                <tbody id="historyBodyOrchra"></tbody>
            </table>
        </div>

        <div class="grid-2-col">
            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h2>🔍 Baseline Cluster Diagnostics</h2>
                    <button onclick="checkClusterHealth('baseline')" style="font-size:11px; padding:4px 8px;">Scan Now</button>
                </div>
                <div id="baseline-health-indicator" class="health-indicator-large text-muted">● UNKNOWN STATE</div>
                <div id="baseline-details" style="font-size:12px; font-family:monospace; color:var(--text-muted);">No logs polled. Hit 'Scan Now' to stream pod properties.</div>
            </div>

            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h2>🔍 Orchra Production Diagnostics</h2>
                    <button onclick="checkClusterHealth('orchra')" class="btn-orchra" style="font-size:11px; padding:4px 8px;">Scan Now</button>
                </div>
                <div id="orchra-health-indicator" class="health-indicator-large text-muted">● UNKNOWN STATE</div>
                <div id="orchra-details" style="font-size:12px; font-family:monospace; color:var(--text-muted);">No logs polled. Hit 'Scan Now' to stream pod properties.</div>
            </div>
        </div>

        <div class="card">
            <h2>🖥️ Direct Broker Event Logs</h2>
            <div id="console-output">System initialized. Awaiting orchestration telemetry data triggers...</div>
        </div>

    </div>

    <script>
        // Orchestration Router for Migration Form Execution
        async function executeMigration(type) {
            const ue_id = document.getElementById(type + '_ue_id').value;
            const target_slice = document.getElementById(type + '_target').value;
            const current_slice = target_slice === "URLLC" ? "EMBB" : "URLLC";
            const endpoint = type === 'mosaic' ? '/trigger-mosaic-migration' : '/trigger-orchra-migration';
            
            const consoleBox = document.getElementById('console-output');
            consoleBox.innerHTML += `<br>[${new Date().toLocaleTimeString()}] Requesting ${type.toUpperCase()} context swap for ${ue_id}...`;

            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        ue_id: ue_id,
                        current_slice: current_slice,
                        target_slice: target_slice,
                        slice_baseurl: "internal-broker-auto"
                    })
                });
                const data = await response.json();
                consoleBox.innerHTML += `<br><span style="color:#58a6ff;">[Response] Status=${response.status} Payload=${JSON.stringify(data)}</span>`;
                consoleBox.scrollTop = consoleBox.scrollHeight;
                updateMetrics();
            } catch (err) {
                consoleBox.innerHTML += `<br><span style="color:var(--danger);">[Network Error] ${err.message}</span>`;
            }
        }

        // Expanded Cluster Health Scanners
        async function checkClusterHealth(cluster) {
            const indicatorEl = document.getElementById(cluster + '-health-indicator');
            const detailsEl = document.getElementById(cluster + '-details');
            
            try {
                const response = await fetch('/health?cluster=' + cluster);
                const data = await response.json();
                
                const statusStr = data.status ? data.status.toUpperCase() : "DEGRADED";
                indicatorEl.textContent = "● " + statusStr;
                
                if (statusStr === "HEALTHY") {
                    indicatorEl.className = "health-indicator-large text-success";
                } else {
                    indicatorEl.className = "health-indicator-large text-danger";
                }
                
                detailsEl.innerHTML = `
                    Namespace Scope: ${data.namespace || 'N/A'}<br>
                    Component Map: ${data.components || '0/0 pods active'}<br>
                    Active Container Registry Pod Matrix:<br>
                    ${data.pods ? data.pods.map(p => `• ${p.name} ➔ [${p.phase}] (Restarts: ${p.restarts || 0})`).join('<br>') : 'No pods matched'}
                `;
            } catch(err) {
                indicatorEl.textContent = "● ERROR";
                indicatorEl.className = "health-indicator-large text-danger";
                detailsEl.textContent = "Failed to list cluster attributes: " + err.message;
            }
        }

        // Stats Polling Loop for Cards & Logs Matrices
        async function updateMetrics() {
            try {
                const response = await fetch('/stats');
                if (!response.ok) return;
                const data = await response.json();
                if (!data || !data.systems) return;

                // Elements Core Mapping
                document.getElementById('hitVal').textContent = data.latest_mosaic_hit_ms || "0.00";
                document.getElementById('hitValOrchra').textContent = data.latest_orchra_hit_ms || "0.00";
                document.getElementById('currentTime').textContent = "Sync Tracking Boundary: " + data.timestamp;

                const cb = data.systems.core_baseline || {};
                document.getElementById('coreNamespace').textContent = cb.namespace || '-';
                document.getElementById('amfHost').textContent = cb.amf_host || '-';
                document.getElementById('smfHost').textContent = cb.smf_host || '-';
                document.getElementById('upfHost').textContent = cb.upf_host || '-';
                document.getElementById('mysqlHost').textContent = cb.mysql_host || '-';
                document.getElementById('coreMetric').textContent = cb.metric || '-';

                const co = data.systems.core_orchra || {};
                document.getElementById('orchraNamespace').textContent = co.namespace || '-';
                document.getElementById('orchraAmfHost').textContent = co.amf_host || '-';
                document.getElementById('orchraSmfHost').textContent = co.smf_host || '-';
                document.getElementById('orchraUpfHost').textContent = co.upf_host || '-';
                document.getElementById('orchraMysqlHost').textContent = co.mysql_host || '-';
                document.getElementById('redisMetric').textContent = co.metric || '-';

                const ric = data.systems.ric || {};
                document.getElementById('ricMetric').textContent = ric.metric || '-';

                const orch = data.systems.orchestrator || {};
                document.getElementById('orchNamespace').textContent = orch.namespace || '-';
                document.getElementById('orchRedisHost').textContent = orch.redis_host || '-';
                document.getElementById('orchMetric').textContent = orch.metric || '-';

                // Table Loop Rendering: Mosaic
                const historyBody = document.getElementById('historyBody');
                historyBody.innerHTML = '';
                if(data.history_mosaic && data.history_mosaic.length > 0) {
                    data.history_mosaic.forEach(row => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><b>${row.ue_id}</b></td>
                            <td><span style="background:#FF9800; padding:2px 6px; border-radius:3px; color:#000; font-weight:bold; font-size:11px;">● STATELESS</span></td>
                            <td>${row.latency_ms} ms</td>
                            <td>${row.current_slice || 'EMBB'}</td>
                            <td>${row.target_slice}</td>
                            <td>${row.timestamp}</td>
                        `;
                        historyBody.appendChild(tr);
                    });
                } else {
                    historyBody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">No stateless migrations routed yet.</td></tr>';
                }

                // Table Loop Rendering: Orchra
                const historyBodyOrchra = document.getElementById('historyBodyOrchra');
                historyBodyOrchra.innerHTML = '';
                if(data.history_orchra && data.history_orchra.length > 0) {
                    data.history_orchra.forEach(row => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><b>${row.ue_id}</b></td>
                            <td><span style="background:var(--success); padding:2px 6px; border-radius:3px; color:#fff; font-weight:bold; font-size:11px;">● ACTIVE</span></td>
                            <td>${row.latency_ms} ms</td>
                            <td>${row.current_slice || 'EMBB'}</td>
                            <td>${row.target_slice}</td>
                            <td>${row.timestamp}</td>
                        `;
                        historyBodyOrchra.appendChild(tr);
                    });
                } else {
                    historyBodyOrchra.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">No stateful migrations routed yet.</td></tr>';
                }
            } catch (error) {
                console.error("Dashboard metrics parsing exception: ", error);
            }
        }

        // Initialize background timers
        setInterval(updateMetrics, 2500);
        window.onload = function() {
            updateMetrics();
            checkClusterHealth('baseline');
            checkClusterHealth('orchra');
        };
    </script>
</body>
</html>
"""

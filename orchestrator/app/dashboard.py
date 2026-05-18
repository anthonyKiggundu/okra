def render_dashboard() -> str:
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>5G Network Slicing Dashboard</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 2rem;
                background: #f5f7fb;
                color: #222;
            }
            .card {
                background: white;
                padding: 1rem;
                border-radius: 12px;
                margin-bottom: 1rem;
                box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            }
            button {
                padding: 10px 16px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                background: #4f46e5;
                color: white;
                margin-right: 8px;
            }
            pre {
                background: #111827;
                color: #d1fae5;
                padding: 1rem;
                border-radius: 8px;
                overflow: auto;
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                padding: 10px;
                border-bottom: 1px solid #ddd;
                text-align: left;
            }
        </style>
    </head>
    <body>
        <h1>5G Network Slicing Orchestration Dashboard</h1>

        <div class="card">
            <button onclick="checkHealth()">Check Health</button>
            <button onclick="testRedis()">Test Redis</button>
            <button onclick="triggerMigration()">Trigger Migration</button>
        </div>

        <div class="card">
            <h2>Latest HIT</h2>
            <div><strong id="hitVal">0.00</strong> ms</div>
        </div>

        <div class="card">
            <h2>Recent Migration History</h2>
            <table>
                <thead>
                    <tr>
                        <th>UE ID</th>
                        <th>Status</th>
                        <th>HIT (ms)</th>
                        <th>Target Slice</th>
                        <th>Time</th>
                    </tr>
                </thead>
                <tbody id="historyBody"></tbody>
            </table>
        </div>

        <div class="card">
            <h2>Output</h2>
            <pre id="output"></pre>
        </div>

        <script>
            async function checkHealth() {
                const output = document.getElementById('output');
                const res = await fetch('/health');
                const data = await res.json();
                output.textContent = JSON.stringify(data, null, 2);
            }

            async function testRedis() {
                const output = document.getElementById('output');
                const res = await fetch('/example');
                const data = await res.json();
                output.textContent = JSON.stringify(data, null, 2);
            }

            async function triggerMigration() {
                const output = document.getElementById('output');
                const res = await fetch('/trigger-migration', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        ue_id: 'UE-' + Math.floor(Math.random() * 1000),
                        current_slice: 'EMBB',
                        target_slice: 'URLLC'
                    })
                });
                const data = await res.json();
                output.textContent = JSON.stringify(data, null, 2);
                await updateStats();
            }

            async function updateStats() {
                const res = await fetch('/stats');
                const data = await res.json();

                document.getElementById('hitVal').textContent = data.latest_hit_ms.toFixed(2);

                const tbody = document.getElementById('historyBody');
                tbody.innerHTML = '';

                data.history.forEach(item => {
                    const row = tbody.insertRow();
                    row.innerHTML = `
                        <td>${item.ue_id}</td>
                        <td>${item.status}</td>
                        <td>${item.hit === null ? 'N/A' : item.hit.toFixed(2)}</td>
                        <td>${item.target_slice}</td>
                        <td>${item.timestamp}</td>
                    `;
                });
            }

            window.onload = async () => {
                await checkHealth();
                await updateStats();
                setInterval(updateStats, 2000);
            };
        </script>
    </body>
    </html>
    """

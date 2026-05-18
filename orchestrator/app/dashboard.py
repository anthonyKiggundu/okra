from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import aiohttp
import os

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>5G Network Slicing Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #1e1e1e; color: #fff; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { text-align: center; padding: 20px; background: #2d2d2d; border-radius: 8px; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 20px; }
            .card { background: #2d2d2d; padding: 20px; border-radius: 8px; border-left: 4px solid #4CAF50; }
            .card.core { border-left-color: #2196F3; }
            .card.ran { border-left-color: #FF9800; }
            .card.ric { border-left-color: #9C27B0; }
            .card.orchestrator { border-left-color: #4CAF50; }
            .status { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; margin-top: 10px; }
            .status.running { background: #4CAF50; }
            .status.pending { background: #FF9800; }
            .status.error { background: #f44336; }
            h1 { margin: 0; color: #4CAF50; }
            h2 { margin: 10px 0; font-size: 18px; }
            p { margin: 5px 0; color: #aaa; }
            .metric { font-size: 24px; font-weight: bold; color: #4CAF50; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🌐 5G Network Slicing Orchestration Platform</h1>
                <p>Real-time monitoring and management</p>
            </div>
            
            <div class="grid">
                <div class="card core">
                    <h2>📡 5G Core Network</h2>
                    <div class="status running">● RUNNING</div>
                    <p>AMF: oai-amf.5g-core.svc</p>
                    <p>SMF: oai-smf.5g-core.svc</p>
                    <p>UPF: oai-upf.5g-core.svc</p>
                    <p class="metric">3/3 Components</p>
                </div>
                
                <div class="card ric">
                    <h2>🎛️ RAN Intelligent Controller</h2>
                    <div class="status running">● RUNNING</div>
                    <p>FlexRIC: flexric.5g-ric.svc</p>
                    <p>Monitoring RAN metrics</p>
                    <p class="metric">Active</p>
                </div>
                
                <div class="card orchestrator">
                    <h2>🎯 Slice Orchestrator</h2>
                    <div class="status running">● RUNNING</div>
                    <p>API: slice-orchestrator.5g-orchestrator.svc</p>
                    <p>Redis: redis-master.5g-core.svc</p>
                    <p class="metric">Online</p>
                </div>
                
                <div class="card">
                    <h2>💾 Context Storage</h2>
                    <div class="status running">● RUNNING</div>
                    <p>Redis Master: redis-master.5g-core.svc:6379</p>
                    <p>Type: In-Memory Store</p>
                    <p class="metric">Connected</p>
                </div>
            </div>
            
            <div style="margin-top: 30px; padding: 20px; background: #2d2d2d; border-radius: 8px;">
                <h2>📊 Quick Actions</h2>
                <button onclick="testRedis()" style="padding: 10px 20px; margin: 5px; background: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer;">Test Redis</button>
                <button onclick="checkHealth()" style="padding: 10px 20px; margin: 5px; background: #2196F3; color: white; border: none; border-radius: 4px; cursor: pointer;">Check Health</button>
                <button onclick="viewLogs()" style="padding: 10px 20px; margin: 5px; background: #9C27B0; color: white; border: none; border-radius: 4px; cursor: pointer;">View Logs</button>
                <div id="output" style="margin-top: 20px; padding: 15px; background: #1e1e1e; border-radius: 4px; font-family: monospace; white-space: pre-wrap;"></div>
            </div>
        </div>
        
        <script>
            async function testRedis() {
                document.getElementById('output').textContent = 'Testing Redis...';
                const response = await fetch('/example');
                const data = await response.json();
                document.getElementById('output').textContent = JSON.stringify(data, null, 2);
            }
            
            async function checkHealth() {
                document.getElementById('output').textContent = 'Checking health...';
                const response = await fetch('/health');
                const data = await response.json();
                document.getElementById('output').textContent = JSON.stringify(data, null, 2);
            }
            
            function viewLogs() {
                document.getElementById('output').textContent = 'Logs feature coming soon...\\nUse: kubectl logs -n 5g-orchestrator -l app=slice-orchestrator';
            }
        </script>
    </body>
    </html>
    """

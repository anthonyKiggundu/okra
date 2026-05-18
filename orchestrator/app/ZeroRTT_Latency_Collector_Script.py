import requests
import time
import csv
from datetime import datetime

# --- Configuration ---
SOURCE_SMF = "http://10.0.0.1:8080"
TARGET_SMF = "http://10.0.0.2:8080"
SUPI = "208930000000001"
PDU_ID = 1
ITERATIONS = 50  # Number of tests for statistical significance
OUTPUT_FILE = "slicing_overhead_results.csv"

def run_benchmarking():
    results = []
    print(f"🚀 Starting Zero-RTT Benchmarking ({ITERATIONS} iterations)...")

    for i in range(ITERATIONS):
        try:
            # 1. Measure Pause Latency (Source)
            t0 = time.perf_counter()
            requests.post(f"{SOURCE_SMF}/internal/pdu-sessions/{SUPI}/{PDU_ID}/pause")
            t_pause = (time.perf_counter() - t0) * 1000

            # 2. Export Context (Source)
            t0 = time.perf_counter()
            resp = requests.get(f"{SOURCE_SMF}/internal/pdu-sessions/{SUPI}/{PDU_ID}")
            context = resp.json()
            t_export = (time.perf_counter() - t0) * 1000

            # 3. Import Context (Target)
            t0 = time.perf_counter()
            requests.post(f"{TARGET_SMF}/internal/pdu-sessions/{SUPI}/{PDU_ID}", json=context)
            t_import = (time.perf_counter() - t0) * 1000

            # 4. MEASURE BIND OVERHEAD (Target Systemic Overhead)
            # This is the "Deterministic" part of your paper
            t0 = time.perf_counter()
            requests.post(f"{TARGET_SMF}/internal/pdu-sessions/{SUPI}/{PDU_ID}/bind")
            t_bind = (time.perf_counter() - t0) * 1000

            # 5. Resume Traffic (Target)
            t0 = time.perf_counter()
            requests.post(f"{TARGET_SMF}/internal/pdu-sessions/{SUPI}/{PDU_ID}/resume")
            t_resume = (time.perf_counter() - t0) * 1000

            total_overhead = t_pause + t_export + t_import + t_bind + t_resume
            
            results.append([i, t_pause, t_export, t_import, t_bind, t_resume, total_overhead])
            print(f"Iteration {i}: Bind={t_bind:.3f}ms | Total={total_overhead:.3f}ms")

            # Cleanup for next iteration: Release target and unpause source (if re-testing same UE)
            requests.delete(f"{TARGET_SMF}/internal/pdu-sessions/{SUPI}/{PDU_ID}")
            
        except Exception as e:
            print(f"❌ Error in iteration {i}: {e}")

    # --- Save to CSV ---
    header = ['Iteration', 'Pause_ms', 'Export_ms', 'Import_ms', 'Bind_ms', 'Resume_ms', 'Total_ms']
    with open(OUTPUT_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(results)
    
    print(f"✅ Results saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    run_benchmarking()

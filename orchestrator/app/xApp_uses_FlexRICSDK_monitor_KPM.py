import xapp_sdk
import time
import os

def monitor_slice_migration():
    # 1. Initialize FlexRIC SDK
    xapp = xapp_sdk.XApp()
    
    print("🚀 Mosaic5G xApp: Monitoring Zero-RTT Slice Migration...")

    while True:
        # 2. Fetch KPM (Key Performance Metrics) from gNB
        # This includes PDCP SDU throughput and RLC buffer stats
        kpm_reports = xapp.get_kpm_stats()
        
        for report in kpm_reports:
            ue_id = report.ue_id
            # Monitor Downlink Throughput (bytes/sec)
            dl_tput = report.drb_stats.dl_throughput 
            # Monitor RLC Buffer Occupancy (indicating jitter/congestion)
            rlc_buffer = report.drb_stats.rlc_buffer_occ 

            # 3. Detect the "Switch" 
            # In your paper, correlate this timestamp with the SMF 'Bind' timestamp
            timestamp = time.time_ns()
            
            if dl_tput > 0:
                print(f"[Metric] UE: {ue_id} | TS: {timestamp} | DL-Tput: {dl_tput/1e6:.2f} Mbps | RLC-Buf: {rlc_buffer} bytes")

            # 4. Log to CSV for your Table 1
            with open("mosaic5g_metrics.csv", "a") as f:
                f.write(f"{timestamp},{ue_id},{dl_tput},{rlc_buffer}\n")

        time.sleep(0.01) # 10ms sampling rate for high-granularity migration data

if __name__ == "__main__":
    try:
        monitor_slice_migration()
    except KeyboardInterrupt:
        print("Stopping xApp...")

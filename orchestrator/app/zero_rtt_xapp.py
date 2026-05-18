'''
1.  FlexRIC Subscription (UE Isolation)

To measure the "Zero-RTT" effect without noise from other traffic, you need to 
subscribe specifically to the KPM (Key Performance Metrics) of the UE being migrated.
In FlexRIC, you use a Control Message or a specific Subscription Request with a ue_list filter. 
Here is the Python logic for your xApp to isolate your test UE (identified by its RNTI or TMSI).

2.  Benchmarking Logic: Correlating SMF and RAN

To prove "Zero-RTT" in your paper, you need to sync the clocks of your SMF and your FlexRIC xApp.
    Orchestrator Trigger: When the orchestrator sends POST /bind, it logs T_bind_start.
    SMF Logic: SMF logs T_n4_sent and T_n2_sent.
    FlexRIC xApp: The xApp observes a "bump" in the DRB.RlcSduDelayDl metric.

The Total Interruption Time in your results table is:

HIT=Tfirst_packet_target_UPF − Tlast_packet_source_UPF

If your Bind command and N2 Update happen within that 2-5ms window, the FlexRIC 
throughput graph will show a seamless handover with zero "zero-throughput" intervals.
We need a shell script (get_ue_rnti.sh) that pulls the RNTI automatically from the AMF logs so the 
xApp can subscribe to the correct UE without manual input

3.  Integrated FlexRIC xApp (zero_rtt_xapp.py)
This Python script calls the shell script (get_ue_rnti.sh) internally to automate the subscription.

4.  Final Verification of the Zero-RTT Pipeline

To get the metrics for your table, you will run the orchestrator and the xApp simultaneously:

    Terminal 1 (xApp):
    python3 zero_rtt_xapp.py 208930000000001

    Terminal 2 (Orchestrator):
    python3 latency_collector.py (The script I provided earlier).

📝 Interpretation of Results for the Paper:
Event	Timestamp (Orchestrator)	Timestamp (xApp)	Expected Behavior
Paue	t_pause_start	t_ran_buffer_rise	Throughput drops to 0; RLC buffer rises.
Bind	t_bind_start	t_ran_config_change	Control plane re-anchors (Systemic Overhead).
Resume	t_resume_done	t_ran_tput_restore	Throughput returns; RLC buffer flushes.

The "Handover Interruption Time" (HIT) is exactly:
(tran_tput_restore − tran_buffer_rise)/1,000,000 ms

By showing that this HIT is nearly identical to your Bind latency, you prove that 
the RAN doesn't add any significant stochastic delay—making the entire switch deterministic.
'''

# zero_rtt_xapp.py

import xapp_sdk
import subprocess
import time
import sys

def fetch_rnti(supi):
    """Calls the shell script to get the current RNTI for the SUPI."""
    try:
        result = subprocess.check_output(['./get_ue_rnti.sh', supi], stderr=subprocess.STDOUT)
        rnti_str = result.decode('utf-8').strip()
        if not rnti_str:
            return None
        # Convert hex string (0x...) or decimal to integer
        return int(rnti_str, 16) if '0x' in rnti_str else int(rnti_str)
    except Exception as e:
        print(f"❌ Error fetching RNTI: {e}")
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 zero_rtt_xapp.py <SUPI>")
        return

    target_supi = sys.argv[1]
    xapp = xapp_sdk.XApp()

    print(f"🔍 Searching for RNTI for SUPI: {target_supi}...")

    # Wait until UE attaches and RNTI is available
    target_rnti = None
    while target_rnti is None:
        target_rnti = fetch_rnti(target_supi)
        if target_rnti:
            print(f"✅ Found UE RNTI: {hex(target_rnti)}")
            break
        print("...waiting for UE attachment...")
        time.sleep(2)

    # 3. Flexible KPM Subscription
    # Action ID 1: Throughput | Action ID 2: Latency/Jitter
    sub_req = xapp_sdk.kpm_sub_req_t()
    sub_req.header.ue_id = target_rnti

    # We subscribe to DRB stats to see the user-plane "bump" during migration
    sub_req.action_item.append("DRB.PdcpSduBitRateDl") # Throughput
    sub_req.action_item.append("DRB.RlcSduDelayDl")    # Jitter/Delay

    xapp.subscribe_kpm(sub_req)

    print("📊 Subscription active. Monitoring Zero-RTT transition...")

    # Data Handler
    while True:
        reports = xapp.get_kpm_stats()
        for r in reports:
            if r.ue_id == target_rnti:
                ts = time.time_ns()
                tput = r.drb_stats.dl_throughput
                delay = r.drb_stats.rlc_buffer_occ # Using buffer as proxy for jitter

                print(f"[{ts}] Tput: {tput/1e6:.2f} Mbps | Jitter Proxy: {delay} bytes")

                # Log to CSV for your "Mosaic5G Metrics" table
                with open("migration_bench.csv", "a") as f:
                    f.write(f"{ts},{tput},{delay}\n")

        time.sleep(0.01) # High frequency sampling

if __name__ == "__main__":
    main()

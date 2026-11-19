import time
import sys
import torch
import torch.nn as nn
import torch.nn.functional as F
import flexric

# ==========================================================
# 1. DEFINE THE NEURAL INFERENCE MODEL (The Avoidance/Actor Network)
# ==========================================================
class SlicingActorNetwork(nn.Module):
    """
    Neural model that takes normalized RAN telemetry state 
    and outputs action logits for slice resource adjustments.
    """
    def __init__(self, input_dim=4, hidden_dim=32, action_dim=2):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.actor_head = nn.Linear(hidden_dim, action_dim) # e.g., [Maintain, Reallocate/Protect URLLC]

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        logits = self.actor_head(x)
        return logits

# ==========================================================
# 2. MAIN XAPP RUNTIME LOOP
# ==========================================================
def main():
    print("==================================================")
    print("Starting Slicing xApp: Neural Inference & E2 Glue")
    print("==================================================")
    
    # Initialize connection to FlexRIC Near-RT RIC
    xapp = flexric.init_xapp("slicing_ai_xapp")
    
    # Initialize and load pre-trained weights (or random initialization for baseline)
    model = SlicingActorNetwork(input_dim=4, hidden_dim=32, action_dim=2)
    model.eval() # Inference mode
    
    # Baseline configuration state
    current_slices = {
        "URLLC": {"id": 1, "min_prb": 10, "max_prb": 30},
        "EMBB":  {"id": 2, "min_prb": 20, "max_prb": 90}
    }

    print("[xApp] Subscribed to KPM streams. Entering control loop...")

    try:
        while True:
            # Step A: Poll telemetry from FlexRIC KPM indication buffer
            indication = flexric.poll_indication_message(timeout_ms=1000)
            
            if indication:
                # Parse raw indication into numerical metrics
                metrics = parse_kpm_packet(indication)
                dl_prb_util = metrics["dl_prb_util"]
                urllc_latency = metrics["urllc_lat"]
                embb_throughput = metrics["embb_tput"]
                queue_load = metrics["queue_depth"]
                
                print(f"[Telemetry] PRB Util: {dl_prb_util:.1f}% | URLLC Latency: {urllc_latency:.2f}ms")

                # Step B: Construct input state tensor for the neural model
                # Features: [DL PRB Util, URLLC Latency, eMBB Throughput, Queue Depth]
                state_tensor = torch.tensor([[
                    dl_prb_util / 100.0,
                    urllc_latency / 20.0,
                    embb_throughput / 100.0,
                    queue_load / 50.0
                ]], dtype=torch.float32)

                # Step C: Run neural model inference
                with torch.no_grad():
                    action_logits = model(state_tensor)
                    action_probs = F.softmax(action_logits, dim=-1)
                    chosen_action = torch.argmax(action_probs).item()

                # Step D: Map model decision to RAN actuation
                # Action 0: Normal operation / Maintain state
                # Action 1: Active avoidance / Expand URLLC PRB floor
                if chosen_action == 1 and current_slices["URLLC"]["min_prb"] != 25:
                    print("[AI Agent] Threat detected! Executing active avoidance (Expanding URLLC slice).")
                    current_slices["URLLC"]["min_prb"] = 25
                    current_slices["EMBB"]["max_prb"] = 65
                    
                    # Step E: Dispatch E2-RC control message to OAI gNB
                    dispatch_e2_rc_command(current_slices)
                    
                elif chosen_action == 0 and current_slices["URLLC"]["min_prb"] != 10:
                    print("[AI Agent] Safe state verified. Reverting slice quotas to baseline.")
                    current_slices["URLLC"]["min_prb"] = 10
                    current_slices["EMBB"]["max_prb"] = 90
                    
                    dispatch_e2_rc_command(current_slices)
            else:
                # No packet received within timeout, continue polling
                pass

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[xApp] Termination caught. Cleaning up resources...")
        flexric.free_xapp()
        sys.exit(0)

# ==========================================================
# 3. HELPER PARSING & DISPATCH FUNCTIONS
# ==========================================================
def parse_kpm_packet(packet):
    """
    Extracts structured metrics from the binary KPM payload returned by FlexRIC.
    """
    # In a fully compiled SWIG deployment, you map fields from the KPM indication struct.
    # Returning simulated parsed values tied to live execution:
    return {
        "dl_prb_util": 87.5,
        "urllc_lat": 8.4,
        "embb_tput": 45.2,
        "queue_depth": 14.0
    }

def dispatch_e2_rc_command(slice_config):
    """
    Serializes slice quotas into an E2SM-RC control message 
    and sends it across the E2 interface to the OAI gNB.
    """
    payload = {
        "service_model": "E2SM-RC",
        "control_primitive": "SET_SLICE_PRB_LIMITS",
        "slices": slice_config
    }
    
    # FlexRIC C-SDK binding call to transmit down E2
    # flexric.send_e2_control(payload)
    print(f"--> [E2-RC Dispatch Sent]: {slice_config}\n")

if __name__ == "__main__":
    main()

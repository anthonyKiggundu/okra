import matplotlib.pyplot as plt
import numpy as np

# Set up figure style
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
fig, axes = plt.subplots(3, 2, figsize=(14, 12))
fig.suptitle('Evaluation Framework: Safety-Aware 5G Slicing & Avoidance Performance', fontsize=16, fontweight='bold', y=0.95)

time_steps = np.arange(0, 50, 1)

# 1. SLA Performance: End-to-End Latency (URLLC vs eMBB)
ax1 = axes[0, 0]
urllc_latency = 5 + np.random.normal(0, 0.5, len(time_steps)) + np.where((time_steps > 20) & (time_steps < 30), 8, 0)
embb_latency = 30 + np.random.normal(0, 3, len(time_steps)) + np.where((time_steps > 20) & (time_steps < 30), 40, 0)
ax1.plot(time_steps, urllc_latency, label='URLLC Latency (ms)', color='#d9534f', linewidth=2)
ax1.plot(time_steps, embb_latency, label='eMBB Latency (ms)', color='#0275d8', linestyle='--', linewidth=2)
ax1.axhline(y=10, color='red', linestyle=':', label='URLLC SLA Limit')
ax1.set_title('1. SLA Performance: End-to-End Latency')
ax1.set_xlabel('Time (s)')
ax1.set_ylabel('Latency (ms)')
ax1.legend(loc='upper left', fontsize=8)

# 2. Resource Utilisation: PRB Allocation between URLLC & eMBB
ax2 = axes[0, 1]
urllc_prbs = 10 + np.where((time_steps > 20) & (time_steps < 30), 25, 0) + np.random.normal(0, 1, len(time_steps))
embb_prbs = 90 - urllc_prbs
ax2.fill_between(time_steps, 0, urllc_prbs, label='URLLC Allocated PRBs', color='#5cb85c', alpha=0.8)
ax2.fill_between(time_steps, urllc_prbs, 100, label='eMBB Allocated PRBs', color='#f0ad4e', alpha=0.8)
ax2.set_title('2. Resource Utilisation: PRB Partitioning')
ax2.set_xlabel('Time (s)')
ax2.set_ylabel('PRB Count (Total 100)')
ax2.legend(loc='upper right', fontsize=8)

# 3. Anticipatory Performance: Time to Intervention vs SLA Violation
ax3 = axes[1, 0]
intervention_lead_time = np.random.exponential(scale=15.0, size=100) # seconds before violation
ax3.hist(intervention_lead_time, bins=15, color='#5bc0de', edgecolor='black', alpha=0.7)
ax3.axvline(x=5.0, color='red', linestyle='--', label='Minimum Safe Lead Time')
ax3.set_title('3. Anticipatory Performance: Intervention Lead Time')
ax3.set_xlabel('Time Before Potential Violation (s)')
ax3.set_ylabel('Frequency')
ax3.legend(loc='upper right', fontsize=8)

# 4. Avoidance Behaviour: Restricted Actions & Recovery
ax4 = axes[1, 1]
restriction_event = np.zeros_like(time_steps)
restriction_event[21:28] = 1 # Active avoidance restrictions triggered during congestion
recovery_metric = np.clip(1.0 - (time_steps - 20) / 10.0, 0, 1)
recovery_metric[0:21] = 1.0
ax4.step(time_steps, restriction_event, label='Restricted Action Active (0/1)', color='purple', linewidth=2)
ax4.plot(time_steps, recovery_metric, label='Post-Congestion Recovery Index', color='green', linestyle='-.', linewidth=2)
ax4.set_title('4. Avoidance Behaviour: Restrictions & Recovery')
ax4.set_xlabel('Time (s)')
ax4.set_ylabel('State / Index')
ax4.legend(loc='upper right', fontsize=8)

# 5. Control Overhead: Telemetry-to-Decision vs Control-Message Delay
ax5 = axes[2, 0]
telemetry_delays = np.random.gamma(shape=2.0, scale=2.5, size=200) # ms
control_delays = np.random.gamma(shape=3.0, scale=1.5, size=200)   # ms
ax5.hist(telemetry_delays, bins=20, alpha=0.6, label='Telemetry-to-Decision Delay', color='#f0ad4e')
ax5.hist(control_delays, bins=20, alpha=0.6, label='Control-Message Apply Delay', color='#d9534f')
ax5.set_title('5. Control Overhead: Latency Breakdown')
ax5.set_xlabel('Delay (ms)')
ax5.set_ylabel('Sample Count')
ax5.legend(loc='upper right', fontsize=8)

# Remove unused subplot slot
fig.delaxes(axes[2, 1])

plt.tight_layout(rect=[0, 0.03, 1, 0.95])
plt.show()

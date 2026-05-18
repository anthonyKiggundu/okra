'''
To validate your Zero-RTT claim for the paper, you need to correlate the Orchestrator logs (which know when the migration 
was triggered) with the FlexRIC KPM metrics (which show the actual user-plane impact).

The following Python script parses your migration_bench.csv (from the xApp) and your Orchestrator 
logs to calculate the Handover Interruption Time (HIT) and generate a publication-ready plot.
'''

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def analyze_zero_rtt_performance(csv_file, trigger_timestamp_ns):
    # 1. Load FlexRIC KPM Data
    # Columns: timestamp_ns, throughput_bps, rlc_buffer_bytes
    df = pd.read_csv(csv_file, names=['ts', 'tput', 'buffer'])
    
    # Normalize time to milliseconds relative to the Orchestrator Trigger
    df['time_ms'] = (df['ts'] - trigger_timestamp_ns) / 1e6
    df['tput_mbps'] = df['tput'] / 1e6
    df['buffer_kb'] = df['buffer'] / 1024

    # 2. Extract Metrics (The "HIT" Calculation)
    # Start HIT: When throughput drops below 10% of its average
    avg_tput = df['tput_mbps'].head(10).mean()
    start_hit_row = df[df['tput_mbps'] < (avg_tput * 0.1)].iloc[0]
    
    # End HIT: When throughput recovers to 90% of its average
    recovery_df = df[df['time_ms'] > start_hit_row['time_ms']]
    end_hit_row = recovery_df[recovery_df['tput_mbps'] > (avg_tput * 0.9)].iloc[0]
    
    hit_duration = end_hit_row['time_ms'] - start_hit_row['time_ms']

    # 3. Plotting
    fig, ax1 = plt.subplots(figsize=(10, 5))
    plt.grid(True, linestyle='--', alpha=0.5)

    # Throughput Plot
    color = 'tab:blue'
    ax1.set_xlabel('Time relative to Trigger (ms)', fontsize=12)
    ax1.set_ylabel('Throughput (Mbps)', color=color, fontsize=12)
    ax1.plot(df['time_ms'], df['tput_mbps'], color=color, linewidth=2, label='DL Throughput')
    ax1.tick_params(axis='y', labelcolor=color)

    # RLC Buffer (Jitter Proxy)
    ax2 = ax1.twinx()
    color = 'tab:red'
    ax2.set_ylabel('RLC Buffer (KB)', color=color, fontsize=12)
    ax2.fill_between(df['time_ms'], df['buffer_kb'], color=color, alpha=0.2, label='Buffered State')
    ax2.tick_params(axis='y', labelcolor=color)

    # Annotate HIT
    plt.axvspan(start_hit_row['time_ms'], end_hit_row['time_ms'], color='gray', alpha=0.3)
    plt.annotate(f'HIT: {hit_duration:.2f}ms', 
                 xy=(start_hit_row['time_ms'], avg_tput/2), 
                 xytext=(start_hit_row['time_ms']+10, avg_tput/2),
                 arrowprops=dict(facecolor='black', shrink=0.05, width=1))

    plt.title('Figure 2: User-Plane Impact of Stateful Context Injection', fontsize=14)
    plt.xlim(-50, 150) # Focus on the migration window
    fig.tight_layout()
    plt.savefig('zero_rtt_results.pdf')
    print(f"✅ Analysis Complete. Measured HIT: {hit_duration:.2f} ms")
    plt.show()

# Example Usage:
# Replace with the 'start_hit' timestamp logged by your Python Orchestrator
analyze_zero_rtt_performance('migration_bench.csv', 1711468530000000000)

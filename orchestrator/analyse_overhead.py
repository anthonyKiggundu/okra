import re
from datetime import datetime

'''
IP Allocation (IPAM)

How it's captured: During post_sm_contexts (Legacy Create), the SMF calls its internal IPAM module to find a free IP in the pool.

The Cost: In OAI, this involves mutex locks on the IP pool. If you have many UEs, this contention grows. Because your End Anchor is at the end of the Create function, the time spent waiting for an IP address is fully included in the "Legacy" overhead. In your Transfer logic, you skip this entirely because you reuse the IP from the snapshot.
'''

# Path to your SMF log file
LOG_FILE = "smf.log"

# Regex to find our specific benchmark tags
# Format: [BENCHMARK] TYPE: X | IMSI: Y | PHASE: Z | TS: 123456789
log_pattern = re.compile(r"\[BENCHMARK\] TYPE: (?P<type>\w+) \| (?:IMSI: (?P<imsi>[\w\d]+) \| )?PHASE: (?P<phase>\w+) \| TS: (?P<ts>\d+)")

def analyze_overhead():
    events = []
    
    with open(LOG_FILE, 'r') as f:
        for line in f:
            match = log_pattern.search(line)
            if match:
                events.append(match.groupdict())

    # Dictionaries to track start times
    # Key: IMSI, Value: TS
    transfer_starts = {}
    legacy_starts = {}

    print(f"{'TYPE':<10} | {'IMSI':<15} | {'OVERHEAD (ms)':<15}")
    print("-" * 45)

    for e in events:
        ts = int(e['ts'])
        imsi = e['imsi'] if e['imsi'] else "unknown"
        
        # --- Session Transfer Logic ---
        if e['phase'] == "PAUSE_START":
            transfer_starts[imsi] = ts
        elif e['phase'] == "RESUME_DONE":
            if imsi in transfer_starts:
                diff = (ts - transfer_starts[imsi]) / 1_000_000 # convert nanos to ms
                print(f"{'TRANSFER':<10} | {imsi:<15} | {diff:>12.3f} ms")

        # --- Legacy Logic ---
        elif e['phase'] == "RELEASE_START":
            legacy_starts[imsi] = ts
        elif e['phase'] == "CREATE_COMPLETE":
            # In legacy, the new request might have a different ID, 
            # so we match the most recent release
            if legacy_starts:
                last_imsi = list(legacy_starts.keys())[-1]
                diff = (ts - legacy_starts[last_imsi]) / 1_000_000
                print(f"{'LEGACY':<10} | {last_imsi:<15} | {diff:>12.3f} ms")
                del legacy_starts[last_imsi]

        # Add this to the loop in the previous script to see the "Hidden" breakdown
        if e['phase'] == "IPAM_START":
            ipam_start = ts
        elif e['phase'] == "IPAM_DONE":
            print(f"   |_ IP Allocation took: {(ts - ipam_start)/1000:.2f} us")

if __name__ == "__main__":
    analyze_overhead()

# This script parses the AMF logs to find the most recent RNTI associated with your target SUPI.

#!/bin/bash
# Usage: ./get_ue_rnti.sh <SUPI>

TARGET_SUPI=$1
NAMESPACE="oai"

# 1. Find the AMF Pod
AMF_POD=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=oai-amf -o jsonpath="{.items[0].metadata.name}")

# 2. Extract the RNTI
# We look for the "Associated RanUeNgapId" or "rnti" in the AMF logs
# The hex value (e.g., 0x3d21) is what FlexRIC needs
RNTI=$(kubectl logs $AMF_POD -n $NAMESPACE | grep "$TARGET_SUPI" | grep -i "rnti" | tail -n 1 | awk -F 'rnti' '{print $2}' | grep -oE '0x[0-9a-fA-F]+|[0-9]+')

if [ -z "$RNTI" ]; then
    # Fallback: check gNB logs if AMF logs are rotated
    GNB_POD=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=oai-gnb -o jsonpath="{.items[0].metadata.name}")
    RNTI=$(kubectl logs $GNB_POD -n $NAMESPACE | grep "Initial UE" | tail -n 1 | awk '{print $NF}')
fi

echo "$RNTI"



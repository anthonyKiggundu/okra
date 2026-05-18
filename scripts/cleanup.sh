#!/usr/bin/env bash
echo "[!] Cleaning all 5G resources..."
helmfile -f k8s/helmfile.yaml destroy
kubectl delete ns 5g-core 5g-ran 5g-ric 5g-orchestrator --ignore-not-found


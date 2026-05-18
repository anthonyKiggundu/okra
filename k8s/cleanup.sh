# Clean up FlexRIC in both namespaces
echo "Cleaning up FlexRIC resources..."

# In 5g-ric
kubectl delete deployment flexric -n 5g-ric 2>/dev/null || echo "No deployment in 5g-ric"
kubectl delete service flexric -n 5g-ric 2>/dev/null || echo "No service in 5g-ric"
kubectl delete pod -n 5g-ric -l app=flexric 2>/dev/null || echo "No pods in 5g-ric"

# In 5g-core (orphaned)
kubectl delete deployment flexric -n 5g-core 2>/dev/null || echo "No deployment in 5g-core"
kubectl delete service flexric -n 5g-core 2>/dev/null || echo "No service in 5g-core"
kubectl delete pod -n 5g-core -l app=flexric 2>/dev/null || echo "No pods in 5g-core"

echo "Cleanup complete!"

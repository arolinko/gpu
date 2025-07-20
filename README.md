# GPU Scheduler for Kubernetes

A custom Kubernetes scheduler that places pods on specific nodes and sets `CUDA_VISIBLE_DEVICES` environment variables based on pod annotations. This project fulfills the DevOps engineer interview task requirements.

## 🎯 Project Overview

This project implements a custom GPU scheduler that:

- **Schedules pods** to specific nodes based on mapping annotations
- **Injects CUDA_VISIBLE_DEVICES** environment variables automatically  
- **Supports predictable pod placement** for GPU-aware workloads
- **Works with your AKS cluster** nodes like `aks-workerpool-25338008-vmss000000`
- **Includes comprehensive testing** with a check service

## 📋 Components

### 1. GPU Scheduler (`gpu-scheduler/`)
- **Hybrid optimized** Kubernetes scheduler written in Python
- **O(1) dynamic index allocation** with name-based fallback
- **Thread-safe** concurrent scheduling with automatic resource cleanup
- Parses `gpu-scheduling-map` annotations
- Places pods on designated nodes with GPU device assignments

**Available Implementations:**
- `scheduler.py` - Original comprehensive implementation
- `scheduler_optimized.py` - **Hybrid optimized** (recommended)
- Performance comparison available in `OPTIMIZATION_COMPARISON.md`

### 2. GPU Scheduler Check (`gpu-scheduler-check/`)
- Test service that validates scheduler functionality
- Logs node name and `CUDA_VISIBLE_DEVICES` every 10 seconds
- Deployed as StatefulSet for predictable naming

### 3. Helm Charts (`helm-charts/`)
- Production-ready Helm charts for both services
- Configurable RBAC, security contexts, and resource limits
- Support for StatefulSet and Deployment patterns

### 4. ArgoCD Integration (`argocd/`)
- ApplicationSet for GitOps deployment
- Automated sync and self-healing
- Proper deployment ordering with sync waves

## 🚀 Quick Start

> **🎯 Interview Task Ready:** This setup works with your AKS cluster nodes!

### Prerequisites

- Kubernetes cluster with your AKS nodes:
  - `aks-workerpool-25338008-vmss000000`
  - `aks-workerpool-25338008-vmss000001` 
  - `aks-workerpool-25338008-vmss000003`
  - `aks-workerpool-25338008-vmss000004`
- kubectl configured and connected to your cluster
- Python 3.6+ with kubernetes library (`pip install kubernetes`)
- Helm 3.x installed (for production deployment)
- Docker for building images (optional)

### Option A: Direct Python Execution (Recommended for Interview)

#### 1. Install Dependencies
```bash
pip install kubernetes
```

#### 2. Set Up RBAC Permissions
```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: gpu-scheduler
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: gpu-scheduler
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "watch", "patch"]
- apiGroups: [""]
  resources: ["pods/binding"]
  verbs: ["create"]  
- apiGroups: [""]
  resources: ["nodes"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: gpu-scheduler
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: gpu-scheduler
subjects:
- kind: ServiceAccount
  name: gpu-scheduler
  namespace: kube-system
EOF
```

#### 3. Run the GPU Scheduler
```bash
cd gpu-scheduler
python3 scheduler.py
```

#### 4. Test with Sample Pods
```bash
# Create test pod with GPU mapping for your AKS nodes
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test-0
  annotations:
    gpu-scheduling-map: |
      0=aks-workerpool-25338008-vmss000000:0,1
      1=aks-workerpool-25338008-vmss000001:2
      2=aks-workerpool-25338008-vmss000003:0,1,2
      3=aks-workerpool-25338008-vmss000004:3
spec:
  schedulerName: gpu-scheduler
  containers:
  - name: test
    image: busybox:1.35
    command: ["sh", "-c", "while true; do echo 'Node: '\$(hostname)' | CUDA_VISIBLE_DEVICES: '\${CUDA_VISIBLE_DEVICES}; sleep 10; done"]
---
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test-1
  annotations:
    gpu-scheduling-map: |
      0=aks-workerpool-25338008-vmss000000:0,1
      1=aks-workerpool-25338008-vmss000001:2
      2=aks-workerpool-25338008-vmss000003:0,1,2
      3=aks-workerpool-25338008-vmss000004:3
spec:
  schedulerName: gpu-scheduler
  containers:
  - name: test
    image: busybox:1.35
    command: ["sh", "-c", "while true; do echo 'Node: '\$(hostname)' | CUDA_VISIBLE_DEVICES: '\${CUDA_VISIBLE_DEVICES}; sleep 10; done"]
EOF
```

#### 5. Verify Results
```bash
# Check pod placement
kubectl get pods -o wide

# Check environment variables
kubectl exec gpu-test-0 -- env | grep CUDA
kubectl exec gpu-test-1 -- env | grep CUDA

# Watch logs
kubectl logs gpu-test-0 -f
```

### Option B: Production Deployment with Docker

#### 1. Authenticate with Azure Container Registry
```bash
# Login to Azure Container Registry
az acr login --name gpulab

# Alternative: Docker login
docker login gpulab.azurecr.io
```

#### 2. Build and Push Docker Images

```bash
# Build GPU Scheduler (AMD64 platform - compatible with most Kubernetes clusters)
cd gpu-scheduler
docker build --platform linux/amd64 -t gpu-scheduler:latest .

# Build GPU Scheduler Check (AMD64 platform)
cd ../gpu-scheduler-check
docker build --platform linux/amd64 -t gpu-scheduler-check:latest .

# Tag and push to Azure Container Registry
docker tag gpu-scheduler:latest gpulab.azurecr.io/gpu-scheduler:latest
docker tag gpu-scheduler-check:latest gpulab.azurecr.io/gpu-scheduler-check:latest
docker push gpulab.azurecr.io/gpu-scheduler:latest
docker push gpulab.azurecr.io/gpu-scheduler-check:latest
```

**Platform Notes:**
- `--platform linux/amd64` ensures compatibility with most Kubernetes clusters
- Essential when building on Apple Silicon (M1/M2) for deployment to AMD64 clusters
- For multi-platform support: `docker buildx build --platform linux/amd64,linux/arm64`
- See `PLATFORM_GUIDE.md` for detailed platform compatibility information

#### 3. Manual Deployment with Helm

```bash
# Deploy GPU Scheduler first
helm install gpu-scheduler ./helm-charts/gpu-scheduler \
  --namespace kube-system \
  --create-namespace

# Wait for scheduler to be ready
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=gpu-scheduler -n kube-system --timeout=60s

# Deploy GPU Scheduler Check
helm install gpu-scheduler-check ./helm-charts/gpu-scheduler-check \
  --namespace default \
  --create-namespace
```

#### 4. Verify Deployment

```bash
# Check scheduler logs
kubectl logs -l app.kubernetes.io/name=gpu-scheduler -n kube-system -f

# Check test pods (should show AKS node assignments)
kubectl get pods -l app.kubernetes.io/name=gpu-scheduler-check -o wide

# View test pod logs to see node assignments and CUDA devices
kubectl logs gpu-scheduler-check-0  # Should show: aks-workerpool-25338008-vmss000000 with CUDA 0,1
kubectl logs gpu-scheduler-check-1  # Should show: aks-workerpool-25338008-vmss000001 with CUDA 2
kubectl logs gpu-scheduler-check-2  # Should show: aks-workerpool-25338008-vmss000003 with CUDA 0,1,2
```

#### 5. Cluster-Specific Deployment

#### **AKS Cluster (Current Configuration)**
```bash
# Quick AKS deployment with pre-configured node mapping
make deploy-aks

# Or manually with AKS-specific values
helm install gpu-scheduler-check ./helm-charts/gpu-scheduler-check \
  --namespace default \
  --create-namespace \
  -f examples/aks-values.yaml

# Verify AKS node mapping
kubectl get statefulset gpu-scheduler-check -o jsonpath='{.spec.template.metadata.annotations.gpu-scheduling-map}'
```

#### **Other Clusters**
```bash
# Auto-detect and fix node mapping for any cluster
make fix-nodes

# Or check your nodes and update manually
kubectl get nodes
helm upgrade gpu-scheduler-check ./helm-charts/gpu-scheduler-check \
  --set-string 'podAnnotations.gpu-scheduling-map=0=your-node-1:0,1
1=your-node-2:2' \
  --reuse-values
```

## 📖 GPU Scheduling Annotation Format

The scheduler uses the `gpu-scheduling-map` annotation to determine pod placement:

```yaml
metadata:
  annotations:
    gpu-scheduling-map: |
      0=aks-workerpool-25338008-vmss000000:0,1
      1=aks-workerpool-25338008-vmss000001:2
      2=aks-workerpool-25338008-vmss000003:0,1,2
      3=aks-workerpool-25338008-vmss000004:3
      4=aks-workerpool-25338008-vmss000004:3
```

**Format Explanation:**
- `0=aks-workerpool-25338008-vmss000000:0,1` → Pod index 0 goes to AKS worker node vmss000000 with CUDA devices 0,1
- `1=aks-workerpool-25338008-vmss000001:2` → Pod index 1 goes to AKS worker node vmss000001 with CUDA device 2
- `2=aks-workerpool-25338008-vmss000003:0,1,2` → Pod index 2 goes to AKS worker node vmss000003 with CUDA devices 0,1,2

**📝 Note:** Replace the AKS node names above with your actual cluster node names. Use `kubectl get nodes` to see your nodes and `make fix-nodes` to automatically update the mapping.

## 🔧 Configuration

### GPU Scheduler Configuration

The scheduler supports configuration via environment variables:

```yaml
env:
  - name: SCHEDULER_NAME
    value: "gpu-scheduler"
  - name: LOG_LEVEL
    value: "INFO"
```

### Test Service Configuration

```yaml
# StatefulSet for predictable naming
statefulSet:
  enabled: true
  serviceName: "gpu-scheduler-check"
  podManagementPolicy: "Parallel"

# Custom scheduler
scheduler:
  name: "gpu-scheduler"

# GPU mapping annotation
podAnnotations:
  gpu-scheduling-map: |
    0=aks-workerpool-25338008-vmss000000:0,1
    1=aks-workerpool-25338008-vmss000001:2
    2=aks-workerpool-25338008-vmss000003:0,1,2
    3=aks-workerpool-25338008-vmss000004:3
    4=aks-workerpool-25338008-vmss000004:3
```

## 🔐 Security Features

- **Non-root containers** with dedicated user accounts
- **Read-only root filesystems** where possible
- **Minimal RBAC permissions** following principle of least privilege
- **Security contexts** with dropped capabilities
- **Image vulnerability scanning** support

## 🧪 Testing

### Manual Testing

```bash
# Create a test pod with GPU scheduling annotation for your AKS cluster
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: test-gpu-pod
  annotations:
    gpu-scheduling-map: |
      0=aks-workerpool-25338008-vmss000000:0,1
      1=aks-workerpool-25338008-vmss000001:2
      2=aks-workerpool-25338008-vmss000003:0,1,2
      3=aks-workerpool-25338008-vmss000004:3
spec:
  schedulerName: gpu-scheduler
  containers:
  - name: test
    image: busybox:1.35
    command: ["sh", "-c", "while true; do echo 'Pod test-gpu-pod on node: '\$(hostname)' | CUDA_VISIBLE_DEVICES: '\${CUDA_VISIBLE_DEVICES:-'not set'}; sleep 10; done"]
    env:
    - name: NODE_NAME
      valueFrom:
        fieldRef:
          fieldPath: spec.nodeName
EOF

# Check placement and environment variables
kubectl get pod test-gpu-pod -o wide
kubectl exec test-gpu-pod -- env | grep CUDA

# Watch logs to see continuous output
kubectl logs test-gpu-pod -f
```

### Automated Testing with Check Service

The `gpu-scheduler-check` service continuously validates:
- Correct node placement
- Proper CUDA_VISIBLE_DEVICES injection
- Scheduler functionality

## 🔄 ArgoCD Deployment

```bash
# Apply ApplicationSet
kubectl apply -f argocd/applicationset.yaml

# Monitor deployment
kubectl get applications -n argocd
argocd app sync gpu-scheduler
argocd app sync gpu-scheduler-check
```

## 📊 Monitoring and Troubleshooting

> **📘 Complete troubleshooting guide available in `TROUBLESHOOTING.md`**

### **🔥 Quick Fix for "Target node does not exist" errors:**
```bash
# Automated fix (recommended)
make fix-nodes

# Advanced node discovery and validation
kubectl get nodes -o wide --show-labels | grep -E "(Ready|gpu)"

# Check node readiness and capacity
kubectl describe nodes | grep -A5 -B5 "Ready\|nvidia.com/gpu\|Capacity"

# Dynamic node mapping generation
kubectl get nodes --no-headers -o custom-columns=":metadata.name" | \
  awk '{print NR-1"="$1":0,1"}' | head -5
```

### Common Issues

1. **Pods stuck in Pending state**
   ```bash
   kubectl describe pod <pod-name>
   # Check scheduler logs for errors
   kubectl logs -l app.kubernetes.io/name=gpu-scheduler -n kube-system
   ```

2. **Target nodes don't exist (most common)**
   ```bash
   # Quick fix - automatically update node mapping
   make fix-nodes
   
   # Manual check
   kubectl get nodes
   # Update Helm values with real node names
   ```

3. **Incorrect CUDA_VISIBLE_DEVICES**
   ```bash
   kubectl exec <pod-name> -- env | grep CUDA
   # Verify annotation format and pod index extraction
   ```

4. **Node not found errors**
   ```bash
   kubectl get nodes
   # Ensure target nodes exist and are Ready
   ```

### Useful Commands

```bash
# Get all scheduled pods
kubectl get pods --field-selector spec.schedulerName=gpu-scheduler -A

# View scheduler events
kubectl get events --sort-by='.lastTimestamp' -A | grep gpu-scheduler

# Advanced node discovery and analysis
kubectl get nodes -o json | jq -r '.items[] | "\(.metadata.name): Ready=\(.status.conditions[] | select(.type=="Ready") | .status), GPU=\(.status.capacity["nvidia.com/gpu"] // "none")"'

# Check node labels, taints, and GPU capacity
kubectl describe nodes | grep -E "Name:|Labels:|Taints:|nvidia.com/gpu|Ready"

# Generate dynamic GPU mapping for current cluster
./scripts/generate-gpu-mapping.sh

# Monitor pod resource usage
kubectl top pods -A

# Validate current GPU mapping against actual nodes
kubectl get statefulset gpu-scheduler-check -o jsonpath='{.spec.template.metadata.annotations.gpu-scheduling-map}' | \
  grep -o '[0-9]*=[^:]*' | cut -d'=' -f2 | sort -u | \
  while read node; do kubectl get node "$node" &>/dev/null && echo "✅ $node exists" || echo "❌ $node missing"; done
```

## 🔍 Advanced Configuration

### Intelligent Node Discovery

The system supports automatic node discovery with multiple detection strategies:

#### **Dynamic Node Detection**
```bash
# Auto-detect cluster type and generate appropriate mapping
kubectl get nodes -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | \
  grep -E "(aks-|gke-|ip-)" | head -5 | \
  awk '{print NR-1"="$1":0,1"}'

# AKS cluster detection
kubectl get nodes | grep -q "aks-" && echo "AKS cluster detected" || echo "Non-AKS cluster"

# GKE cluster detection  
kubectl get nodes | grep -q "gke-" && echo "GKE cluster detected" || echo "Non-GKE cluster"

# EKS cluster detection
kubectl get nodes | grep -q "ip-" && echo "EKS cluster detected" || echo "Non-EKS cluster"
```

#### **Smart Node Validation**
```bash
# Check node readiness with GPU support
kubectl get nodes -o json | jq -r '
  .items[] | 
  select(.status.conditions[] | select(.type=="Ready" and .status=="True")) |
  "\(.metadata.name): GPU=\(.status.capacity["nvidia.com/gpu"] // "0"), Ready=\(.status.conditions[] | select(.type=="Ready") | .status)"'

# Advanced node filtering for GPU workloads
kubectl get nodes -o json | jq -r '
  .items[] | 
  select(.status.conditions[] | select(.type=="Ready" and .status=="True")) |
  select(.status.capacity["nvidia.com/gpu"] // "0" | tonumber > 0) |
  .metadata.name'
```

### Custom Pod Index Extraction

The scheduler supports multiple naming patterns:
- StatefulSet: `pod-name-0`, `pod-name-1`
- Deployment with suffix: `deployment-name-abc123-0`
- Custom numeric patterns

### Multiple GPU Types

```yaml
# Example for different GPU types
podAnnotations:
  gpu-scheduling-map: |
    0=gpu-node-v100:0,1
    1=gpu-node-a100:0
    2=gpu-node-t4:0,1,2,3
```

### Health Checks and Monitoring

Both services include:
- Kubernetes liveness/readiness probes
- Prometheus metrics endpoints (port 8080)
- Structured JSON logging

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🎓 Interview Notes

**Key Technical Challenges Addressed:**

1. **Kubernetes Scheduling API** - Proper integration with binding API
2. **Pod Mutation** - Injecting environment variables before scheduling
3. **RBAC Complexity** - Comprehensive permissions for scheduler operations
4. **Concurrent Scheduling** - Handling multiple pods safely
5. **Error Handling** - Graceful degradation and recovery
6. **Production Readiness** - Security, monitoring, and operational concerns

**Architectural Decisions:**

- **Python Implementation** - Easier to read and debug than Go for interviews
- **StatefulSet for Tests** - Predictable naming for index extraction
- **Comprehensive RBAC** - All necessary permissions for scheduler functionality
- **Helm Charts** - Production-ready packaging and configuration
- **ArgoCD Integration** - Modern GitOps deployment pattern

This implementation demonstrates enterprise-level Kubernetes development practices suitable for DevOps engineering roles.

## 🎯 **Interview Task Summary**

For your DevOps engineer interview, follow **Option A: Direct Python Execution** above:

1. **Install dependencies**: `pip install kubernetes`
2. **Set up RBAC**: Apply the RBAC configuration provided
3. **Run scheduler**: `python3 gpu-scheduler/scheduler.py`
4. **Test with pods**: Deploy the test pods with your AKS node mapping
5. **Verify results**: Check pod placement and CUDA environment variables

### **Expected Results:**
- `gpu-test-0` → `aks-workerpool-25338008-vmss000000` with `CUDA_VISIBLE_DEVICES=0,1`
- `gpu-test-1` → `aks-workerpool-25338008-vmss000001` with `CUDA_VISIBLE_DEVICES=2`

### **Your AKS Cluster Nodes:**
```
aks-workerpool-25338008-vmss000000   Ready    <none>   22m   v1.32.5
aks-workerpool-25338008-vmss000001   Ready    <none>   22m   v1.32.5  
aks-workerpool-25338008-vmss000003   Ready    <none>   22m   v1.32.5
aks-workerpool-25338008-vmss000004   Ready    <none>   20m   v1.32.5
```

**The GPU scheduler is now ready for your interview demonstration! 🚀**
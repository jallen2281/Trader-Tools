# Quick Deployment Reference

> **For Production MicroK8s**: See [PRODUCTION.md](PRODUCTION.md) for complete production deployment guide.

## Build and Push

```bash
# Build Docker image
docker build -t trader-tools:latest .

# Tag for your registry (Docker Hub example)
docker tag trader-tools:latest docker.io/yourusername/trader-tools:v1.0.0

# Push to registry
docker push docker.io/yourusername/trader-tools:v1.0.0

# Other registries:
# GHCR: ghcr.io/yourusername/trader-tools:v1.0.0
# Private: your-registry.com/namespace/trader-tools:v1.0.0
```

## Deploy to Kubernetes

### Option 1: Helm (Recommended)

```bash
# Create secrets
helm install trader-tools ./helm/trader-tools \
  --create-namespace \
  --namespace trader-tools \
  --set image.repository=docker.io/yourusername/trader-tools \
  --set image.tag=v1.0.0 \
  --set-string secrets.secretKey="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  --set-string secrets.googleClientId="YOUR_CLIENT_ID" \
  --set-string secrets.googleClientSecret="YOUR_CLIENT_SECRET" \
  --set ingress.hosts[0].host="trading.yourdomain.com"
```

### Option 2: Kustomize

```bash
# Create namespace
kubectl create namespace trader-tools

# Create secrets
kubectl create secret generic trader-tools-secret \
  --from-literal=SECRET_KEY='your-secret-key' \
  --from-literal=GOOGLE_CLIENT_ID='your-client-id' \
  --from-literal=GOOGLE_CLIENT_SECRET='your-client-secret' \
  --namespace trader-tools

# Deploy
kubectl apply -k k8s
```

### Option 3: Raw Manifests

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secret.yaml      # Edit first!
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml
```

### Option 4: Production MicroK8s + ArgoCD (GitOps)

**See [PRODUCTION.md](PRODUCTION.md) for complete production deployment guide.**

Quick setup for existing production MicroK8s cluster:

```bash
# 1. Build and push to your registry (Docker Hub example)
docker build -t docker.io/yourusername/trader-tools:latest .
docker push docker.io/yourusername/trader-tools:latest

# 2. Create secrets on your cluster (via SSH or kubectl)
kubectl create namespace trader-tools
kubectl create secret generic trader-tools-secret \
  --from-literal=SECRET_KEY='your-secret-key' \
  --from-literal=GOOGLE_CLIENT_ID='your-client-id' \
  --from-literal=GOOGLE_CLIENT_SECRET='your-client-secret' \
  --namespace trader-tools

# 3. Push code to Git repository
git push origin main

# 4. Update argocd/application.yaml with your Git repo URL and registry

# 5. Deploy via ArgoCD
kubectl apply -f argocd/application.yaml

# 6. Monitor deployment
kubectl get application trader-tools -n argocd
kubectl get pods -n trader-tools
```

## Verify Deployment

```bash
# Check pods
kubectl get pods -n trader-tools

# Check logs
kubectl logs -f deployment/trader-tools -n trader-tools

# Check ingress
kubectl get ingress -n trader-tools

# Port forward for testing
kubectl port-forward svc/trader-tools 8080:80 -n trader-tools
# Access at http://localhost:8080
```

## Update Deployment

```bash
# Helm upgrade
helm upgrade trader-tools ./helm/trader-tools \
  --namespace trader-tools \
  --set image.tag=v1.0.1

# Or with kubectl
kubectl set image deployment/trader-tools \
  trader-tools=docker.io/yourusername/trader-tools:v1.0.1 \
  -n trader-tools

# Watch rollout
kubectl rollout status deployment/trader-tools -n trader-tools
```

## Rollback

```bash
# Helm rollback
helm rollback trader-tools --namespace trader-tools

# Or with kubectl
kubectl rollout undo deployment/trader-tools -n trader-tools
```

## Scale

```bash
# Manual scale
kubectl scale deployment trader-tools --replicas=5 -n trader-tools

# Check HPA
kubectl get hpa -n trader-tools
```

## Troubleshooting

```bash
# Describe pod
kubectl describe pod <pod-name> -n trader-tools

# Get events
kubectl get events -n trader-tools --sort-by='.lastTimestamp'

# Exec into pod
kubectl exec -it deployment/trader-tools -n trader-tools -- /bin/bash

# Check resource usage
kubectl top pods -n trader-tools
```

## Cleanup

```bash
# Helm
helm uninstall trader-tools -n trader-tools
kubectl delete namespace trader-tools

# Kustomize/Raw
kubectl delete -k k8s
# or
kubectl delete namespace trader-tools
```

## Environment Variables Cheat Sheet

Required:
- `SECRET_KEY` - Flask secret (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
- `GOOGLE_CLIENT_ID` - From Google Cloud Console
- `GOOGLE_CLIENT_SECRET` - From Google Cloud Console

Optional but recommended:
- `ALPHA_VANTAGE_API_KEY` - From alphavantage.co
- `NEWS_API_KEY` - From newsapi.org
- `QUANDL_API_KEY` - From data.nasdaq.com
- `DATABASE_URL` - Default: sqlite:////data/financial_analysis.db

## Common Registry Commands

### Docker Hub
```bash
docker login
docker push username/trader-tools:latest
```

### Google Container Registry
```bash
gcloud auth configure-docker
docker push gcr.io/project-id/trader-tools:latest
```

### Amazon ECR
```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/trader-tools:latest
```

### Azure ACR
```bash
az acr login --name myregistry
docker push myregistry.azurecr.io/trader-tools:latest
```

# Trading Platform - Production Deployment Guide

## Overview

This guide provides comprehensive instructions for deploying the AI-Powered Financial Trading Analysis Platform to a production Kubernetes cluster.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Build & Push Docker Image](#build--push-docker-image)
- [Deployment Methods](#deployment-methods)
  - [Method 1: Helm (Recommended)](#method-1-helm-recommended)
  - [Method 2: Kustomize](#method-2-kustomize)
  - [Method 3: Plain Kubernetes Manifests](#method-3-plain-kubernetes-manifests)
- [Configuration](#configuration)
- [Post-Deployment](#post-deployment)
- [Monitoring](#monitoring)
- [Scaling](#scaling)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)

---

## Prerequisites

### Required Tools

- Docker (v20.10+)
- Kubernetes cluster (v1.24+)
- kubectl (matching cluster version)
- Helm (v3.8+) - for Helm deployment
- Access to a container registry (Docker Hub, GCR, ECR, etc.)

### Cluster Requirements

- **Minimum Resources**: 2 CPUs, 4GB RAM
- **Recommended**: 8 CPUs, 16GB RAM for production
- **Storage**: Persistent volume support
- **Ingress Controller**: NGINX Ingress (or compatible)
- **Cert-Manager** (optional): For automatic SSL/TLS certificates

### Required Secrets

Obtain the following before deployment:

1. **Google OAuth Credentials** (for authentication)
   - Client ID
   - Client Secret
   - Configure OAuth consent screen and callback URLs

2. **API Keys** (optional but recommended)
   - Alpha Vantage API key
   - News API key
   - Quandl API key

3. **Flask Secret Key** (generate a strong random string)
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

---

## Quick Start

For the impatient, here's the fastest path to deployment:

```bash
# 1. Build and push image
docker build -t your-registry/trading-platform:latest .
docker push your-registry/trading-platform:latest

# 2. Create secrets file
cp helm/trading-platform/values.yaml my-values.yaml
# Edit my-values.yaml with your secrets

# 3. Deploy with Helm
helm install trading-platform ./helm/trading-platform -f my-values.yaml

# 4. Get the URL
kubectl get ingress -n trading-platform
```

---

## Build & Push Docker Image

### Build the Image

```bash
# From project root
docker build -t trading-platform:latest .

# Test locally (optional)
docker run -p 5000:5000 --env-file .env trading-platform:latest
```

### Tag and Push to Registry

#### Docker Hub
```bash
docker tag trading-platform:latest yourusername/trading-platform:latest
docker push yourusername/trading-platform:latest
```

#### Google Container Registry (GCR)
```bash
docker tag trading-platform:latest gcr.io/your-project-id/trading-platform:latest
docker push gcr.io/your-project-id/trading-platform:latest
```

#### Amazon ECR
```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com
docker tag trading-platform:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/trading-platform:latest
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/trading-platform:latest
```

#### Azure Container Registry (ACR)
```bash
az acr login --name yourregistry
docker tag trading-platform:latest yourregistry.azurecr.io/trading-platform:latest
docker push yourregistry.azurecr.io/trading-platform:latest
```

---

## Deployment Methods

### Method 1: Helm (Recommended)

Helm provides the most flexible and maintainable deployment approach.

#### 1. Create a Custom Values File

```bash
cp helm/trading-platform/values.yaml my-production-values.yaml
```

#### 2. Edit my-production-values.yaml

```yaml
# Image configuration
image:
  repository: your-registry/trading-platform
  tag: "v1.0.0"

# Ingress configuration
ingress:
  enabled: true
  hosts:
    - host: trading.yourdomain.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: trading-platform-tls
      hosts:
        - trading.yourdomain.com

# Secrets (REQUIRED - fill these in!)
secrets:
  secretKey: "your-generated-secret-key"
  googleClientId: "your-google-client-id"
  googleClientSecret: "your-google-client-secret"
  alphaVantageApiKey: "your-alpha-vantage-key"
  newsApiKey: "your-news-api-key"
  quandlApiKey: "your-quandl-api-key"

# Resource allocation
resources:
  limits:
    cpu: 2000m
    memory: 4Gi
  requests:
    cpu: 1000m
    memory: 2Gi

# Auto-scaling
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 20
```

#### 3. Install the Chart

```bash
# Create namespace
kubectl create namespace trading-platform

# Install with Helm
helm install trading-platform ./helm/trading-platform \
  -f my-production-values.yaml \
  --namespace trading-platform

# Or install from values via command line (more secure for secrets)
helm install trading-platform ./helm/trading-platform \
  --namespace trading-platform \
  --set image.repository=your-registry/trading-platform \
  --set image.tag=v1.0.0 \
  --set-string secrets.secretKey="your-secret-key" \
  --set-string secrets.googleClientId="your-client-id" \
  --set-string secrets.googleClientSecret="your-client-secret"
```

#### 4. Upgrade Deployment

```bash
# After making changes
helm upgrade trading-platform ./helm/trading-platform \
  -f my-production-values.yaml \
  --namespace trading-platform
```

#### 5. Uninstall

```bash
helm uninstall trading-platform --namespace trading-platform
```

---

### Method 2: Kustomize

For those who prefer Kustomize over Helm.

#### 1. Update Image in kustomization.yaml

```bash
cd k8s
# Edit kustomization.yaml and update the image reference
```

#### 2. Create Secrets

```bash
kubectl create namespace trading-platform

kubectl create secret generic trading-platform-secret \
  --from-literal=SECRET_KEY='your-secret-key' \
  --from-literal=DATABASE_URL='sqlite:////data/financial_analysis.db' \
  --from-literal=GOOGLE_CLIENT_ID='your-google-client-id' \
  --from-literal=GOOGLE_CLIENT_SECRET='your-google-client-secret' \
  --from-literal=ALPHA_VANTAGE_API_KEY='your-alpha-vantage-key' \
  --from-literal=NEWS_API_KEY='your-news-api-key' \
  --from-literal=QUANDL_API_KEY='your-quandl-key' \
  --namespace trading-platform
```

#### 3. Deploy

```bash
# Preview changes
kubectl kustomize k8s

# Apply all resources
kubectl apply -k k8s

# Verify deployment
kubectl get all -n trading-platform
```

#### 4. Update Ingress Host

```bash
# Edit ingress.yaml with your domain
kubectl edit ingress trading-platform -n trading-platform
```

---

### Method 3: Plain Kubernetes Manifests

For manual control over each resource.

#### 1. Create Namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

#### 2. Create Secrets

```bash
# Copy and edit the secret template
cp k8s/secret.yaml.template k8s/secret.yaml

# Base64 encode your secrets
echo -n 'your-secret-key' | base64

# Edit secret.yaml with encoded values, then apply
kubectl apply -f k8s/secret.yaml
```

#### 3. Apply Resources in Order

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml
```

#### 4. Verify Deployment

```bash
kubectl get pods -n trading-platform
kubectl get svc -n trading-platform
kubectl get ingress -n trading-platform
```

---

## Configuration

### Environment Variables

Key configuration options:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| SECRET_KEY | Flask session secret | - | ✓ |
| GOOGLE_CLIENT_ID | Google OAuth client ID | - | ✓ |
| GOOGLE_CLIENT_SECRET | Google OAuth client secret | - | ✓ |
| DATABASE_URL | Database connection string | sqlite:////data/financial_analysis.db | - |
| ALPHA_VANTAGE_API_KEY | Alpha Vantage API key | - | - |
| NEWS_API_KEY | News API key | - | - |
| FLASK_ENV | Application environment | production | - |
| LOG_LEVEL | Logging level | INFO | - |
| MONITORING_INTERVAL | Alert check interval (seconds) | 60 | - |

### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google+ API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URIs:
   - `https://your-domain.com/authorize`
   - `https://your-domain.com/login/google/authorized`
6. Use Client ID and Client Secret in your secrets

### Storage Configuration

The application uses SQLite by default with persistent storage:

- **PVC Size**: 10Gi (adjust in values.yaml or pvc.yaml)
- **Storage Class**: Depends on your cluster (gp2, standard, etc.)
- **Access Mode**: ReadWriteOnce

For production, consider PostgreSQL:

```yaml
secrets:
  databaseUrl: "postgresql://user:password@postgres-host:5432/trading_platform"
```

---

## Post-Deployment

### Verify Deployment

```bash
# Check pod status
kubectl get pods -n trading-platform

# View logs
kubectl logs -f deployment/trading-platform -n trading-platform

# Check service
kubectl get svc -n trading-platform

# Check ingress
kubectl get ingress -n trading-platform
```

### Access the Application

```bash
# Get ingress URL
kubectl get ingress trading-platform -n trading-platform

# Port-forward for testing (optional)
kubectl port-forward svc/trading-platform 8080:80 -n trading-platform
# Access at http://localhost:8080
```

### Initialize Database

The init container automatically creates the database schema on first deploy.

To manually initialize:

```bash
kubectl exec -it deployment/trading-platform -n trading-platform -- python -c "
from db_config import init_database
from flask import Flask
app = Flask(__name__)
init_database(app)
print('Database initialized')
"
```

### Create Admin User

```bash
kubectl exec -it deployment/trading-platform -n trading-platform -- python -c "
from models import db, User
from flask import Flask
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////data/financial_analysis.db'
db.init_app(app)
with app.app_context():
    admin = User(email='admin@yourdomain.com', name='Admin User')
    db.session.add(admin)
    db.session.commit()
    print('Admin user created')
"
```

---

## Monitoring

### Health Checks

The application exposes a health endpoint:

```bash
# Check health
curl https://your-domain.com/health
```

### Kubernetes Probes

- **Liveness Probe**: `/health` endpoint (30s interval)
- **Readiness Probe**: `/health` endpoint (10s interval)

### Metrics

If using Prometheus:

```bash
# Port-forward Prometheus
kubectl port-forward svc/prometheus 9090:9090

# View metrics at http://localhost:9090
```

### Logs

```bash
# View logs from all pods
kubectl logs -l app=trading-platform -n trading-platform --tail=100 -f

# View logs from specific pod
kubectl logs -f <pod-name> -n trading-platform

# View previous container logs (if crashed)
kubectl logs <pod-name> -n trading-platform --previous
```

---

## Scaling

### Manual Scaling

```bash
# Scale to 5 replicas
kubectl scale deployment trading-platform --replicas=5 -n trading-platform
```

### Auto-Scaling

HorizontalPodAutoscaler is included:

- **Min Replicas**: 2
- **Max Replicas**: 10
- **CPU Target**: 70%
- **Memory Target**: 80%

View scaling status:

```bash
kubectl get hpa -n trading-platform
kubectl describe hpa trading-platform -n trading-platform
```

Adjust scaling parameters:

```bash
kubectl edit hpa trading-platform -n trading-platform
```

---

## Troubleshooting

### Common Issues

#### Pods in CrashLoopBackOff

```bash
# Check logs
kubectl logs <pod-name> -n trading-platform

# Common causes:
# - Missing required secrets (SECRET_KEY, GOOGLE_CLIENT_ID)
# - Database initialization failure
# - Port conflicts
```

#### Ingress Not Working

```bash
# Check ingress status
kubectl describe ingress trading-platform -n trading-platform

# Verify ingress controller is running
kubectl get pods -n ingress-nginx

# Check DNS resolution
nslookup your-domain.com
```

#### Database Errors

```bash
# Check PVC
kubectl get pvc -n trading-platform

# Check volume mount
kubectl describe pod <pod-name> -n trading-platform

# Exec into pod and check database
kubectl exec -it <pod-name> -n trading-platform -- ls -la /data
```

#### Memory/CPU Issues

```bash
# Check resource usage
kubectl top pods -n trading-platform

# Increase resources in values.yaml or deployment.yaml
resources:
  limits:
    cpu: 4000m
    memory: 8Gi
```

### Debug Commands

```bash
# Get all resources
kubectl get all -n trading-platform

# Describe deployment
kubectl describe deployment trading-platform -n trading-platform

# Get events
kubectl get events -n trading-platform --sort-by='.lastTimestamp'

# Exec into pod
kubectl exec -it <pod-name> -n trading-platform -- /bin/bash

# View config
kubectl get configmap trading-platform-config -n trading-platform -o yaml
```

---

## Security Considerations

### Best Practices Implemented

1. **Non-root User**: Application runs as UID 1000
2. **Read-only Filesystem**: Where possible
3. **No Privilege Escalation**: Disabled
4. **Dropped Capabilities**: All unnecessary capabilities dropped
5. **Network Policies**: Define network policies for pod-to-pod communication
6. **Secret Management**: Use external secret managers (Vault, Sealed Secrets)
7. **Image Scanning**: Scan images with Trivy or Snyk before deployment
8. **RBAC**: Implement least-privilege service accounts
9. **TLS/SSL**: Always use HTTPS in production
10. **Rate Limiting**: Enabled via Ingress annotations

### Additional Security Steps

```bash
# Create network policy
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: trading-platform-netpol
  namespace: trading-platform
spec:
  podSelector:
    matchLabels:
      app: trading-platform
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - protocol: TCP
          port: 5000
  egress:
    - {}  # Allow all egress (adjust as needed)
EOF
```

### Secrets Management with Sealed Secrets

```bash
# Install sealed-secrets controller
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/controller.yaml

# Install kubeseal CLI
brew install kubeseal

# Create sealed secret
kubectl create secret generic trading-platform-secret \
  --from-literal=SECRET_KEY='your-secret-key' \
  --dry-run=client -o yaml | \
  kubeseal -o yaml > sealed-secret.yaml

# Apply sealed secret
kubectl apply -f sealed-secret.yaml -n trading-platform
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build and Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build Docker image
        run: docker build -t ${{ secrets.REGISTRY }}/trading-platform:${{ github.sha }} .
      
      - name: Push to registry
        run: |
          echo ${{ secrets.REGISTRY_PASSWORD }} | docker login -u ${{ secrets.REGISTRY_USER }} --password-stdin ${{ secrets.REGISTRY }}
          docker push ${{ secrets.REGISTRY }}/trading-platform:${{ github.sha }}
      
      - name: Deploy to Kubernetes
        uses: azure/k8s-deploy@v4
        with:
          manifests: |
            k8s/deployment.yaml
          images: ${{ secrets.REGISTRY }}/trading-platform:${{ github.sha }}
          namespace: trading-platform
```

---

## Backup and Restore

### Backup Database

```bash
# Create backup
kubectl exec -it deployment/trading-platform -n trading-platform -- \
  tar -czf /tmp/backup.tar.gz /data/financial_analysis.db

# Copy backup locally
kubectl cp trading-platform/<pod-name>:/tmp/backup.tar.gz ./backup-$(date +%Y%m%d).tar.gz
```

### Restore Database

```bash
# Copy backup to pod
kubectl cp ./backup.tar.gz trading-platform/<pod-name>:/tmp/backup.tar.gz

# Restore
kubectl exec -it <pod-name> -n trading-platform -- \
  tar -xzf /tmp/backup.tar.gz -C /
```

---

## Maintenance

### Rolling Updates

```bash
# Update image
kubectl set image deployment/trading-platform \
  trading-platform=your-registry/trading-platform:v2.0.0 \
  -n trading-platform

# Watch rollout
kubectl rollout status deployment/trading-platform -n trading-platform
```

### Rollback

```bash
# Rollback to previous version
kubectl rollout undo deployment/trading-platform -n trading-platform

# Rollback to specific revision
kubectl rollout undo deployment/trading-platform --to-revision=2 -n trading-platform
```

### Cleanup

```bash
# Delete everything
kubectl delete namespace trading-platform

# Or with Helm
helm uninstall trading-platform -n trading-platform
kubectl delete namespace trading-platform
```

---

## Support

For issues and questions:
- GitHub Issues: https://github.com/yourusername/trading-platform/issues
- Documentation: https://docs.yourdomain.com
- Email: support@yourdomain.com

---

## License

Copyright © 2026 Your Company. All rights reserved.

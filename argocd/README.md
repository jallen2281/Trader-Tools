# ArgoCD Deployment

This directory contains ArgoCD Application manifests for GitOps-based continuous deployment.

## Quick Start

### 1. Install ArgoCD on MicroK8s

```bash
# Create namespace
microk8s kubectl create namespace argocd

# Install ArgoCD
microk8s kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ready
microk8s kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd
```

### 2. Access ArgoCD UI

```bash
# Port forward
microk8s kubectl port-forward svc/argocd-server -n argocd 8080:443

# Get admin password
microk8s kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d

# Access at https://localhost:8080
# Username: admin
# Password: (from above command)
```

### 3. Configure Git Repository

Edit the Application manifest to point to your Git repository:

```yaml
# In application.yaml or application-kustomize.yaml
source:
  repoURL: https://github.com/YOUR_USERNAME/YOUR_REPO.git
  targetRevision: main
```

### 4. Create Secrets

Secrets are not stored in Git. Create them manually:

```bash
# Create namespace
microk8s kubectl create namespace trading-platform

# Create from template
cp k8s/secret.yaml.template k8s/secret-local.yaml

# Edit with your values
nano k8s/secret-local.yaml

# Apply (DO NOT commit this file)
microk8s kubectl apply -f k8s/secret-local.yaml
```

### 5. Deploy Application

#### Using Helm Chart (Recommended)
```bash
microk8s kubectl apply -f argocd/application.yaml
```

#### Using Kustomize
```bash
microk8s kubectl apply -f argocd/application-kustomize.yaml
```

### 6. Monitor Deployment

```bash
# Watch sync status
argocd app get trading-platform

# View in UI
# https://localhost:8080/applications/trading-platform

# Watch pods
microk8s kubectl get pods -n trading-platform -w
```

## Application Manifests

### application.yaml
- **Purpose**: Deploys using Helm chart
- **Source Path**: `helm/trading-platform/`
- **Sync Policy**: Automated with self-heal
- **Features**:
  - Auto-sync on Git commits
  - Self-healing on cluster drift
  - Automatic pruning of deleted resources
  - Namespace auto-creation
  - HPA-aware (ignores replica count)

### application-kustomize.yaml
- **Purpose**: Deploys using Kustomize
- **Source Path**: `k8s/`
- **Sync Policy**: Automated with self-heal
- **Features**:
  - Image override for local registry
  - Common labels and annotations
  - Version-pinned Kustomize

## GitOps Workflow

### 1. Make Changes
```bash
# Edit code or configs
vim app.py
vim helm/trading-platform/values.yaml

# Commit changes
git add .
git commit -m "Update feature X"
git push origin main
```

### 2. ArgoCD Auto-Syncs
ArgoCD detects changes and automatically syncs (if automated sync enabled):
- Polls Git repository every 3 minutes (default)
- Compares Git state with cluster state
- Applies differences to cluster
- Self-heals if cluster state drifts

### 3. Monitor Sync
```bash
# CLI
argocd app get trading-platform

# UI
# https://localhost:8080/applications/trading-platform
```

### 4. Rollback if Needed
```bash
# Via ArgoCD UI: Click "History and Rollback"
# Or via CLI:
argocd app rollback trading-platform <revision-number>
```

## Building and Pushing Images

### Automated Image Builds (CI/CD)

Create `.github/workflows/build.yaml`:

```yaml
name: Build and Push

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build image
        run: |
          docker build -t localhost:32000/trading-platform:${{ github.sha }} .
          docker tag localhost:32000/trading-platform:${{ github.sha }} localhost:32000/trading-platform:latest
      
      # For MicroK8s, need to transfer image
      # Option: Use external registry or save/load
```

### Manual Builds

```bash
# Build new version
docker build -t localhost:32000/trading-platform:v1.2.0 .
docker push localhost:32000/trading-platform:v1.2.0

# Update values.yaml
sed -i 's/tag: ".*"/tag: "v1.2.0"/' helm/trading-platform/values.yaml

# Commit and push
git add helm/trading-platform/values.yaml
git commit -m "Update to v1.2.0"
git push

# ArgoCD will auto-sync
```

## ArgoCD CLI Commands

### Application Management
```bash
# List applications
argocd app list

# Get application details
argocd app get trading-platform

# Sync application
argocd app sync trading-platform

# Refresh application (check Git for changes)
argocd app get trading-platform --refresh

# Delete application
argocd app delete trading-platform
```

### Sync Operations
```bash
# Sync specific resource
argocd app sync trading-platform --resource=:Deployment:trading-platform

# Force sync (override)
argocd app sync trading-platform --force

# Dry run sync
argocd app sync trading-platform --dry-run

# Preview sync diff
argocd app diff trading-platform
```

### Rollback Operations
```bash
# List history
argocd app history trading-platform

# Rollback to revision
argocd app rollback trading-platform 3

# Rollback to previous
argocd app rollback trading-platform
```

### Repository Management
```bash
# List repositories
argocd repo list

# Add private repository
argocd repo add https://github.com/YOUR_USERNAME/YOUR_REPO.git \
  --username YOUR_USERNAME \
  --password YOUR_TOKEN

# Add via SSH
argocd repo add git@github.com:YOUR_USERNAME/YOUR_REPO.git \
  --ssh-private-key-path ~/.ssh/id_rsa
```

## Configuration Options

### Sync Policy Options

**Automated Sync**:
```yaml
syncPolicy:
  automated:
    prune: true      # Delete resources removed from Git
    selfHeal: true   # Sync when cluster state changes
    allowEmpty: false # Must have resources to sync
```

**Manual Sync**:
```yaml
syncPolicy:
  automated: null  # Disabled - manual sync only
```

### Sync Options
```yaml
syncOptions:
  - CreateNamespace=true          # Auto-create namespace
  - PrunePropagationPolicy=foreground  # Delete order
  - PruneLast=true                # Delete after sync
  - ApplyOutOfSyncOnly=true       # Only sync changed resources
  - RespectIgnoreDifferences=true # Honor ignore rules
  - Replace=false                 # Use apply, not replace
  - ServerSideApply=false         # Client-side apply
```

### Retry Policy
```yaml
retry:
  limit: 5           # Max retry attempts
  backoff:
    duration: 5s     # Initial wait
    factor: 2        # Exponential multiplier
    maxDuration: 3m  # Max wait time
```

## Ignore Differences

Prevent sync loops by ignoring certain field changes:

```yaml
ignoreDifferences:
  # Ignore HPA-managed replicas
  - group: apps
    kind: Deployment
    jsonPointers:
      - /spec/replicas
  
  # Ignore secrets data (if sealed-secrets used)
  - group: ""
    kind: Secret
    jsonPointers:
      - /data
  
  # Ignore status fields
  - group: "*"
    kind: "*"
    jsonPointers:
      - /status
```

## Private Git Repositories

### HTTPS with Token
```bash
argocd repo add https://github.com/YOUR_USERNAME/YOUR_REPO.git \
  --username YOUR_USERNAME \
  --password ghp_YOUR_GITHUB_TOKEN
```

### SSH Key
```bash
# Generate SSH key (if needed)
ssh-keygen -t ed25519 -C "argocd@trading-platform" -f ~/.ssh/argocd

# Add public key to GitHub: Settings > SSH Keys

# Add to ArgoCD
argocd repo add git@github.com:YOUR_USERNAME/YOUR_REPO.git \
  --ssh-private-key-path ~/.ssh/argocd
```

### Via UI
1. Navigate to Settings > Repositories
2. Click "Connect Repo"
3. Enter repository URL
4. Choose connection method (HTTPS/SSH)
5. Provide credentials
6. Click "Connect"

## Notifications

Set up ArgoCD notifications for sync events:

```bash
# Install notifications controller
microk8s kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj-labs/argocd-notifications/stable/manifests/install.yaml

# Configure Slack/Email/Webhook notifications
# See: https://argocd-notifications.readthedocs.io/
```

## Multi-Environment Setup

Deploy to multiple environments using branches:

```yaml
# Production
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: trading-platform-prod
spec:
  source:
    repoURL: https://github.com/YOUR_USERNAME/YOUR_REPO.git
    targetRevision: main
    path: helm/trading-platform
  destination:
    namespace: trading-platform-prod

---
# Staging
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: trading-platform-staging
spec:
  source:
    repoURL: https://github.com/YOUR_USERNAME/YOUR_REPO.git
    targetRevision: develop
    path: helm/trading-platform
  destination:
    namespace: trading-platform-staging
```

## Troubleshooting

### Application Not Syncing
```bash
# Check sync status
argocd app get trading-platform

# Force refresh
argocd app get trading-platform --refresh --hard-refresh

# Check repository access
argocd repo list
argocd repo get https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

### Sync Failed
```bash
# View sync details
argocd app get trading-platform

# View logs
argocd app logs trading-platform

# Describe specific resource
microk8s kubectl describe deployment/trading-platform -n trading-platform
```

### Out of Sync Status
```bash
# View differences
argocd app diff trading-platform

# Sync specific out-of-sync resources
argocd app sync trading-platform --resource=:Deployment:trading-platform
```

### Repository Connection Failed
```bash
# Test connection
argocd repo get https://github.com/YOUR_USERNAME/YOUR_REPO.git

# Re-add repository with credentials
argocd repo rm https://github.com/YOUR_USERNAME/YOUR_REPO.git
argocd repo add https://github.com/YOUR_USERNAME/YOUR_REPO.git --username USER --password TOKEN
```

## Resources

- [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- [ArgoCD Best Practices](https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/)
- [GitOps Principles](https://www.gitops.tech/)
- [ArgoCD Examples](https://github.com/argoproj/argocd-example-apps)

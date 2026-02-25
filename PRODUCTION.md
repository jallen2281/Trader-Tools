# Production Deployment Guide

Quick guide for deploying to **existing production MicroK8s cluster** with external container registry and ArgoCD.

> **💡 No Docker Installed?** Option A (GitHub Actions) is recommended - it builds images in the cloud automatically!

> **🎯 Management UIs Available:**
> - **ArgoCD UI** - Recommended for GitOps deployment and monitoring (`https://argocd.your-domain.com`)
> - **Portainer** - Alternative for container/cluster management (`https://portainer.your-domain.com`)
> - Both provide visual deployment, monitoring, and log viewing without SSH!

## Prerequisites ✅

- ✓ Production MicroK8s cluster (v1.28+) already running
- ✓ ArgoCD already installed on the cluster
- ✓ External container registry (Docker Hub, GHCR, ECR, etc.)
- ✓ `kubectl` configured OR SSH access to MicroK8s server
- ✓ Docker installed locally for building images
- ✓ Git repository for your code (GitHub, GitLab, Bitbucket)

## 🚀 Deployment Workflow Overview

```
Your Windows Machine          GitHub                    Production MicroK8s
─────────────────────        ────────                  ─────────────────────
                                                       
1. Push code       ──────>   2. GitHub Actions         3. ArgoCD detects
   to Git                       builds container           Git changes
                                image auto-                    │
                                matically                      │
                                    │                          │
                                    │                          ▼
                                    └──────> 4. Pulls image  
                                              and deploys
                                                     
5. Monitor via ArgoCD UI (https://argocd.your-domain.com)
   or Portainer (https://portainer.your-domain.com)
```

**No Docker? No SSH? No problem!** Use ArgoCD UI + GitHub Actions for 100% browser-based deployment.

---

## Step 1: Configure Registry

Update the image registry in deployment manifests:

### Option A: Using Docker Hub

```bash
# 1. Update k8s/deployment.yaml
sed -i 's|docker.io/yourusername|docker.io/YOUR_DOCKERHUB_USERNAME|g' k8s/deployment.yaml

# 2. Update Helm values
sed -i 's|docker.io/yourusername|docker.io/YOUR_DOCKERHUB_USERNAME|g' helm/trader-tools/values.yaml

# 3. Update ArgoCD manifest
sed -i 's|docker.io/yourusername|docker.io/YOUR_DOCKERHUB_USERNAME|g' argocd/application-kustomize.yaml
```

### Option B: Using GitHub Container Registry

```bash
# Use ghcr.io/YOUR_GITHUB_USERNAME/trader-tools:latest
sed -i 's|docker.io/yourusername/trader-tools|ghcr.io/YOUR_GITHUB_USERNAME/trader-tools|g' k8s/deployment.yaml
sed -i 's|docker.io/yourusername/trader-tools|ghcr.io/YOUR_GITHUB_USERNAME/trader-tools|g' helm/trader-tools/values.yaml
```

### Option C: Using Private Registry

```bash
# Use your-registry.com/namespace/trader-tools:latest
REGISTRY="your-registry.com/namespace"
sed -i "s|docker.io/yourusername|$REGISTRY|g" k8s/deployment.yaml
sed -i "s|docker.io/yourusername|$REGISTRY|g" helm/trader-tools/values.yaml
```

## Step 2: Build & Push Container Image

### Option A: Using CI/CD Pipeline (Recommended - No Docker Required)

**GitHub Actions** - Add `.github/workflows/build.yml`:

```yaml
name: Build and Push Container Image

on:
  push:
    branches: [ main, develop ]
    tags: [ 'v*' ]

env:
  REGISTRY: docker.io
  IMAGE_NAME: ${{ github.repository_owner }}/trader-tools

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Log in to Docker Hub
      uses: docker/login-action@v3
      with:
        registry: docker.io
        username: ${{ secrets.DOCKERHUB_USERNAME }}
        password: ${{ secrets.DOCKERHUB_TOKEN }}

    - name: Extract metadata
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
        tags: |
          type=ref,event=branch
          type=ref,event=pr
          type=semver,pattern={{version}}
          type=semver,pattern={{major}}.{{minor}}
          type=sha,prefix={{branch}}-
          type=raw,value=latest,enable={{is_default_branch}}

    - name: Build and push image
      uses: docker/build-push-action@v5
      with:
        context: .
        push: true
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}
```

**Setup:**
1. Go to GitHub Settings → Secrets → Actions
2. Add secrets:
   - `DOCKERHUB_USERNAME`: Your Docker Hub username
   - `DOCKERHUB_TOKEN`: Docker Hub access token (create at hub.docker.com/settings/security)
3. Push code to trigger build:
   ```bash
   git add .
   git commit -m "Add CI/CD workflow"
   git push origin main
   ```

**For GitHub Container Registry (GHCR)** - Change `.github/workflows/build.yml`:
```yaml
env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}  # ghcr.io/username/repo

jobs:
  build:
    steps:
    - name: Log in to GHCR
      uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}  # Automatic, no setup needed
```

### Option B: Using Cloud Build Services (No Docker Required)

**Google Cloud Build:**
```bash
# Install gcloud CLI: https://cloud.google.com/sdk/docs/install

# Build and push (runs in cloud)
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/trader-tools:latest .
```

**Azure Container Registry:**
```bash
# Install Azure CLI: https://aka.ms/azure-cli

# Build and push (runs in cloud)
az acr build --registry YOUR_REGISTRY_NAME \
  --image trader-tools:latest \
  --file Dockerfile .
```

**AWS CodeBuild:**
Create `buildspec.yml`:
```yaml
version: 0.2
phases:
  pre_build:
    commands:
      - echo Logging in to Amazon ECR...
      - aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com
  build:
    commands:
      - echo Building the Docker image...
      - docker build -t trader-tools .
      - docker tag trader-tools:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/trader-tools:latest
  post_build:
    commands:
      - echo Pushing the Docker image...
      - docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/trader-tools:latest
```

### Option C: Using Podman (Docker Alternative)

Podman is a Docker alternative that doesn't require a daemon:

```bash
# Install Podman
# Windows: winget install -e --id RedHat.Podman
# Linux: sudo apt install podman  # or dnf install podman

# Build (same syntax as Docker)
podman build -t docker.io/YOUR_USERNAME/trader-tools:latest .

# Login
podman login docker.io

# Push
podman push docker.io/YOUR_USERNAME/trader-tools:latest
```

### Option D: Using Remote Docker (Another Machine)

If you have access to another machine with Docker:

```bash
# On your local machine, create tar of source
tar -czf trader-tools-src.tar.gz --exclude='.git' --exclude='__pycache__' .

# Copy to remote machine
scp trader-tools-src.tar.gz user@build-server:/tmp/

# SSH to build server
ssh user@build-server

# Extract and build
cd /tmp
tar -xzf trader-tools-src.tar.gz -C trader-tools-build
cd trader-tools-build

# Build and push
docker build -t YOUR_REGISTRY/trader-tools:latest .
docker push YOUR_REGISTRY/trader-tools:latest
```

### Option E: If You Have Docker Installed Locally

<details>
<summary>Click to expand Docker commands</summary>

**Docker Hub:**
```bash
docker login
docker build -t YOUR_DOCKERHUB_USERNAME/trader-tools:latest .
docker push YOUR_DOCKERHUB_USERNAME/trader-tools:latest

# Tag with version (recommended)
docker tag YOUR_DOCKERHUB_USERNAME/trader-tools:latest YOUR_DOCKERHUB_USERNAME/trader-tools:v1.0.0
docker push YOUR_DOCKERHUB_USERNAME/trader-tools:v1.0.0
```

**GitHub Container Registry:**
```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
docker build -t ghcr.io/YOUR_GITHUB_USERNAME/trader-tools:latest .
docker push ghcr.io/YOUR_GITHUB_USERNAME/trader-tools:latest
```

**Private Registry:**
```bash
docker login your-registry.com
docker build -t your-registry.com/namespace/trader-tools:latest .
docker push your-registry.com/namespace/trader-tools:latest
```

</details>

## Step 3: Push Code to Git Repository

ArgoCD needs your manifests in a Git repository:

```bash
# Initialize git if not already done
git init
git add .
git commit -m "Add deployment manifests"

# Add remote and push
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

## Step 4: Configure ArgoCD Application

Update the ArgoCD Application manifest with your Git repository:

```yaml
# Edit argocd/application.yaml
# Change these lines:
  source:
    repoURL: https://github.com/YOUR_USERNAME/YOUR_REPO.git  # Your repository
    targetRevision: main
    path: helm/trader-tools
    
    helm:
      values: |
        image:
          repository: YOUR_REGISTRY/trader-tools  # Your registry
          tag: "latest"  # or specific version like v1.0.0
```

or for Kustomize deployment:

```yaml
# Edit argocd/application-kustomize.yaml
  source:
    repoURL: https://github.com/YOUR_USERNAME/YOUR_REPO.git
    targetRevision: main
    path: k8s
    
    kustomize:
      images:
        - name: trader-tools
          newName: YOUR_REGISTRY/trader-tools
          newTag: latest
```

## Step 5: Create Kubernetes Secrets

### Option A: From Production MicroK8s Server (SSH)

```bash
# SSH to your MicroK8s server
ssh user@your-production-server

# Create secrets
microk8s kubectl create namespace trader-tools

microk8s kubectl create secret generic trader-tools-secret \
  --from-literal=SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  --from-literal=GOOGLE_CLIENT_ID="your-google-client-id" \
  --from-literal=GOOGLE_CLIENT_SECRET="your-google-client-secret" \
  --from-literal=ALPHA_VANTAGE_API_KEY="your-alpha-vantage-key" \
  --from-literal=NEWS_API_KEY="your-news-api-key" \
  --from-literal=QUANDL_API_KEY="your-quandl-api-key" \
  --namespace trader-tools
```

### Option B: From Local kubectl (if configured)

```bash
# Create namespace
kubectl create namespace trader-tools

# Create secrets
kubectl create secret generic trader-tools-secret \
  --from-literal=SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  --from-literal=GOOGLE_CLIENT_ID="your-google-client-id" \
  --from-literal=GOOGLE_CLIENT_SECRET="your-google-client-secret" \
  --from-literal=ALPHA_VANTAGE_API_KEY="your-alpha-vantage-key" \
  --from-literal=NEWS_API_KEY="your-news-api-key" \
  --from-literal=QUANDL_API_KEY="your-quandl-api-key" \
  --namespace trader-tools
```

### Option C: Using CI/CD Pipeline

Add to your CI/CD pipeline (GitHub Actions, GitLab CI, Jenkins):

```yaml
# Example: GitHub Actions
- name: Create Kubernetes secrets
  run: |
    echo "${{ secrets.KUBECONFIG }}" > kubeconfig
    export KUBECONFIG=kubeconfig
    
    kubectl create namespace trader-tools --dry-run=client -o yaml | kubectl apply -f -
    
    kubectl create secret generic trader-tools-secret \
      --from-literal=SECRET_KEY="${{ secrets.SECRET_KEY }}" \
      --from-literal=GOOGLE_CLIENT_ID="${{ secrets.GOOGLE_CLIENT_ID }}" \
      --from-literal=GOOGLE_CLIENT_SECRET="${{ secrets.GOOGLE_CLIENT_SECRET }}" \
      --namespace trader-tools \
      --dry-run=client -o yaml | kubectl apply -f -
```

## Step 6: Deploy with ArgoCD

### Option A: Using ArgoCD UI (Recommended - Easiest)

1. Open ArgoCD UI in your browser: `https://argocd.your-domain.com`
2. Log in with your ArgoCD credentials
3. Click **+ NEW APP** or **Create Application**
4. Configure the application:
   - **Application Name**: `trader-tools`
   - **Project**: `default`
   - **Sync Policy**: `Automatic`
     - ✔️ Enable **Auto-Sync**
     - ✔️ Enable **Self Heal**
     - ✔️ Enable **Prune Resources**
   - **Source**:
     - **Repository URL**: `https://github.com/YOUR_USERNAME/YOUR_REPO.git`
     - **Revision**: `main` or `HEAD`
     - **Path**: `helm/trader-tools` (for Helm) or `k8s` (for Kustomize)
   - **Destination**:
     - **Cluster URL**: `https://kubernetes.default.svc`
     - **Namespace**: `trader-tools`
   - **Helm** (if using Helm path):
     - Add values overrides if needed
5. Click **CREATE**
6. Watch the sync progress in real-time!
7. Click on resources to view logs, events, and details

### Option B: Using ArgoCD CLI

```bash
# SSH to MicroK8s server or use kubectl port-forward
ssh user@your-production-server

# Apply the Application manifest
microk8s kubectl apply -f argocd/application.yaml
```

### Option C: Using kubectl Locally

```bash
# Apply ArgoCD Application manifest
kubectl apply -f argocd/application.yaml

# Watch deployment
kubectl get applications -n argocd
argocd app get trader-tools
```

### Option D: Using Portainer UI (Alternative)

If you prefer Portainer for management:

1. Open Portainer UI: `https://portainer.your-domain.com`
2. Navigate to your MicroK8s cluster endpoint
3. Go to **Namespaces** → Create namespace `trader-tools`
4. Go to **Custom Templates** or **Stacks**
5. Create stack:
   - From Git repository (connect to your repo)
   - Or paste Kubernetes manifests directly
6. Deploy and monitor through Portainer dashboard
7. Use Portainer's built-in log viewer and shell access

## Step 7: Verify Deployment

### Via ArgoCD UI (Easiest)

1. Open ArgoCD UI: `https://argocd.your-domain.com`
2. Click on your `trader-tools` application
3. View the **Application Details** page:
   - **Sync Status**: Should show "Synced"
   - **Health Status**: Should show "Healthy"
   - **Resource Tree**: Visual view of all deployed resources
4. Click on individual resources (Deployments, Pods, Services) to:
   - View logs directly in the UI
   - Check events and status
   - See resource manifests
5. Use **App Diff** to see what changed

### Via Portainer UI (Alternative)

1. Open Portainer: `https://portainer.your-domain.com`
2. Go to your cluster → Namespaces → `trader-tools`
3. View:
   - **Applications**: See running pods and their status
   - **Services**: Check exposed services
   - **Ingresses**: View ingress rules
   - **Volumes**: Check PVC status
4. Click on pods to view logs or open a console

### Via SSH/kubectl

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Check ArgoCD Application status
microk8s kubectl get application trader-tools -n argocd

# Check pods
microk8s kubectl get pods -n trader-tools

# Check services
microk8s kubectl get svc -n trader-tools

# Check ingress
microk8s kubectl get ingress -n trader-tools

# View logs
microk8s kubectl logs -n trader-tools -l app=trader-tools --tail=100

# Test health endpoint (on MicroK8s server)
microk8s kubectl port-forward -n trader-tools svc/trader-tools 8080:80
# Then from another terminal: curl http://localhost:8080/health
```

## Step 8: Configure Ingress/Domain

Update your DNS to point to your MicroK8s cluster ingress IP:

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Get ingress IP
microk8s kubectl get ingress -n trader-tools

# Example output:
# NAME                CLASS   HOSTS                    ADDRESS        PORTS
# trader-tools    nginx   trading.yourdomain.com   192.168.1.100  80, 443
```

Add DNS A record:
```
trading.yourdomain.com → 192.168.1.100
```

## Deployment Methods Comparison

| Method | Use Case | Pros | Cons |
|--------|----------|------|------|
| **ArgoCD Helm** | Production (recommended) | GitOps, auto-sync, easy rollbacks, monitoring | Requires Git repo |
| **ArgoCD Kustomize** | Production (simpler configs) | GitOps, lightweight, overlays | Less templating power |
| **Direct Helm** | Quick production deploy | Fast, flexible | No GitOps benefits |
| **Direct kubectl** | Testing, simple deploys | Simple, no dependencies | Manual updates |

## Updates & Rollbacks

### Update Application (GitOps Way)

```bash
# 1. Build new image
docker build -t YOUR_REGISTRY/trader-tools:v1.1.0 .
docker push YOUR_REGISTRY/trader-tools:v1.1.0

# 2. Update manifest in Git
# Update image tag in argocd/application.yaml or helm values
git commit -am "Update to v1.1.0"
git push

# 3. ArgoCD auto-syncs within 3 minutes (or manual sync)
argocd app sync trader-tools
```

### Rollback

```bash
# Using ArgoCD
argocd app rollback trader-tools

# Or revert Git commit
git revert HEAD
git push
```

## Monitoring

### Via ArgoCD UI

1. Open ArgoCD UI: `https://argocd.your-domain.com`
2. View **Applications** dashboard
3. Click on `trader-tools` to see:
   - Real-time sync status
   - Health of all resources
   - Recent sync history
   - Application events
4. Use **Sync Status** to see out-of-sync resources
5. View **Logs** tab for pod logs
6. Check **Events** for Kubernetes events

### Via Portainer UI

1. Open Portainer: `https://portainer.your-domain.com`
2. Dashboard shows cluster resource usage
3. Navigate to namespace for detailed pod metrics
4. View container logs in real-time
5. Monitor resource consumption graphs
6. Set up alerts for pod failures

### Via SSH/kubectl

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Check application health (requires argocd CLI)
argocd app get trader-tools

# Watch sync status
argocd app wait trader-tools --timeout 300

# View logs
microk8s kubectl logs -n trader-tools -l app=trader-tools -f

# Check metrics (if metrics-server enabled)
microk8s kubectl top pods -n trader-tools
microk8s kubectl top nodes
```

## Troubleshooting

### Image Pull Failures

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Check if secret is needed for private registry
microk8s kubectl create secret docker-registry regcred \
  --docker-server=your-registry.com \
  --docker-username=your-username \
  --docker-password=your-password \
  --namespace trader-tools

# Add to deployment
microk8s kubectl patch deployment trader-tools -n trader-tools \
  -p '{"spec":{"template":{"spec":{"imagePullSecrets":[{"name":"regcred"}]}}}}'
```

### ArgoCD Not Syncing

**Via ArgoCD UI (Easiest):**
1. Open ArgoCD UI and navigate to your application
2. Click **REFRESH** button (force refresh from Git)
3. Click **SYNC** button to manually trigger sync
4. Check **App Details** panel for sync errors
5. View **Events** tab for detailed error messages
6. Use **App Diff** to see what will change
7. Check **Parameters** tab to verify Helm values/Kustomize settings

**Via kubectl:**
```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Check Application status
microk8s kubectl describe application trader-tools -n argocd

# Force refresh (requires argocd CLI)
argocd app get trader-tools --refresh

# Manual sync
argocd app sync trader-tools --force

# Check ArgoCD logs
microk8s kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller
```

### Pod CrashLoops

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Check pod logs
microk8s kubectl logs -n trader-tools -l app=trader-tools --previous

# Check events
microk8s kubectl describe pod -n trader-tools -l app=trader-tools

# Verify secrets exist
microk8s kubectl get secret trader-tools-secret -n trader-tools

# Check configmap
microk8s kubectl get configmap trader-tools-config -n trader-tools
```

### Database Issues

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Check PVC
microk8s kubectl get pvc -n trader-tools

# Check PVC mount
microk8s kubectl exec -n trader-tools deployment/trader-tools -- ls -la /data

# Reinitialize database (careful in production!)
microk8s kubectl exec -n trader-tools deployment/trader-tools -- python -c "
from db_config import init_database
from flask import Flask
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////data/financial_analysis.db'
init_database(app)
"
```

## Security Considerations

1. **Secrets Management**: Never commit secrets to Git
   ```bash
   # Verify secrets not in repo
   git log --all --full-history --source --show-pulls -- k8s/secret.yaml
   ```

2. **Image Scanning**: Scan images before deployment
   ```bash
   docker scan YOUR_REGISTRY/trader-tools:latest
   ```

3. **Network Policies**: Restrict pod communication (add to k8s/)
   ```yaml
   apiVersion: networking.k8s.io/v1
   kind: NetworkPolicy
   metadata:
     name: trader-tools-netpol
     namespace: trader-tools
   spec:
     podSelector:
       matchLabels:
         app: trader-tools
     policyTypes:
     - Ingress
     - Egress
     ingress:
     - from:
       - namespaceSelector:
           matchLabels:
             name: ingress-nginx
     egress:
     - to:
       - namespaceSelector: {}
       ports:
       - protocol: TCP
         port: 443
       - protocol: TCP
         port: 80
   ```

4. **RBAC**: Limit ArgoCD permissions (production)
   ```bash
   # SSH to your Ubuntu MicroK8s server
   ssh user@your-microk8s-server
   
   # Create limited service account for ArgoCD
   microk8s kubectl create sa trader-tools-deployer -n trader-tools
   microk8s kubectl create rolebinding trader-tools-deployer \
     --clusterrole=edit \
     --serviceaccount=trader-tools:trader-tools-deployer \
     --namespace=trader-tools
   ```

## Scaling

### Manual Scaling

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Scale replicas
microk8s kubectl scale deployment trader-tools -n trader-tools --replicas=5

# Or update in Git for GitOps (recommended)
# Edit helm/trader-tools/values.yaml or k8s/deployment.yaml
# Commit and push - ArgoCD will sync automatically
```

### Auto-Scaling (HPA already configured)

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Check HPA status
microk8s kubectl get hpa -n trader-tools

# View metrics
microk8s kubectl top pods -n trader-tools
```

### Vertical Scaling (Resource Limits)

Update `helm/trader-tools/values.yaml`:
```yaml
resources:
  limits:
    cpu: 4000m
    memory: 4Gi
  requests:
    cpu: 1000m
    memory: 2Gi
```

Commit, push, and ArgoCD will sync.

## Backup & Disaster Recovery

### Backup SQLite Database

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Create backup job (if CronJob exists)
microk8s kubectl create job --from=cronjob/backup-db backup-manual -n trader-tools

# Or manual backup
microk8s kubectl exec -n trader-tools deployment/trader-tools -- \
  sqlite3 /data/financial_analysis.db ".backup /data/backup.db"

# Copy to local (from MicroK8s server to your local machine)
microk8s kubectl cp trader-tools/trader-tools-<pod-id>:/data/backup.db ./backup.db

# Or copy from server to your Windows machine
# On your local Windows machine:
scp user@your-microk8s-server:~/backup.db .
```

### Restore from Backup

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Copy backup to pod (get exact pod name first)
POD_NAME=$(microk8s kubectl get pods -n trader-tools -l app=trader-tools -o jsonpath='{.items[0].metadata.name}')
microk8s kubectl cp ./backup.db trader-tools/$POD_NAME:/data/financial_analysis.db

# Restart pod
microk8s kubectl rollout restart deployment/trader-tools -n trader-tools
```

## Next Steps

- ✅ Configure monitoring with Prometheus/Grafana
- ✅ Set up log aggregation (ELK/Loki)
- ✅ Configure alerting (AlertManager)
- ✅ Implement database backups (CronJob)
- ✅ Set up SSL/TLS with cert-manager
- ✅ Configure rate limiting
- ✅ Add health check monitoring
- ✅ Implement disaster recovery plan

## 🎛️ Management Tools Best Practices

Your production MicroK8s cluster provides multiple management interfaces. Here's when to use each:

### ArgoCD UI (`https://argocd.your-domain.com`)
**Use for:**
- ✅ **Deploying applications** - Visual, intuitive application creation
- ✅ **Monitoring GitOps sync status** - Real-time sync and health indicators
- ✅ **Troubleshooting deployments** - View sync errors, app diffs, and resource trees
- ✅ **Rolling back changes** - One-click rollback to previous versions
- ✅ **Viewing deployment history** - Complete audit trail of changes

**Best for:** Application lifecycle management, GitOps workflows

### Portainer (`https://portainer.your-domain.com`)
**Use for:**
- ✅ **Day-to-day monitoring** - Dashboard overview of cluster health
- ✅ **Viewing logs** - Easy log access without kubectl
- ✅ **Pod console access** - Built-in terminal for debugging
- ✅ **Resource usage monitoring** - CPU/memory graphs and metrics
- ✅ **Quick inspections** - Fast pod/service status checks

**Best for:** Operations, monitoring, troubleshooting

### kubectl via SSH
**Use for:**
- ✅ **Automation and scripting** - CI/CD pipelines
- ✅ **Advanced operations** - Complex kubectl commands
- ✅ **Bulk operations** - Managing multiple resources at once
- ✅ **Custom queries** - JSONPath, label selectors, etc.

**Best for:** Power users, automation, scripting

### Recommended Workflow

1. **Deploy**: Use **ArgoCD UI** to create and deploy applications
2. **Monitor**: Use **Portainer** for daily health checks and log viewing
3. **Update**: Push to Git → **ArgoCD** auto-syncs → Monitor in **ArgoCD UI**
4. **Debug**: Use **Portainer** for logs and console access
5. **Automate**: Use **kubectl/SSH** for scripts and CI/CD
6. **Rollback**: Use **ArgoCD UI** for one-click rollbacks

### Quick Access URLs

Add these to your bookmarks:

```
ArgoCD:    https://argocd.your-domain.com
Portainer: https://portainer.your-domain.com
Your App:  https://trading.your-domain.com
```

### Tips

- 💡 **Enable ArgoCD notifications** to get Slack/email alerts on sync failures
- 💡 **Use Portainer teams** to control user access to namespaces
- 💡 **Bookmark ArgoCD app pages** for quick access to your applications
- 💡 **Use ArgoCD CLI** for advanced operations (install: `brew install argocd` or download from releases)
- 💡 **Set up Portainer webhooks** for automated deployments from external CI/CD

## Support

For detailed documentation on all deployment methods, see:
- [DEPLOYMENT.md](DEPLOYMENT.md) - Comprehensive deployment guide
- [QUICKSTART.md](QUICKSTART.md) - Quick reference commands
- [argocd/README.md](argocd/README.md) - ArgoCD-specific guide

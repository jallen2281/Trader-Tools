# Quick Start - No Docker Required

This guide is for deploying to production MicroK8s **without Docker installed locally**.

## ⚡ Fastest Path (GitHub Container Registry)

### Step 1: Enable GitHub Actions Workflow

```bash
# Remove Docker Hub workflow (uses GHCR instead)
rm .github/workflows/build.yml

# GHCR workflow (.github/workflows/build-ghcr.yml) is ready to use!
```

### Step 2: Push Code to GitHub

```bash
# If not already a git repo
git init

# Add all files
git add .
git commit -m "Initial commit with deployment configs"

# Create repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git push -u origin main
```

**✅ GitHub Actions will automatically build and push your image to GHCR!**

Check build status: Go to your GitHub repo → **Actions** tab

### Step 3: Update Deployment Manifests

Your image will be at: `ghcr.io/YOUR_USERNAME/YOUR_REPO:latest`

Update the manifests:

```bash
# Windows PowerShell
$REGISTRY = "ghcr.io/YOUR_USERNAME/YOUR_REPO"
(Get-Content k8s/deployment.yaml) -replace 'docker.io/yourusername/trading-platform', $REGISTRY | Set-Content k8s/deployment.yaml
(Get-Content helm/trading-platform/values.yaml) -replace 'docker.io/yourusername/trading-platform', $REGISTRY | Set-Content helm/trading-platform/values.yaml
(Get-Content argocd/application-kustomize.yaml) -replace 'docker.io/yourusername/trading-platform', $REGISTRY | Set-Content argocd/application-kustomize.yaml

# Commit changes
git add .
git commit -m "Update registry to GHCR"
git push
```

### Step 4: Create Secrets on Production Cluster

SSH to your MicroK8s server or use kubectl locally:

```bash
# Create namespace
kubectl create namespace trading-platform

# Generate secret key
$SECRET_KEY = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})

# Create secret
kubectl create secret generic trading-platform-secret `
  --from-literal=SECRET_KEY="$SECRET_KEY" `
  --from-literal=GOOGLE_CLIENT_ID="your-google-client-id" `
  --from-literal=GOOGLE_CLIENT_SECRET="your-google-client-secret" `
  --namespace trading-platform
```

### Step 5: Update ArgoCD Application

Edit `argocd/application.yaml`:

```yaml
source:
  repoURL: https://github.com/YOUR_USERNAME/YOUR_REPO.git  # Your repo
  targetRevision: main
  path: helm/trading-platform
  
  helm:
    values: |
      image:
        repository: ghcr.io/YOUR_USERNAME/YOUR_REPO  # Your image
        tag: "latest"
```

Commit and push:

```bash
git add argocd/application.yaml
git commit -m "Configure ArgoCD for production"
git push
```

### Step 6: Deploy with ArgoCD

```bash
# Apply ArgoCD Application
kubectl apply -f argocd/application.yaml

# Watch deployment
kubectl get application trading-platform -n argocd -w

# Check pods
kubectl get pods -n trading-platform

# View logs
kubectl logs -n trading-platform -l app=trading-platform -f
```

### Step 7: Access Your Application

```bash
# Get ingress URL
kubectl get ingress -n trading-platform

# Or port-forward for testing
kubectl port-forward -n trading-platform svc/trading-platform 8080:80
```

Access at: `http://localhost:8080` (if port-forwarding) or your ingress domain.

---

## 🔄 Making Updates

Every time you push to GitHub:

1. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Update feature X"
   git push
   ```

2. **GitHub Actions builds new image automatically**

3. **ArgoCD syncs within 3 minutes** (or manual sync):
   ```bash
   kubectl patch application trading-platform -n argocd \
     --type merge \
     -p '{"operation":{"initiatedBy":{"username":"manual"},"sync":{"syncStrategy":{}}}}'
   ```

---

## 📦 Alternative: Docker Hub with GitHub Actions

If you prefer Docker Hub:

### Step 1: Create Docker Hub Token

1. Go to https://hub.docker.com/settings/security
2. Click **New Access Token**
3. Name: `GitHub Actions`
4. Copy the token

### Step 2: Add GitHub Secrets

1. Go to your GitHub repo → Settings → Secrets → Actions
2. Click **New repository secret**
3. Add:
   - Name: `DOCKERHUB_USERNAME`, Value: your Docker Hub username
   - Name: `DOCKERHUB_TOKEN`, Value: your access token

### Step 3: Enable Docker Hub Workflow

```bash
# Remove GHCR workflow
rm .github/workflows/build-ghcr.yml

# Docker Hub workflow (.github/workflows/build.yml) is ready!
```

### Step 4: Update Manifests

```bash
# Windows PowerShell
$REGISTRY = "docker.io/YOUR_DOCKERHUB_USERNAME/trading-platform"
(Get-Content k8s/deployment.yaml) -replace 'docker.io/yourusername/trading-platform', $REGISTRY | Set-Content k8s/deployment.yaml
(Get-Content helm/trading-platform/values.yaml) -replace 'docker.io/yourusername/trading-platform', $REGISTRY | Set-Content helm/trading-platform/values.yaml
```

### Step 5: Push and Deploy

```bash
git add .
git commit -m "Configure Docker Hub registry"
git push

# Continue with Steps 4-7 from above
```

---

## 🛠️ Troubleshooting

### "Failed to pull image"

**For GHCR private images**, create pull secret:

```bash
# Create GitHub PAT at https://github.com/settings/tokens
# Scopes needed: read:packages

kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USERNAME \
  --docker-password=YOUR_GITHUB_TOKEN \
  --namespace trading-platform

# Patch deployment
kubectl patch serviceaccount default -n trading-platform \
  -p '{"imagePullSecrets":[{"name":"ghcr-secret"}]}'
```

**Or make image public:**
1. Go to https://github.com/users/YOUR_USERNAME/packages
2. Find your package → Package settings
3. Change visibility to Public

### "GitHub Actions build failing"

Check the Actions tab for detailed logs. Common issues:
- Dockerfile syntax errors
- Missing dependencies in requirements.txt
- Wrong permissions (check workflow has `packages: write`)

### "ArgoCD not syncing"

```bash
# Force refresh
kubectl patch application trading-platform -n argocd --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'

# Check Application status
kubectl describe application trading-platform -n argocd

# View ArgoCD logs
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller
```

---

## 📚 More Information

- [PRODUCTION.md](PRODUCTION.md) - Complete production deployment guide
- [.github/workflows/README.md](.github/workflows/README.md) - GitHub Actions workflows details
- [DEPLOYMENT.md](DEPLOYMENT.md) - Comprehensive deployment documentation
- [QUICKSTART.md](QUICKSTART.md) - Quick command reference

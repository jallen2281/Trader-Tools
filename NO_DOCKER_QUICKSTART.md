# Quick Start - No Docker Required

This guide is for deploying to production MicroK8s **without Docker installed locally**.

> **🎯 Your Production Cluster Has:**
> - ✅ **ArgoCD UI** - Use for visual GitOps deployment (easiest!)
> - ✅ **Portainer** - Alternative UI for cluster management
> - ✅ Both eliminate the need for SSH/kubectl in most cases!

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
# Set your registry
REGISTRY="ghcr.io/jallen2281/Trader-Tools:latest"

# Update manifests (Linux/macOS)
sed -i "s|docker.io/yourusername/trader-tools|$REGISTRY|g" k8s/deployment.yaml
sed -i "s|docker.io/yourusername/trader-tools|$REGISTRY|g" helm/trader-tools/values.yaml
sed -i "s|docker.io/yourusername/trader-tools|$REGISTRY|g" argocd/application-kustomize.yaml

# Commit changes
git add .
git commit -m "Update registry to GHCR"
git push
```

### Step 4: Configure Secrets

**IMPORTANT:** The Helm chart creates secrets automatically. You have two options:

#### Option A: Pass Secrets via ArgoCD (Recommended for GitOps)

Edit `argocd/application.yaml` and update the secrets section:

```yaml
values: |
  secrets:
    secretKey: "your-generated-secret-key-here"  # Generate with: python3 -c 'import secrets; print(secrets.token_hex(32))'
    googleClientId: "your-google-client-id"
    googleClientSecret: "your-google-client-secret"
    databaseUrl: "sqlite:////data/financial_analysis.db"
```

Then commit and push:
```bash
git add argocd/application.yaml
git commit -m "Configure production secrets"
git push
```

**⚠️ Security Warning:** Secrets in Git are not ideal for production. See Option B below for better security.

#### Option B: Use External Secrets (More Secure)

Create a separate Kubernetes secret that Helm will use:

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Create namespace first
microk8s kubectl create namespace trader-tools

# Generate secret key
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

# Create secret with the EXACT name Helm expects
microk8s kubectl create secret generic trader-tools \
  --from-literal=SECRET_KEY="$SECRET_KEY" \
  --from-literal=GOOGLE_CLIENT_ID="your-google-client-id" \
  --from-literal=GOOGLE_CLIENT_SECRET="your-google-client-secret" \
  --from-literal=DATABASE_URL="sqlite:////data/financial_analysis.db" \
  --from-literal=OLLAMA_BASE_URL="http://localhost:11434" \
  --namespace trader-tools
```

Then comment out the secrets in `argocd/application.yaml`:

```yaml
values: |
  # secrets:  # Using pre-created Kubernetes secret instead
  #   secretKey: ""
```

**Note:** The secret name MUST be `trader-tools` (not `trader-tools-secret`) because that's what the Helm chart expects.

### Step 5: Update ArgoCD Application for Your Environment

Edit `argocd/application.yaml` to configure for production:

```yaml
source:
  repoURL: https://github.com/jallen2281/Trader-Tools.git  # Your repo
  targetRevision: master  # Your branch
  path: helm/trader-tools
  
  helm:
    values: |
      image:
        repository: ghcr.io/jallen2281/trader-tools  # Your image
        tag: "latest"
      
      ingress:
        hosts:
          - host: tradertools.kegbot.net  # Your domain
        tls:
          - secretName: trader-tools-tls
            hosts:
              - tradertools.kegbot.net
      
      # If using Option A from Step 4, add secrets here
      secrets:
        secretKey: "your-generated-secret"
        googleClientId: "your-client-id"
        googleClientSecret: "your-client-secret"
```

Commit and push:

```bash
git add argocd/application.yaml
git commit -m "Configure ArgoCD for production"
git push
```

### Step 6: Deploy with ArgoCD

#### Option A: Using ArgoCD UI (Easiest)

1. Open ArgoCD UI in your browser: `https://argocd.your-domain.com`
2. Log in with your credentials
3. Click **+ NEW APP** or **+ Create Application**
4. Fill in the application details:
   - **Application Name**: `trader-tools`
   - **Project**: `default`
   - **Sync Policy**: Select `Automatic` (enable auto-sync, self-heal, prune)
   - **Repository URL**: `https://github.com/YOUR_USERNAME/YOUR_REPO.git`
   - **Revision**: `main` (or `HEAD`)
   - **Path**: `helm/trader-tools` (or `k8s` for Kustomize)
   - **Cluster URL**: `https://kubernetes.default.svc`
   - **Namespace**: `trader-tools`
5. Click **CREATE**
6. Watch the application sync in real-time!

#### Option B: Using kubectl (SSH to server)

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Apply ArgoCD Application manifest
microk8s kubectl apply -f argocd/application.yaml

# Watch deployment
microk8s kubectl get application trader-tools -n argocd -w

# Check pods
microk8s kubectl get pods -n trader-tools

# View logs
microk8s kubectl logs -n trader-tools -l app=trader-tools -f
```

#### Option C: Using Portainer (Alternative UI)

If you prefer Portainer:

1. Open Portainer UI: `https://portainer.your-domain.com`
2. Navigate to your MicroK8s cluster
3. Go to **Namespaces** → Create namespace `trader-tools`
4. Go to **Custom Templates** or **Stacks**
5. Create new stack from Git repository or paste manifests
6. Deploy and monitor through Portainer UI

### Step 7: Access Your Application

#### Monitor Deployment via ArgoCD UI

1. Open ArgoCD UI: `https://argocd.your-domain.com`
2. View your `trader-tools` application
3. See real-time sync status, health, and resource tree
4. Click on pods to view logs directly in the UI

#### Monitor via Portainer UI

1. Open Portainer: `https://portainer.your-domain.com`
2. Navigate to your cluster → Namespaces → `trader-tools`
3. View pods, services, and resource usage
4. Access logs and shell directly from UI

#### Access via SSH/kubectl

```bash
# SSH to your Ubuntu MicroK8s server
ssh user@your-microk8s-server

# Get ingress URL
microk8s kubectl get ingress -n trader-tools

# Or port-forward for testing (accessible from server only)
microk8s kubectl port-forward -n trader-tools svc/trader-tools 8080:80
```

**Access your application** at the ingress URL or configured domain.

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

3. **ArgoCD syncs within 3 minutes** (or view/trigger in UI):
   - **ArgoCD UI**: Click **SYNC** button or wait for auto-sync
   - **Or via kubectl**:
     ```bash
     # SSH to MicroK8s server
     microk8s kubectl patch application trader-tools -n argocd \
       --type merge \
       -p '{"operation":{"initiatedBy":{"username":"manual"},"sync":{"syncStrategy":{}}}}'
     ```

4. **Monitor in ArgoCD UI** or **Portainer** to watch rollout progress

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
# Set your registry
REGISTRY="docker.io/YOUR_DOCKERHUB_USERNAME/trader-tools"

# Update manifests (Linux/macOS)
sed -i "s|docker.io/yourusername/trader-tools|$REGISTRY|g" k8s/deployment.yaml
sed -i "s|docker.io/yourusername/trader-tools|$REGISTRY|g" helm/trader-tools/values.yaml
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

### "ArgoCD isn't using the secret"

**Symptom:** Pods fail with missing environment variables

**Cause:** The Helm chart creates its own secret named `trader-tools`, but you may have manually created `trader-tools-secret`

**Solution:**
```bash
# SSH to MicroK8s server
ssh user@your-microk8s-server

# Delete incorrectly named secret
microk8s kubectl delete secret trader-tools-secret -n trader-tools

# Option 1: Pass secrets via ArgoCD application.yaml (see Step 4, Option A)
# Option 2: Create secret with correct name
microk8s kubectl create secret generic trader-tools \
  --from-literal=SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  --from-literal=GOOGLE_CLIENT_ID="your-id" \
  --from-literal=GOOGLE_CLIENT_SECRET="your-secret" \
  --from-literal=DATABASE_URL="sqlite:////data/financial_analysis.db" \
  --namespace trader-tools

# Then disable secret creation in Helm
# Edit argocd/application.yaml and remove/comment the secrets: section
```

Verify the secret exists:
```bash
microk8s kubectl get secret trader-tools -n trader-tools -o yaml
```

### "Failed to pull image"

**For GHCR private images**, create pull secret:

```bash
# SSH to MicroK8s server
ssh user@your-microk8s-server

# Create GitHub PAT at https://github.com/settings/tokens
# Scopes needed: read:packages

microk8s kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USERNAME \
  --docker-password=YOUR_GITHUB_TOKEN \
  --namespace trader-tools

# Patch deployment
microk8s kubectl patch serviceaccount default -n trader-tools \
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

**Via ArgoCD UI:**
1. Open ArgoCD UI
2. Click on your application
3. Click **REFRESH** button (hard refresh)
4. Click **SYNC** button if needed
5. Check **App Details** for error messages

**Via kubectl:**
```bash
# SSH to MicroK8s server
ssh user@your-microk8s-server

# Force refresh
microk8s kubectl patch application trader-tools -n argocd --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'

# Check Application status
microk8s kubectl describe application trader-tools -n argocd

# View ArgoCD logs
microk8s kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller
```

---

## 🎛️ Management Tools Summary

Your production MicroK8s cluster provides these management interfaces:

### ArgoCD UI (Recommended for GitOps)
- **URL**: `https://argocd.your-domain.com`
- **Use for**:
  - Creating and managing applications
  - Monitoring sync status and health
  - Viewing deployment history and rollbacks
  - Triggering manual syncs
  - Viewing logs and events
  - Comparing Git vs deployed state

### Portainer (Alternative Management)
- **URL**: `https://portainer.your-domain.com`
- **Use for**:
  - Cluster resource overview
  - Creating namespaces and resources
  - Viewing pod logs and metrics
  - Opening pod shells/consoles
  - Managing volumes and configs
  - Resource usage monitoring

### kubectl via SSH (Power Users)
- Best for automation, scripting, and advanced operations
- Use when UI doesn't provide needed functionality

**💡 Tip**: Start with ArgoCD UI for deployment, then use Portainer for day-to-day monitoring and log viewing!

---

## 📚 More Information

- [PRODUCTION.md](PRODUCTION.md) - Complete production deployment guide
- [.github/workflows/README.md](.github/workflows/README.md) - GitHub Actions workflows details
- [DEPLOYMENT.md](DEPLOYMENT.md) - Comprehensive deployment documentation
- [QUICKSTART.md](QUICKSTART.md) - Quick command reference

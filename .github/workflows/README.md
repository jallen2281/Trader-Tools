# GitHub Actions Workflows

This directory contains CI/CD workflows for building and pushing container images.

## Available Workflows

### 1. `build.yml` - Docker Hub Build (Requires Secrets)

Builds and pushes images to Docker Hub (`docker.io/username/trader-tools`).

**Setup:**
1. Create Docker Hub access token at https://hub.docker.com/settings/security
2. Go to GitHub repo → Settings → Secrets and variables → Actions
3. Add secrets:
   - `DOCKERHUB_USERNAME`: Your Docker Hub username
   - `DOCKERHUB_TOKEN`: Your Docker Hub access token

**To enable:** Rename `build.yml` to `build.yml.disabled` if you want to use GHCR instead.

### 2. `build-ghcr.yml` - GitHub Container Registry (No Setup Required)

Builds and pushes images to GitHub Container Registry (`ghcr.io/username/repo-name`).

**Setup:** None! Uses automatic `GITHUB_TOKEN`.

**To enable:** This is the **recommended** option if you don't want to manage secrets.

## Usage

Both workflows trigger automatically on:
- **Push to `main` branch**: Builds and tags as `latest`
- **Push to `develop` branch**: Builds and tags as `develop`
- **Push tags** (`v*`): Builds versioned images (e.g., `v1.0.0`)
- **Pull requests**: Builds only (doesn't push)
- **Manual trigger**: Click "Run workflow" in GitHub Actions tab

## Image Tags

The workflows automatically create multiple tags:
- `latest` - Latest build from main branch
- `develop` - Latest build from develop branch
- `v1.0.0` - Semantic version tags
- `main-abc1234` - Branch name + commit SHA

## Which One to Use?

| Workflow | Registry | Setup Required | Recommended For |
|----------|----------|----------------|-----------------|
| `build-ghcr.yml` | GitHub Container Registry | ✅ None | **Recommended** - Easiest setup |
| `build.yml` | Docker Hub | ⚠️ Requires secrets | Public images, traditional workflow |

## Using Only One Workflow

To avoid running both workflows on every push:

**Option 1: Delete the one you don't want**
```bash
# Use only GHCR
rm .github/workflows/build.yml

# Use only Docker Hub
rm .github/workflows/build-ghcr.yml
```

**Option 2: Disable by renaming**
```bash
# Disable Docker Hub
mv .github/workflows/build.yml .github/workflows/build.yml.disabled

# Disable GHCR
mv .github/workflows/build-ghcr.yml .github/workflows/build-ghcr.yml.disabled
```

## After Pushing Images

Update your deployment manifests with the correct registry:

**For GHCR (`build-ghcr.yml`):**
```bash
# Update deployment manifests
REGISTRY="ghcr.io/YOUR_GITHUB_USERNAME/llmtesting"  # Use lowercase repo name
sed -i "s|docker.io/yourusername/trader-tools|$REGISTRY|g" k8s/deployment.yaml
sed -i "s|docker.io/yourusername/trader-tools|$REGISTRY|g" helm/trader-tools/values.yaml
```

**For Docker Hub (`build.yml`):**
```bash
# Update deployment manifests
REGISTRY="docker.io/YOUR_DOCKERHUB_USERNAME/trader-tools"
sed -i "s|docker.io/yourusername/trader-tools|$REGISTRY|g" k8s/deployment.yaml
sed -i "s|docker.io/yourusername/trader-tools|$REGISTRY|g" helm/trader-tools/values.yaml
```

## Viewing Build Status

1. Go to your GitHub repo
2. Click **Actions** tab
3. See workflow runs and logs

## Making Images Public (GHCR)

GHCR images are private by default. To make public:

1. Go to https://github.com/users/YOUR_USERNAME/packages
2. Find `trader-tools` package
3. Click **Package settings**
4. Scroll to **Danger Zone**
5. Click **Change visibility** → **Public**

## Troubleshooting

**Build fails with "authentication required":**
- For Docker Hub: Check secrets are correctly set
- For GHCR: Ensure workflow has `packages: write` permission (already configured)

**Can't pull image from GHCR:**
```bash
# Login to GHCR (for private images)
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin
```

**Want to trigger build manually:**
1. Go to **Actions** tab
2. Select workflow
3. Click **Run workflow** button

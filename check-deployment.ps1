#!/usr/bin/env pwsh
# Quick deployment status check

Write-Host "`n=== DEPLOYMENT STATUS CHECK ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n" -ForegroundColor Gray

# Get latest commit
$latestCommit = git log -1 --format='%h - %s'
Write-Host "Latest Commit:" -ForegroundColor Yellow
Write-Host "  $latestCommit`n"

# GitHub Actions build status
Write-Host "GitHub Actions Build:" -ForegroundColor Yellow
Write-Host "  https://github.com/jallen2281/Trader-Tools/actions" -ForegroundColor Cyan
Write-Host "  Status: Check if ARM64 build is complete`n"

# Kubernetes pod status
Write-Host "Checking Kubernetes pods..." -ForegroundColor Yellow
try {
    $pods = kubectl get pods -n trader-tools -l app.kubernetes.io/name=trader-tools -o json 2>&1 | ConvertFrom-Json
    
    if ($pods.items) {
        foreach ($pod in $pods.items) {
            $name = $pod.metadata.name
            $phase = $pod.status.phase
            $image = $pod.spec.containers[0].image
            $ready = ($pod.status.containerStatuses[0].ready -eq $true)
            
            Write-Host "  Pod: $name" -ForegroundColor $(if ($ready) { "Green" } else { "Red" })
            Write-Host "    Phase: $phase"
            Write-Host "    Ready: $ready"
            Write-Host "    Image: $image"
            
            # Check if using latest tag
            if ($image -like "*:latest") {
                Write-Host "    ⚠ Using :latest tag - image may be cached" -ForegroundColor Yellow
            }
        }
    } else {
        Write-Host "  No pods found" -ForegroundColor Red
    }
} catch {
    Write-Host "  ✗ Cannot connect to cluster: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Make sure kubectl context is set correctly`n" -ForegroundColor Yellow
}

Write-Host "`n=== NEXT STEPS ===" -ForegroundColor Cyan
Write-Host "1. Wait for GitHub Actions ARM64 build to complete"
Write-Host "2. ArgoCD will auto-sync within 3 minutes of new image"
Write-Host "3. Watch pod restart: kubectl get pods -n trader-tools -w"
Write-Host "4. Check logs after restart: kubectl logs -n trader-tools deployment/trader-tools --tail=100`n"

Write-Host "Manual image pull (if needed):" -ForegroundColor Yellow
Write-Host "  kubectl rollout restart deployment/trader-tools -n trader-tools`n" -ForegroundColor Gray

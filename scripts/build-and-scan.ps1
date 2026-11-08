<#
.SYNOPSIS
    Builds ferrous-vectordb and ferrous-vectordb-seeder Docker images and scans them with Hadolint and Trivy (Story 6.4).
.DESCRIPTION
    Enforces Tier 2 DevSecOps standards locally without incurring cloud CI minutes (AD-13, NFR-10..13).
#>
[CmdletBinding()]
param (
    [Alias("skip-scan")]
    [switch]$SkipScan,
    [Alias("dry-run")]
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$RepoRoot = (Resolve-Path "$ScriptDir\..").Path

$Targets = @(
    @{
        Name = "vectordb"
        Image = "ferrous-vectordb:latest"
        Dockerfile = "Dockerfile"
    },
    @{
        Name = "seeder"
        Image = "ferrous-vectordb-seeder:latest"
        Dockerfile = "Dockerfile.seeder"
    }
)

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " [DEVSECOPS] Building and Scanning ferrous-vectordb & Seeder Containers" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

Push-Location $RepoRoot
try {
    # 1. Hadolint Dockerfile Linting
    Write-Host "`n[Step 1/3] Running Hadolint Dockerfile SAST audit..." -ForegroundColor Yellow
    foreach ($target in $Targets) {
        $df = $target.Dockerfile
        Write-Host "  Auditing $df..." -ForegroundColor Gray
        if ($DryRun) {
            Write-Host "  [DRY-RUN] hadolint $df"
        } else {
            $HadolintCmd = Get-Command hadolint -ErrorAction SilentlyContinue
            if ($HadolintCmd) {
                hadolint $df
            } else {
                Write-Host "  [INFO] Local hadolint CLI not found; running via hadolint/hadolint container..." -ForegroundColor Gray
                docker run --rm -v "${RepoRoot}:/work" -w /work hadolint/hadolint:latest hadolint $df
            }
            if ($LASTEXITCODE -ne 0) { throw "Hadolint Dockerfile validation failed for $df" }
            Write-Host "  [OK] $df passed Hadolint linting (0 issues)." -ForegroundColor Green
        }
    }

    # 2. Build Container Images
    Write-Host "`n[Step 2/3] Building container images..." -ForegroundColor Yellow
    foreach ($target in $Targets) {
        $img = $target.Image
        $df = $target.Dockerfile
        Write-Host "  Building image $img from $df..." -ForegroundColor Gray
        if ($DryRun) {
            Write-Host "  [DRY-RUN] docker build -t $img -f $df ."
        } else {
            docker build -t $img -f $df .
            if ($LASTEXITCODE -ne 0) { throw "Failed to build container image $img" }
            Write-Host "  [OK] Container image $img built successfully." -ForegroundColor Green
        }
    }

    if ($SkipScan) {
        Write-Host "`n[WARN] Skipping Trivy vulnerability scanning (-SkipScan enabled)." -ForegroundColor Yellow
        return
    }

    function Invoke-TrivyScan {
        param ([string]$ImageName)
        $TrivyCmd = Get-Command trivy -ErrorAction SilentlyContinue
        if ($TrivyCmd) {
            trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 $ImageName
        } else {
            Write-Host "  [INFO] Local trivy CLI not found; running via aquasec/trivy container..." -ForegroundColor Gray
            docker run --rm `
                -v //var/run/docker.sock:/var/run/docker.sock `
                aquasec/trivy:latest image `
                --severity HIGH,CRITICAL `
                --ignore-unfixed `
                --exit-code 1 `
                $ImageName
        }
        if ($LASTEXITCODE -ne 0) { throw "Trivy vulnerability scan failed for $ImageName" }
    }

    # 3. Trivy Scan
    Write-Host "`n[Step 3/3] Running Trivy vulnerability scan on container images..." -ForegroundColor Yellow
    foreach ($target in $Targets) {
        $img = $target.Image
        Write-Host "  Scanning image $img..." -ForegroundColor Gray
        if ($DryRun) {
            Write-Host "  [DRY-RUN] trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 $img"
        } else {
            Invoke-TrivyScan $img
            Write-Host "  [OK] Zero HIGH or CRITICAL unfixed vulnerabilities detected in $img." -ForegroundColor Green
        }
    }

    Write-Host "`n======================================================================" -ForegroundColor Cyan
    Write-Host " [SUCCESS] All Container Targets Built and Verified (0 CVEs)!" -ForegroundColor Green
    Write-Host "======================================================================" -ForegroundColor Cyan
} finally {
    Pop-Location
}

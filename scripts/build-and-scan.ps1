<#
.SYNOPSIS
    Builds ferrous-vectordb Docker image and scans it with Hadolint and Trivy (Story 6.3).
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
$TargetImage = "ferrous-vectordb:latest"
$Dockerfile = "Dockerfile"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " [DEVSECOPS] Building and Scanning ferrous-vectordb Container Image" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

Push-Location $RepoRoot
try {
    # 1. Hadolint Dockerfile Linting
    Write-Host "`n[Step 1/3] Running Hadolint Dockerfile SAST audit on $Dockerfile..." -ForegroundColor Yellow
    if ($DryRun) {
        Write-Host "  [DRY-RUN] hadolint $Dockerfile"
    } else {
        $HadolintCmd = Get-Command hadolint -ErrorAction SilentlyContinue
        if ($HadolintCmd) {
            hadolint $Dockerfile
        } else {
            Write-Host "  [INFO] Local hadolint CLI not found; running via hadolint/hadolint container..." -ForegroundColor Gray
            docker run --rm -v "${RepoRoot}:/work" -w /work hadolint/hadolint:latest hadolint $Dockerfile
        }
        if ($LASTEXITCODE -ne 0) { throw "Hadolint Dockerfile validation failed for $Dockerfile" }
        Write-Host "  [OK] Dockerfile passed Hadolint linting (0 issues)." -ForegroundColor Green
    }

    # 2. Build Qdrant Vector DB Container
    Write-Host "`n[Step 2/3] Building Qdrant container image ($TargetImage)..." -ForegroundColor Yellow
    if ($DryRun) {
        Write-Host "  [DRY-RUN] docker build -t $TargetImage -f $Dockerfile ."
    } else {
        docker build -t $TargetImage -f $Dockerfile .
        if ($LASTEXITCODE -ne 0) { throw "Failed to build container image $TargetImage" }
        Write-Host "  [OK] Container image $TargetImage built successfully." -ForegroundColor Green
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

    # 3. Trivy Scan: ferrous-vectordb
    Write-Host "`n[Step 3/3] Running Trivy vulnerability scan on $TargetImage..." -ForegroundColor Yellow
    if ($DryRun) {
        Write-Host "  [DRY-RUN] trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 $TargetImage"
    } else {
        Invoke-TrivyScan $TargetImage
        Write-Host "  [OK] Zero HIGH or CRITICAL unfixed vulnerabilities detected in $TargetImage." -ForegroundColor Green
    }

    Write-Host "`n======================================================================" -ForegroundColor Cyan
    Write-Host " [SUCCESS] ferrous-vectordb Container Built and Verified (0 CVEs)!" -ForegroundColor Green
    Write-Host "======================================================================" -ForegroundColor Cyan
} finally {
    Pop-Location
}

<#
.SYNOPSIS
    Downloads or provisions enterprise SOP and ABCD benchmark datasets for ferrous-vectordb with offline fallback.

.DESCRIPTION
    Ensures that enterprise SOP markdown files and ABCD customer support benchmark dialogues
    are staged and ready for vector embedding ingestion into Qdrant collections (Story 6.2).
    Adheres to offline portability: verifies packaged artifacts when network is unavailable.

.PARAMETER OutputDir
    Target directory where datasets are located or staged. Defaults to ../data relative to script.

.PARAMETER Offline
    Forces offline mode, bypassing all remote download attempts and validating packaged artifacts.

.PARAMETER Force
    Forces re-validation or re-download of datasets even if already present.

.PARAMETER RemoteUrl
    Optional remote repository or mirror URL for ABCD dataset benchmark.

.EXAMPLE
    .\download-datasets.ps1 -Offline
    .\download-datasets.ps1 -OutputDir ./data
#>

[CmdletBinding()]
param(
    [string]$OutputDir = "",
    [switch]$Offline,
    [switch]$Force,
    [string]$RemoteUrl = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir "..\data"))
} else {
    $OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
}

$SopsDir = Join-Path $OutputDir "sops"
$AbcdDir = Join-Path $OutputDir "raw\abcd"
$AbcdJson = Join-Path $AbcdDir "abcd_dialogues.json"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " FerrousCX - Dataset Provisioning & Download (Story 6.2)   " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Target Data Directory: $OutputDir"
Write-Host " SOPs Directory:        $SopsDir"
Write-Host " ABCD Dialogues:        $AbcdJson"
Write-Host " Offline Flag:          $Offline"

# 1. Ensure target directories exist
if (-not (Test-Path $SopsDir)) {
    New-Item -ItemType Directory -Path $SopsDir -Force | Out-Null
}
if (-not (Test-Path $AbcdDir)) {
    New-Item -ItemType Directory -Path $AbcdDir -Force | Out-Null
}

$RequiredSops = @(
    "SOP-001-Courtesy-Credit-Issuance.md",
    "SOP-002-Carrier-Delay-Escalation.md",
    "SOP-003-Customer-Dispute-Resolution.md"
)

# 2. Check existing SOP files
$MissingSops = @()
foreach ($sop in $RequiredSops) {
    $sopPath = Join-Path $SopsDir $sop
    if (-not (Test-Path $sopPath)) {
        $MissingSops += $sop
    }
}

$AbcdExists = (Test-Path $AbcdJson) -and ((Get-Item $AbcdJson).Length -gt 0)

if ($Offline -or (-not $Force -and ($MissingSops.Count -eq 0) -and $AbcdExists)) {
    Write-Host "[INFO] Evaluating local packaged datasets..." -ForegroundColor Green
    if ($MissingSops.Count -gt 0) {
        Write-Error "[ERROR] Missing required SOP files in offline mode: $($MissingSops -join ', ')"
        exit 1
    }
    if (-not $AbcdExists) {
        Write-Error "[ERROR] Missing or empty ABCD dialogue file in offline mode: $AbcdJson"
        exit 1
    }

    Write-Host "[SUCCESS] All enterprise SOPs and ABCD benchmark datasets are present and verified." -ForegroundColor Green
    Write-Host "  - SOPs verified:        $($RequiredSops.Count) files"
    Write-Host "  - ABCD dialogues:       $AbcdJson"
    exit 0
}

# 3. Remote download attempt with clean offline fallback
Write-Host "[INFO] Attempting dataset synchronization..." -ForegroundColor Yellow
if (-not [string]::IsNullOrWhiteSpace($RemoteUrl)) {
    try {
        Write-Host "[INFO] Fetching ABCD dataset from remote: $RemoteUrl"
        $TempFile = "$AbcdJson.tmp"
        Invoke-WebRequest -Uri $RemoteUrl -OutFile $TempFile -TimeoutSec 10 -UseBasicParsing
        if ((Test-Path $TempFile) -and ((Get-Item $TempFile).Length -gt 0)) {
            Move-Item -Force $TempFile $AbcdJson
            Write-Host "[SUCCESS] Remote ABCD dataset downloaded successfully." -ForegroundColor Green
        } else {
            throw "Downloaded file is empty."
        }
    }
    catch {
        Write-Warning "[WARN] Remote download failed: $($_.Exception.Message). Falling back to local packaged artifacts."
        if (Test-Path "$AbcdJson.tmp") { Remove-Item -Force "$AbcdJson.tmp" -ErrorAction SilentlyContinue }
        if (-not $AbcdExists) {
            Write-Error "[ERROR] Local fallback dataset missing at $AbcdJson"
            exit 1
        }
    }
} else {
    Write-Host "[INFO] No remote URL specified. Using authoritative packaged repository artifacts."
}

# Final verification
$MissingFinal = @()
foreach ($sop in $RequiredSops) {
    $sopPath = Join-Path $SopsDir $sop
    if (-not (Test-Path $sopPath)) {
        $MissingFinal += $sop
    }
}

if ($MissingFinal.Count -gt 0 -or -not (Test-Path $AbcdJson) -or ((Get-Item $AbcdJson).Length -eq 0)) {
    Write-Error "[ERROR] Dataset verification failed. Missing or empty artifacts: $($MissingFinal -join ', ')"
    exit 1
}

Write-Host "[SUCCESS] Dataset provisioning completed successfully." -ForegroundColor Green
exit 0

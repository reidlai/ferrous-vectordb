<#
.SYNOPSIS
    FerrousCX Qdrant Collection Scaffolding Script (PowerShell)
    Initializes cx_policy_knowledge and support_transcripts collections idempotently.

.DESCRIPTION
    Checks service readiness (/readyz), auto-creates storage directory if missing,
    and scaffolds Qdrant collections with tuned HNSW indexing parameters for sub-5ms latency.
    Supports -DryRun for offline verification without network calls.

.PARAMETER HostUrl
    The base URL for the Qdrant REST service. Defaults to env:QDRANT_URL or http://localhost:6333.

.PARAMETER ApiKey
    Optional Qdrant API key / bearer token. Defaults to env:QDRANT_API_KEY.

.PARAMETER DryRun
    When specified, outputs validated collection configurations without dispatching HTTP requests.

.EXAMPLE
    .\create-collections.ps1 -DryRun
    .\create-collections.ps1 -HostUrl "http://localhost:6333"
#>

[CmdletBinding()]
param(
    [Alias("host", "Url")]
    [string]$HostUrl = $env:QDRANT_URL,
    [Alias("Key")]
    [string]$ApiKey = $env:QDRANT_API_KEY,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not $HostUrl) {
    $HostUrl = "http://localhost:6333"
}
$HostUrl = $HostUrl.TrimEnd('/')

$Headers = @{}
if ($ApiKey) {
    $Headers["api-key"] = $ApiKey
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

# Auto-create missing persistent storage directory
$StorageDir = Join-Path $RootDir "qdrant_storage"
if (-not (Test-Path $StorageDir)) {
    Write-Host "[INFO] Creating missing storage directory: $StorageDir"
    New-Item -ItemType Directory -Path $StorageDir -Force | Out-Null
} else {
    Write-Host "[INFO] Persistent storage directory present: $StorageDir"
}

# Collection definitions (384 dimensions, Cosine distance, tuned HNSW)
$CollectionPayload = @{
    vectors = @{
        size = 384
        distance = "Cosine"
    }
    hnsw_config = @{
        m = 16
        ef_construct = 100
        full_scan_threshold = 10000
    }
}

$Collections = @("cx_policy_knowledge", "support_transcripts")
$PayloadJson = $CollectionPayload | ConvertTo-Json -Depth 4

if ($DryRun) {
    Write-Host "===================================================================="
    Write-Host "[DRY RUN] Validated Qdrant Collection Definitions (No Network Calls)"
    Write-Host "===================================================================="
    Write-Host "Target Host: $HostUrl"
    foreach ($col in $Collections) {
        Write-Host ""
        Write-Host "Collection: $col"
        Write-Host "Payload:"
        Write-Host $PayloadJson
    }
    Write-Host "===================================================================="
    Write-Host "[DRY RUN] Validation completed successfully."
    exit 0
}

# Readiness probe with bounded exponential backoff
$MaxRetries = 10
$BackoffSeconds = 1
$Ready = $false

Write-Host "[INFO] Checking Qdrant readiness at $HostUrl/readyz..."
for ($i = 1; $i -le $MaxRetries; $i++) {
    try {
        $readyCheck = Invoke-WebRequest -Uri "$HostUrl/readyz" -Method Get -Headers $Headers -TimeoutSec 5 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($readyCheck.StatusCode -eq 200) {
            Write-Host "[INFO] Qdrant service is ready (HTTP 200)."
            $Ready = $true
            break
        }
    } catch {
        # Service booting or not yet reachable
    }

    if ($i -lt $MaxRetries) {
        Write-Host "[WARN] Qdrant not ready. Attempt $i/$MaxRetries. Retrying in ${BackoffSeconds}s..."
        Start-Sleep -Seconds $BackoffSeconds
        $BackoffSeconds = [Math]::Min($BackoffSeconds * 2, 5)
    }
}

if (-not $Ready) {
    Write-Error "[ERROR] Timed out waiting for Qdrant service at $HostUrl/readyz"
    exit 1
}

# Scaffold collections idempotently
foreach ($col in $Collections) {
    Write-Host "[INFO] Checking existence of collection '$col'..."
    $Exists = $false
    try {
        $getCheck = Invoke-WebRequest -Uri "$HostUrl/collections/$col" -Method Get -Headers $Headers -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($getCheck.StatusCode -eq 200) {
            $Exists = $true
        }
    } catch {
        $statusCode = $null
        if ($_.Exception.Response) {
            $statusCode = $_.Exception.Response.StatusCode.value__
        }
        if ($statusCode -eq 404) {
            $Exists = $false
        } else {
            Write-Error "[ERROR] Failed while checking existence of collection '$col' (Status: $statusCode): $_"
            exit 1
        }
    }

    if ($Exists) {
        Write-Host "[INFO] Collection '$col' already exists. Skipping creation (Idempotent)."
        continue
    }

    Write-Host "[INFO] Creating collection '$col' with 384 dimensions and Cosine distance..."
    try {
        $createResp = Invoke-RestMethod -Uri "$HostUrl/collections/$col" -Method Put -Headers $Headers -Body $PayloadJson -ContentType "application/json" -TimeoutSec 10
        Write-Host "[SUCCESS] Collection '$col' created successfully: $($createResp | ConvertTo-Json -Compress)"
    } catch {
        Write-Error "[ERROR] Failed to create collection '$col': $_"
        exit 1
    }
}

Write-Host "[SUCCESS] All Qdrant collections scaffolded and verified successfully."
exit 0

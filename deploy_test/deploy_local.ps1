# deploy_test/deploy_local.ps1
# Full local deployment test for Madison Ave Construction
# Pre-fills all interview questions via secrets/.env
# Usage: cd deploy_test; .\deploy_local.ps1

param(
    [switch]$DryRun,
    [switch]$SkipSync,
    [switch]$SkipWeb
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
if (-not $ROOT) { $ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path }

Write-Host ""
Write-Host "============================================================"
Write-Host "  HarrisPepe Local Deployment Test"
Write-Host "  Madison Ave Construction"
Write-Host "============================================================"
Write-Host ""

# ── Step 1: Verify prerequisites ─────────────────────────────────────
Write-Host "[1/5] Checking prerequisites..."

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "  ERROR: Python not found. Install Python 3.10+ and add to PATH."
    exit 1
}
$pyver = python --version 2>&1
Write-Host "  OK  $pyver"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Host "  ERROR: gcloud not found. Run: winget install Google.CloudSDK"
    exit 1
}
Write-Host "  OK  gcloud found"

$account = gcloud config get account 2>&1
Write-Host "  OK  GCP account: $account"

# ── Step 2: Install dependencies ─────────────────────────────────────
Write-Host ""
Write-Host "[2/5] Installing dependencies..."
Set-Location "$ROOT\Phase5_oneDrive"
pip install -r requirements.txt -q
if ($LASTEXITCODE -ne 0) { Write-Host "  ERROR: pip install failed"; exit 1 }
Write-Host "  OK  Phase 5 dependencies installed"

Set-Location $ROOT
if (Test-Path "requirements.txt") {
    pip install -r requirements.txt -q
    Write-Host "  OK  Root dependencies installed"
}

# ── Step 3: Bootstrap verification ───────────────────────────────────
Write-Host ""
Write-Host "[3/5] Running Phase 5 bootstrap verification..."
Write-Host "  (Using pre-filled secrets from deploy_test\secrets\.env)"

$env:VERTEX_ENV_FILE = "$ROOT\deploy_test\secrets\.env"
Set-Location "$ROOT\Phase5_oneDrive"

python bootstrap_onedrive.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  Bootstrap failed. Check output above."
    Write-Host "  Most likely fix: run 'gcloud auth application-default login'"
    exit 1
}

# ── Step 4: OneDrive sync ─────────────────────────────────────────────
Write-Host ""
if ($SkipSync) {
    Write-Host "[4/5] Skipping sync (--SkipSync flag set)"
} else {
    if ($DryRun) {
        Write-Host "[4/5] Running OneDrive sync (DRY RUN)..."
        python onedrive_sync.py --dry-run
    } else {
        Write-Host "[4/5] Running OneDrive sync (incremental)..."
        python onedrive_sync.py
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Sync encountered errors -- check output above"
    }
}

# ── Step 5: Web UI ────────────────────────────────────────────────────
Write-Host ""
if ($SkipWeb) {
    Write-Host "[5/5] Skipping web UI (--SkipWeb flag set)"
} else {
    Write-Host "[5/5] Starting web UI..."
    Write-Host "  Open browser to: http://localhost:8080"
    Write-Host "  Press Ctrl+C to stop"
    Write-Host ""
    Set-Location $ROOT
    $env:VERTEX_ENV_FILE = "$ROOT\deploy_test\secrets\.env"
    python scripts\simple_web.py
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  Deployment test complete"
Write-Host "============================================================"

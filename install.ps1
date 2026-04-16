# ============================================================================
#  VERTEX AI SMB BOOTSTRAPPER — install.ps1
#  Interactive installer. Idempotent — safe to re-run.
# ============================================================================

[CmdletBinding()]
param(
    [switch]$NonInteractive,
    [switch]$SkipBootstrap
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor Cyan
}
function Write-Step([string]$Msg) { Write-Host "  → $Msg" -ForegroundColor Yellow }
function Write-Ok([string]$Msg)   { Write-Host "  ✓ $Msg" -ForegroundColor Green }
function Write-Warn([string]$Msg) { Write-Host "  ! $Msg" -ForegroundColor Yellow }
function Write-Err([string]$Msg)  { Write-Host "  ✗ $Msg" -ForegroundColor Red }

function Prompt-Required([string]$Q, [string]$Default = "") {
    if ($NonInteractive) {
        if (-not $Default) { throw "NonInteractive: $Q has no default" }
        return $Default
    }
    while ($true) {
        $p = if ($Default) { "$Q [$Default]" } else { $Q }
        $v = Read-Host $p
        if ([string]::IsNullOrWhiteSpace($v)) { $v = $Default }
        if ($v) { return $v }
        Write-Warn "  required."
    }
}
function Prompt-Optional([string]$Q, [string]$Default = "") {
    if ($NonInteractive) { return $Default }
    $p = if ($Default) { "$Q [$Default]" } else { "$Q (leave blank to skip)" }
    $v = Read-Host $p
    if ([string]::IsNullOrWhiteSpace($v)) { return $Default }
    return $v
}
function Prompt-YesNo([string]$Q, [bool]$Default = $true) {
    if ($NonInteractive) { return $Default }
    $d = if ($Default) { "Y/n" } else { "y/N" }
    $v = (Read-Host "$Q [$d]").Trim().ToLower()
    if ([string]::IsNullOrWhiteSpace($v)) { return $Default }
    return ($v -eq "y" -or $v -eq "yes")
}
function Yaml-Bool([bool]$b) { return $b.ToString().ToLower() }

# ============================================================= 1. PREREQS ==
Write-Section "VERTEX AI SMB BOOTSTRAPPER"
Write-Host "  Location: $RepoRoot"

Write-Section "1/8  Prerequisites"
try { $py = (& python --version) 2>&1; Write-Ok "Python: $py" }
catch { Write-Err "Python 3.10+ required. https://www.python.org/downloads/"; exit 1 }
try { $gc = (& gcloud --version | Select-Object -First 1); Write-Ok "gcloud: $gc" }
catch { Write-Err "gcloud required. https://cloud.google.com/sdk/docs/install"; exit 1 }

# ============================================================= 2. VENV ======
Write-Section "2/8  Python environment"
$VenvPath = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $VenvPath)) {
    Write-Step "Creating .venv"
    & python -m venv $VenvPath
}
$PyExe = Join-Path $VenvPath "Scripts\python.exe"
Write-Step "Installing requirements"
& $PyExe -m pip install --quiet --upgrade pip
& $PyExe -m pip install --quiet -r (Join-Path $RepoRoot "requirements.txt")
Write-Ok "requirements installed"

# ============================================================= 3. AUTH ======
Write-Section "3/8  Google Cloud authentication"
$activeAcct = ""
try { $activeAcct = (& gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null).Trim() } catch {}
if ($activeAcct) { Write-Ok "gcloud signed in as $activeAcct" }
else {
    if (Prompt-YesNo "Sign into gcloud now?" $true) {
        & gcloud auth login
        $activeAcct = (& gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null).Trim()
        Write-Ok "signed in as $activeAcct"
    } else { Write-Err "gcloud sign-in required"; exit 1 }
}

# ============================================================= 4. COMPANY ==
Write-Section "4/8  Company information"
$CompanyName    = Prompt-Required "Company / business name" ""
$CompanySlug    = ($CompanyName -replace '[^a-zA-Z0-9-]', '-').ToLower().Trim('-')
$CompanyDisplay = (Get-Culture).TextInfo.ToTitleCase($CompanyName)
$PrimaryProp    = Prompt-Optional "Primary property / entity name (e.g. '15-Northridge')" ""

# ============================================================= 5. GCP CONFIG =
Write-Section "5/8  GCP project + resources"
$CurrentProject = ""
try { $CurrentProject = (& gcloud config get-value project 2>$null).Trim() } catch {}
if ($CurrentProject -eq "(unset)") { $CurrentProject = "" }

$ProjectId   = Prompt-Required "GCP Project ID" $CurrentProject
$Location    = Prompt-Optional "Discovery Engine region (global|us|eu)" "global"
$BucketName  = Prompt-Required "GCS bucket (globally unique)" "$ProjectId-$CompanySlug-mirror"
$DataStoreId = Prompt-Required "Data Store ID" "$CompanySlug-docs"
$EngineId    = Prompt-Required "Search Engine ID" "$CompanySlug-search"
$SaId        = Prompt-Required "Service Account short name" "$CompanySlug-sync-sa"
$SaEmail     = "$SaId@$ProjectId.iam.gserviceaccount.com"

# ============================================================= 6. CONNECTORS =
Write-Section "6/8  Data source connectors"
Write-Host "  Select which data sources to connect."
Write-Host ""

# --- Drive ---
$EnableDrive   = Prompt-YesNo "  Google Drive?" $true
$DriveFolderId = ""
if ($EnableDrive) {
    $DriveFolderId = Prompt-Required "    Drive folder ID (from URL: drive.google.com/drive/folders/<ID>)" ""
}

# --- Gmail ---
$EnableGmail     = Prompt-YesNo "  Gmail?" $false
$GmailSecretPath = "client_secret.json"
$GmailQuery      = "has:attachment"
$GmailAfter      = "2024/01/01"
$GmailProperty   = ""
if ($EnableGmail) {
    Write-Host ""
    Write-Host "  Gmail requires a Desktop OAuth client (NOT a service account)."
    Write-Host "  Create one at: Cloud Console → APIs & Services → Credentials"
    Write-Host "  → Create Credentials → OAuth Client ID → Desktop app → Download JSON."
    Write-Host ""
    $GmailSecretPath = Prompt-Required "    Path to OAuth client_secret.json" "client_secret.json"
    $GmailQuery      = Prompt-Required "    Gmail search query (e.g. 'has:attachment from:invoices@')" "has:attachment"
    $GmailAfter      = Prompt-Optional "    Only messages after (YYYY/MM/DD)" "2024/01/01"
    $GmailProperty   = Prompt-Optional "    Default property tag for Gmail content" $PrimaryProp
}

# --- OneDrive ---
$EnableOneDrive = Prompt-YesNo "  OneDrive (Phase 2 stub — not yet functional)?" $false

# --- Local files ---
$EnableLocal = Prompt-YesNo "  Local filesystem directory?" $false
$LocalPath   = ""
if ($EnableLocal) {
    $LocalPath = Prompt-Required "    Absolute path to directory" ""
}

# --- CSV ---
$EnableCsv = Prompt-YesNo "  CSV import (Phase 2 stub)?" $false

# --- Heuristic ---
Write-Host ""
$UseHeuristic = Prompt-YesNo "  Enable filename heuristic classifier? (recommended for flat folders)" $true
$DefaultProp  = if ($PrimaryProp) { $PrimaryProp } else { "null" }

# ============================================================= 7. WRITE CONFIG =
Write-Section "7/8  Writing configuration"

$KeyPath = "service-account.json"

$PropsLine = if ($PrimaryProp) { "`n    - $PrimaryProp" } else { "" }
$LocalEsc  = if ($LocalPath) { $LocalPath.Replace('\','\\') } else { "" }
$GmailProp = if ($GmailProperty) { $GmailProperty } else { if ($PrimaryProp) { $PrimaryProp } else { "_inbox" } }

$cfg = @"
# Generated by install.ps1 on $(Get-Date -Format "yyyy-MM-dd HH:mm")
project:
  id: $ProjectId
  location: $Location

gcs:
  bucket: $BucketName
  mirror_prefix: data
  manifest_prefix: _manifests

service_account:
  email: $SaEmail
  key_path: $KeyPath

data_store:
  id: $DataStoreId
  display_name: $CompanyDisplay Documents
  industry_vertical: GENERIC
  solution_types:
    - SOLUTION_TYPE_CHAT
    - SOLUTION_TYPE_SEARCH
  content_config: CONTENT_REQUIRED

engine:
  id: $EngineId
  display_name: $CompanyDisplay Intelligent Search
  search_tier: SEARCH_TIER_ENTERPRISE
  search_add_ons:
    - SEARCH_ADD_ON_LLM

metadata:
  category_folders:
    "01-Acquisition": legal
    "02-Financials":  finance
    "04-Permits":     permit
    "06-Invoices":    billing
    "07-Photos":      image
    "09-Email":       email
  properties: [$PropsLine
  ]
  heuristic_classification: $(Yaml-Bool $UseHeuristic)
  default_property: $DefaultProp
  heuristic_rules:
    - { pattern: "\\.(jpg|jpeg|png|gif|bmp|tiff|webp)`$", doc_type: image }
    - { pattern: "^inv[_\\s-]|invoice|receipt|bill",        doc_type: billing }
    - { pattern: "permit|inspection|code|zoning",           doc_type: permit }
    - { pattern: "p&l|statement|bank|appraisal|balance",    doc_type: finance }
    - { pattern: "contract|closing|deed|title|ein|entity|llc|sow", doc_type: legal }
    - { pattern: ".",                                       doc_type: document }

connectors:
  drive:
    enabled: $(Yaml-Bool $EnableDrive)
    root_folder_id: $DriveFolderId
    mirror_as: Properties
    export_workspace_as: pdf

  gmail:
    enabled: $(Yaml-Bool $EnableGmail)
    client_secret_path: $GmailSecretPath
    query: "$GmailQuery"
    after: "$GmailAfter"
    default_property: $GmailProp
    index_body: true
    index_attachments: true

  onedrive:
    enabled: $(Yaml-Bool $EnableOneDrive)

  local_files:
    enabled: $(Yaml-Bool $EnableLocal)
    path: "$LocalEsc"
    mirror_as: Properties

  csv:
    enabled: $(Yaml-Bool $EnableCsv)
"@

$cfgPath = Join-Path $RepoRoot "config\config.yaml"
$cfg | Out-File -FilePath $cfgPath -Encoding UTF8
Write-Ok "wrote $cfgPath"

@"
GOOGLE_APPLICATION_CREDENTIALS=$RepoRoot\$KeyPath
GOOGLE_CLOUD_PROJECT=$ProjectId
"@ | Out-File -FilePath (Join-Path $RepoRoot ".env") -Encoding UTF8
Write-Ok "wrote .env"

# ============================================================= 8. BOOTSTRAP ==
Write-Section "8/8  GCP resource bootstrap"

& gcloud config set project $ProjectId 2>&1 | Out-Null
try { & gcloud auth application-default set-quota-project $ProjectId 2>&1 | Out-Null } catch {}

if ($SkipBootstrap) {
    Write-Warn "skipping (--SkipBootstrap). Run: python scripts\bootstrap.py"
} else {
    if (Prompt-YesNo "Run bootstrap now? (APIs, SA, bucket, data store, engine, schema)" $true) {
        & $PyExe (Join-Path $RepoRoot "scripts\bootstrap.py") --sa-id $SaId
        if ($LASTEXITCODE -ne 0) { Write-Err "bootstrap failed"; exit 1 }
    }
}

# ============================================================= NEXT STEPS ===
Write-Section "SETUP COMPLETE — NEXT STEPS"

if ($EnableDrive -and $DriveFolderId) {
    Write-Host ""
    Write-Host "  GOOGLE DRIVE:" -ForegroundColor Yellow
    Write-Host "    Share your Drive folder with the service account:"
    Write-Host "    1. Open https://drive.google.com/drive/folders/$DriveFolderId"
    Write-Host "    2. Click Share → paste: $SaEmail → Viewer → Share"
}
if ($EnableGmail) {
    Write-Host ""
    Write-Host "  GMAIL:" -ForegroundColor Yellow
    Write-Host "    1. Ensure client_secret.json is at: $RepoRoot\$GmailSecretPath"
    Write-Host "    2. Enable Gmail API: gcloud services enable gmail.googleapis.com"
    Write-Host "    3. First sync will pop a browser for consent:"
    Write-Host "       python scripts\sync.py --only gmail"
}

Write-Host ""
Write-Host "  RUN THE PIPELINE:" -ForegroundColor Cyan
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "    python scripts\doctor.py"
Write-Host "    python scripts\sync.py --dry-run"
Write-Host "    python scripts\sync.py"
Write-Host "    python scripts\index.py --full"
Write-Host "    python scripts\query.py ""How much did we pay the plumber?"""
Write-Host ""
Write-Host "DONE" -ForegroundColor Green
Write-Host ""

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
    if ($NonInteractive) { if (-not $Default) { throw "NonInteractive: $Q has no default" }; return $Default }
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
try { $py = (& python --version) 2>&1; Write-Ok "Python: $py" } catch { Write-Err "Python 3.10+ required"; exit 1 }
try { $gc = (& gcloud --version | Select-Object -First 1); Write-Ok "gcloud: $gc" } catch { Write-Err "gcloud required"; exit 1 }

# ============================================================= 2. VENV ======
Write-Section "2/8  Python environment"
$VenvPath = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $VenvPath)) { Write-Step "Creating .venv"; & python -m venv $VenvPath }
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
    if (Prompt-YesNo "Sign into gcloud now?" $true) { & gcloud auth login }
    else { Write-Err "gcloud sign-in required"; exit 1 }
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
$EnableDrive   = Prompt-YesNo "  Google Drive?" $true
$DriveFolderId = ""
if ($EnableDrive) { $DriveFolderId = Prompt-Required "    Drive folder ID (from URL: /folders/<ID>)" "" }

$EnableGmail     = Prompt-YesNo "  Gmail?" $false
$GmailSecretPath = "client_secret.json"; $GmailQuery = "has:attachment"; $GmailAfter = "2024/01/01"; $GmailProperty = ""
if ($EnableGmail) {
    Write-Host ""; Write-Host "  Gmail needs a Desktop OAuth client (Cloud Console → Credentials)."
    $GmailSecretPath = Prompt-Required "    Path to OAuth client_secret.json" "client_secret.json"
    $GmailQuery      = Prompt-Required "    Gmail search query" "has:attachment"
    $GmailAfter      = Prompt-Optional "    Only messages after (YYYY/MM/DD)" "2024/01/01"
    $GmailProperty   = Prompt-Optional "    Default property tag for Gmail content" $PrimaryProp
}

$EnableOneDrive = Prompt-YesNo "  OneDrive (stub)?" $false
$EnableLocal    = Prompt-YesNo "  Local filesystem?" $false
$LocalPath = ""; if ($EnableLocal) { $LocalPath = Prompt-Required "    Absolute path" "" }
$EnableCsv = Prompt-YesNo "  CSV import (stub)?" $false

Write-Host ""
$UseHeuristic = Prompt-YesNo "  Enable filename heuristic classifier?" $true
$DefaultProp  = if ($PrimaryProp) { $PrimaryProp } else { "null" }

# --- Cloud Run ---
Write-Host ""
Write-Host "  Automated sync (Cloud Run + Scheduler)" -ForegroundColor Cyan
$PollInterval   = Prompt-Optional "  Sync interval in minutes (15, 30, 60, 120, 360)" "60"
$CloudRunRegion = Prompt-Optional "  Cloud Run region" "us-central1"

# ============================================================= 7. WRITE CONFIG =
Write-Section "7/8  Writing configuration"
$KeyPath   = "service-account.json"
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
  solution_types: [SOLUTION_TYPE_CHAT, SOLUTION_TYPE_SEARCH]
  content_config: CONTENT_REQUIRED

engine:
  id: $EngineId
  display_name: $CompanyDisplay Intelligent Search
  search_tier: SEARCH_TIER_ENTERPRISE
  search_add_ons: [SEARCH_ADD_ON_LLM]

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

cloud_run:
  service_name: $CompanySlug-sync
  region: $CloudRunRegion
  memory: 1Gi
  cpu: 2
  timeout: 1800
  max_instances: 1
  poll_interval_minutes: $PollInterval
  scheduler_job_name: $CompanySlug-sync-cron

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

(Join-Path $RepoRoot "config\config.yaml") | ForEach-Object { $cfg | Out-File -FilePath $_ -Encoding UTF8 }
Write-Ok "wrote config/config.yaml"
@"
GOOGLE_APPLICATION_CREDENTIALS=$RepoRoot\$KeyPath
GOOGLE_CLOUD_PROJECT=$ProjectId
"@ | Out-File -FilePath (Join-Path $RepoRoot ".env") -Encoding UTF8
Write-Ok "wrote .env"

# ============================================================= 8. BOOTSTRAP ==
Write-Section "8/8  GCP resource bootstrap"
& gcloud config set project $ProjectId 2>&1 | Out-Null
try { & gcloud auth application-default set-quota-project $ProjectId 2>&1 | Out-Null } catch {}
if ($SkipBootstrap) { Write-Warn "skipping (--SkipBootstrap)" }
else {
    if (Prompt-YesNo "Run bootstrap now? (APIs, SA, bucket, data store, engine, schema)" $true) {
        & $PyExe (Join-Path $RepoRoot "scripts\bootstrap.py") --sa-id $SaId
        if ($LASTEXITCODE -ne 0) { Write-Err "bootstrap failed"; exit 1 }
    }
}

# ============================================================= NEXT STEPS ===
Write-Section "SETUP COMPLETE"
if ($EnableDrive -and $DriveFolderId) {
    Write-Host ""; Write-Host "  GOOGLE DRIVE:" -ForegroundColor Yellow
    Write-Host "    Share folder with SA: $SaEmail (Viewer role)"
    Write-Host "    https://drive.google.com/drive/folders/$DriveFolderId"
}
if ($EnableGmail) {
    Write-Host ""; Write-Host "  GMAIL:" -ForegroundColor Yellow
    Write-Host "    1. Put client_secret.json at: $RepoRoot\$GmailSecretPath"
    Write-Host "    2. First sync pops a browser: python scripts\sync.py --only gmail"
}
Write-Host ""
Write-Host "  RUN LOCALLY:" -ForegroundColor Cyan
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "    python scripts\doctor.py"
Write-Host "    python scripts\sync.py"
Write-Host "    python scripts\index.py --full"
Write-Host "    python scripts\query.py ""...""            # CLI"
Write-Host "    python scripts\web.py                     # web UI"
Write-Host ""
Write-Host "  DEPLOY TO CLOUD (automated every $PollInterval min):" -ForegroundColor Cyan
Write-Host "    python scripts\deploy.py                  # build + deploy + schedule"
Write-Host "    python scripts\deploy.py --trigger        # run one sync now"
Write-Host "    python scripts\deploy.py --logs           # watch output"
Write-Host "    python scripts\deploy.py --schedule-only  # change interval"
Write-Host ""
Write-Host "DONE" -ForegroundColor Green
Write-Host ""

# ============================================================================
#  VERTEX AI SMB BOOTSTRAPPER — install.ps1
#  Interactive installer for any company. Idempotent — safe to re-run.
#  Harris: Run this once per new client to set everything up.
# ============================================================================

[CmdletBinding()] param([switch]$NonInteractive,[switch]$SkipBootstrap)
$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot

function Write-Section([string]$T) { Write-Host ""; Write-Host ("=" * 72) -ForegroundColor Cyan; Write-Host "  $T" -ForegroundColor Cyan; Write-Host ("=" * 72) -ForegroundColor Cyan }
function Write-Step([string]$M) { Write-Host "  > $M" -ForegroundColor Yellow }
function Write-Ok([string]$M)   { Write-Host "  + $M" -ForegroundColor Green }
function Write-Warn([string]$M) { Write-Host "  ! $M" -ForegroundColor Yellow }
function Write-Err([string]$M)  { Write-Host "  X $M" -ForegroundColor Red }

function Prompt-Req([string]$Q, [string]$D = "") {
    if ($NonInteractive) { if (-not $D) { throw "$Q has no default" }; return $D }
    while ($true) { $v = Read-Host $(if($D){"$Q [$D]"}else{$Q}); if(-not $v){$v=$D}; if($v){return $v}; Write-Warn "required." }
}
function Prompt-Opt([string]$Q, [string]$D = "") {
    if ($NonInteractive) { return $D }
    $v = Read-Host $(if($D){"$Q [$D]"}else{"$Q (optional)"}); if(-not $v){return $D}; return $v
}
function Prompt-YN([string]$Q, [bool]$D = $true) {
    if ($NonInteractive) { return $D }
    $v = (Read-Host "$Q [$(if($D){'Y/n'}else{'y/N'})]").Trim().ToLower()
    if(-not $v){return $D}; return ($v -eq "y" -or $v -eq "yes")
}
function YB([bool]$b) { return $b.ToString().ToLower() }

# ============================================================= 1. PREREQS ==
Write-Section "VERTEX AI DOCUMENT SEARCH — INSTALLER"
Write-Host "  This script sets up an AI-powered document search system."
Write-Host "  It creates GCP resources, configures connectors, and launches the web UI."
Write-Host "  Location: $RepoRoot"
Write-Host ""

Write-Section "1/10  Prerequisites"
try { $py = (& python --version) 2>&1; Write-Ok "Python: $py" } catch { Write-Err "Python 3.10+ required. https://www.python.org/downloads/"; exit 1 }
try { $gc = (& gcloud --version | Select-Object -First 1); Write-Ok "gcloud: $gc" } catch { Write-Err "gcloud CLI required. https://cloud.google.com/sdk/docs/install"; exit 1 }

# ============================================================= 2. VENV ======
Write-Section "2/10  Python environment"
$VenvPath = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $VenvPath)) { Write-Step "Creating .venv"; & python -m venv $VenvPath }
$PyExe = Join-Path $VenvPath "Scripts\python.exe"
Write-Step "Installing requirements"
& $PyExe -m pip install --quiet --upgrade pip
& $PyExe -m pip install --quiet -r (Join-Path $RepoRoot "requirements.txt")
Write-Ok "all packages installed"

# ============================================================= 3. AUTH ======
Write-Section "3/10  Google Cloud authentication"
$acct = ""
try { $acct = (& gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null).Trim() } catch {}
if ($acct) { Write-Ok "signed in as $acct" }
else {
    if (Prompt-YN "Sign into gcloud now?" $true) { & gcloud auth login }
    else { Write-Err "gcloud sign-in required"; exit 1 }
}

# ============================================================= 4. COMPANY ==
Write-Section "4/10  Company information (appears on PDFs and the web UI)"
$CompanyName = Prompt-Req "Company name"
$CompanySlug = ($CompanyName -replace '[^a-zA-Z0-9-]', '-').ToLower().Trim('-')
$CompanyPhone = Prompt-Opt "Phone number" ""
$CompanyEmail = Prompt-Opt "Company email" ""
$CompanyAddr  = Prompt-Opt "Address (city, state)" ""
$CompanyWeb   = Prompt-Opt "Website URL" ""
$CompanyTag   = Prompt-Opt "Tagline (shown in PDF header)" ""
$LogoPath     = Prompt-Opt "Logo file path (relative to repo, e.g. assets/logo.jpg)" ""
$PrimaryProp  = Prompt-Opt "Primary property / entity name (e.g. '15-Northridge')" ""

# ============================================================= 5. GCP ======
Write-Section "5/10  Google Cloud project"
$CurProj = ""; try { $CurProj = (& gcloud config get-value project 2>$null).Trim() } catch {}
if ($CurProj -eq "(unset)") { $CurProj = "" }
$ProjectId   = Prompt-Req "GCP Project ID" $CurProj
$Location    = Prompt-Opt "Discovery Engine region (global|us|eu)" "global"
$BucketName  = Prompt-Req "GCS bucket name (globally unique)" "$ProjectId-$CompanySlug-mirror"
$DataStoreId = Prompt-Req "Data Store ID" "$CompanySlug-docs"
$EngineId    = Prompt-Req "Search Engine ID" "$CompanySlug-search"
$SaId        = Prompt-Req "Service Account short name" "$CompanySlug-sync-sa"
$SaEmail     = "$SaId@$ProjectId.iam.gserviceaccount.com"

# ============================================================= 6. CONNECTORS =
Write-Section "6/10  Data source connectors"
Write-Host "  Select which data sources to connect to your search engine."
Write-Host ""

$EnableDrive = Prompt-YN "  Google Drive?" $true
$DriveFolderId = ""
if ($EnableDrive) {
    Write-Host "    Open your Drive folder and copy the ID from the URL:"
    Write-Host "    https://drive.google.com/drive/folders/<THIS_IS_THE_ID>"
    $DriveFolderId = Prompt-Req "    Drive folder ID"
}

$EnableGmail = Prompt-YN "  Gmail? (indexes emails + attachments)" $false
$GmailSecret="client_secret.json"; $GmailQ="has:attachment"; $GmailAfter="2024/01/01"; $GmailProp=""
if ($EnableGmail) {
    Write-Host ""
    Write-Host "    Gmail requires a Desktop OAuth client ID."
    Write-Host "    Create one at:" -ForegroundColor Yellow
    Write-Host "    https://console.cloud.google.com/apis/credentials"
    Write-Host "    > Create Credentials > OAuth Client ID > Desktop app > Download JSON"
    Write-Host ""
    $GmailSecret = Prompt-Req "    Path to OAuth client_secret.json" "client_secret.json"
    $GmailQ      = Prompt-Req "    Gmail search query" "has:attachment"
    $GmailAfter  = Prompt-Opt "    Only messages after (YYYY/MM/DD)" "2024/01/01"
    $GmailProp   = Prompt-Opt "    Default property tag for Gmail" $PrimaryProp
}

$EnableLocal = Prompt-YN "  Local filesystem directory?" $false
$LocalPath = ""; if ($EnableLocal) { $LocalPath = Prompt-Req "    Absolute path" }

$UseHeuristic = Prompt-YN "  Enable filename heuristic classifier? (recommended)" $true
$DefaultProp  = if ($PrimaryProp) { $PrimaryProp } else { "null" }

# ============================================================= 7. EMAIL ====
Write-Section "7/10  Email (silent sending from the web UI)"
$EnableEmail = Prompt-YN "  Enable email? (sends documents + PDFs via Gmail SMTP)" $false
$EmailSender = ""; $EmailAppPw = "PASTE_APP_PASSWORD_HERE"
if ($EnableEmail) {
    $EmailSender = Prompt-Req "    Gmail sender address" $CompanyEmail
    Write-Host ""
    Write-Host "    You need a Gmail App Password (NOT your regular password)." -ForegroundColor Yellow
    Write-Host "    1. Enable 2-Factor Auth: https://myaccount.google.com/security"
    Write-Host "    2. Create App Password:  https://myaccount.google.com/apppasswords"
    Write-Host "       App name: 'AI Search' > Create > copy the 16-char password"
    Write-Host ""
    $EmailAppPw = Prompt-Opt "    App Password (paste here, or set later in config.yaml)" "PASTE_APP_PASSWORD_HERE"
}

# ============================================================= 8. ADMIN ====
Write-Section "8/10  Admin dashboard"
$AdminPw = Prompt-Opt "  Admin password (for cost/usage dashboard)" "0714"

# Cloud Run
Write-Host ""
$PollInterval   = Prompt-Opt "  Automated sync interval in minutes (15, 30, 60, 120, 360)" "60"
$CloudRunRegion = Prompt-Opt "  Cloud Run region" "us-central1"

# ============================================================= 9. CONFIG ===
Write-Section "9/10  Writing configuration"
$KeyPath = "service-account.json"
$PropsLine = if ($PrimaryProp) { "`n    - $PrimaryProp" } else { "" }
$LocalEsc  = if ($LocalPath) { $LocalPath.Replace('\','\\') } else { "" }
$GmailPropVal = if ($GmailProp) { $GmailProp } else { if ($PrimaryProp) { $PrimaryProp } else { "_inbox" } }

$cfg = @"
# Generated by install.ps1 on $(Get-Date -Format "yyyy-MM-dd HH:mm")
# Company: $CompanyName

project:
  id: $ProjectId
  location: $Location

company:
  name: "$CompanyName"
  phone: "$CompanyPhone"
  email: $CompanyEmail
  address: "$CompanyAddr"
  website: $CompanyWeb
  tagline: "$CompanyTag"
  logo: $LogoPath

admin:
  password: "$AdminPw"

gcs:
  bucket: $BucketName
  mirror_prefix: data
  manifest_prefix: _manifests

service_account:
  email: $SaEmail
  key_path: $KeyPath

data_store:
  id: $DataStoreId
  display_name: $CompanyName Documents
  industry_vertical: GENERIC
  solution_types: [SOLUTION_TYPE_CHAT, SOLUTION_TYPE_SEARCH]
  content_config: CONTENT_REQUIRED

engine:
  id: $EngineId
  display_name: $CompanyName Intelligent Search
  search_tier: SEARCH_TIER_ENTERPRISE
  search_add_ons: [SEARCH_ADD_ON_LLM]

email:
  sender: $EmailSender
  app_password: $EmailAppPw
  smtp_host: smtp.gmail.com
  smtp_port: 587

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
  heuristic_classification: $(YB $UseHeuristic)
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
    enabled: $(YB $EnableDrive)
    root_folder_id: $DriveFolderId
    mirror_as: Properties
    export_workspace_as: pdf
  gmail:
    enabled: $(YB $EnableGmail)
    client_secret_path: $GmailSecret
    query: "$GmailQ"
    after: "$GmailAfter"
    default_property: $GmailPropVal
    index_body: true
    index_attachments: true
  onedrive:
    enabled: false
  local_files:
    enabled: $(YB $EnableLocal)
    path: "$LocalEsc"
    mirror_as: Properties
  csv:
    enabled: false
"@

(Join-Path $RepoRoot "config\config.yaml") | ForEach-Object { $cfg | Out-File -FilePath $_ -Encoding UTF8 }
Write-Ok "wrote config/config.yaml"
@"
GOOGLE_APPLICATION_CREDENTIALS=$RepoRoot\$KeyPath
GOOGLE_CLOUD_PROJECT=$ProjectId
"@ | Out-File -FilePath (Join-Path $RepoRoot ".env") -Encoding UTF8
Write-Ok "wrote .env"

# ============================================================= 10. BOOTSTRAP =
Write-Section "10/10  GCP resource bootstrap"
& gcloud config set project $ProjectId 2>&1 | Out-Null
try { & gcloud auth application-default set-quota-project $ProjectId 2>&1 | Out-Null } catch {}

if ($SkipBootstrap) { Write-Warn "skipping (--SkipBootstrap)" }
else {
    if (Prompt-YN "Run bootstrap now? (creates APIs, SA, bucket, data store, engine)" $true) {
        & $PyExe (Join-Path $RepoRoot "scripts\bootstrap.py") --sa-id $SaId
        if ($LASTEXITCODE -ne 0) { Write-Err "bootstrap failed"; exit 1 }
    }
}

# ============================================================= NEXT STEPS ===
Write-Section "SETUP COMPLETE"

if ($EnableDrive -and $DriveFolderId) {
    Write-Host ""
    Write-Host "  STEP 1 — SHARE YOUR DRIVE FOLDER" -ForegroundColor Yellow
    Write-Host "    Open: https://drive.google.com/drive/folders/$DriveFolderId"
    Write-Host "    Click Share > paste this email > Viewer role > Share:"
    Write-Host "    $SaEmail" -ForegroundColor Cyan
}
if ($EnableGmail) {
    Write-Host ""
    Write-Host "  STEP 2 — GMAIL SETUP" -ForegroundColor Yellow
    Write-Host "    1. Put client_secret.json at: $RepoRoot\$GmailSecret"
    Write-Host "    2. Enable Gmail API: gcloud services enable gmail.googleapis.com"
    Write-Host "    3. First sync pops a browser: python scripts\sync.py --only gmail"
}
if ($EnableEmail -and $EmailAppPw -eq "PASTE_APP_PASSWORD_HERE") {
    Write-Host ""
    Write-Host "  STEP 3 — EMAIL APP PASSWORD" -ForegroundColor Yellow
    Write-Host "    1. Enable 2FA: https://myaccount.google.com/security"
    Write-Host "    2. Create App Password: https://myaccount.google.com/apppasswords"
    Write-Host "    3. Paste it in config/config.yaml under email.app_password"
}

Write-Host ""
Write-Host "  RUN THE PIPELINE:" -ForegroundColor Cyan
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "    python scripts\doctor.py              # health check"
Write-Host "    python scripts\sync.py                # pull files from Drive"
Write-Host "    python scripts\index.py --full         # classify + import to Vertex AI"
Write-Host "    python scripts\web.py                  # launch web UI (port 5000)"
Write-Host ""
Write-Host "  DEPLOY AUTOMATED SYNC:" -ForegroundColor Cyan
Write-Host "    python scripts\deploy.py               # Cloud Run + Scheduler"
Write-Host ""
Write-Host "  ADMIN DASHBOARD:" -ForegroundColor Cyan
Write-Host "    Click the gear icon in the sidebar > password: $AdminPw"
Write-Host ""
Write-Host "DONE" -ForegroundColor Green
Write-Host ""

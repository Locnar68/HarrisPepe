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

function Prompt-Required([string]$Question, [string]$Default = "") {
    if ($NonInteractive) {
        if (-not $Default) { throw "NonInteractive: $Question has no default" }
        return $Default
    }
    while ($true) {
        $prompt = if ($Default) { "$Question [$Default]" } else { "$Question" }
        $val = Read-Host $prompt
        if ([string]::IsNullOrWhiteSpace($val)) { $val = $Default }
        if ($val) { return $val }
        Write-Warn "  required."
    }
}
function Prompt-Optional([string]$Question, [string]$Default = "") {
    if ($NonInteractive) { return $Default }
    $prompt = if ($Default) { "$Question [$Default]" } else { "$Question (leave blank to skip)" }
    $val = Read-Host $prompt
    if ([string]::IsNullOrWhiteSpace($val)) { return $Default }
    return $val
}
function Prompt-YesNo([string]$Question, [bool]$Default = $true) {
    if ($NonInteractive) { return $Default }
    $def = if ($Default) { "Y/n" } else { "y/N" }
    $val = (Read-Host "$Question [$def]").Trim().ToLower()
    if ([string]::IsNullOrWhiteSpace($val)) { return $Default }
    return ($val -eq "y" -or $val -eq "yes")
}

# -------------------------------------------------------------- 1. prereqs --
Write-Section "VERTEX AI SMB BOOTSTRAPPER"
Write-Host "Repo: $RepoRoot"

Write-Section "1/7  Prerequisites"

try { $py = (& python --version) 2>&1; Write-Ok "Python: $py" }
catch { Write-Err "Python 3.10+ required. https://www.python.org/downloads/"; exit 1 }

try { $gc = (& gcloud --version | Select-Object -First 1); Write-Ok "gcloud: $gc" }
catch { Write-Err "gcloud required. https://cloud.google.com/sdk/docs/install"; exit 1 }

# -------------------------------------------------------------- 2. venv ----
Write-Section "2/7  Python environment"

$VenvPath = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $VenvPath)) {
    Write-Step "Creating virtual environment at $VenvPath"
    & python -m venv $VenvPath
}
Write-Ok ".venv ready"

$PyExe = Join-Path $VenvPath "Scripts\python.exe"
Write-Step "Installing requirements"
& $PyExe -m pip install --quiet --upgrade pip
& $PyExe -m pip install --quiet -r (Join-Path $RepoRoot "requirements.txt")
Write-Ok "requirements installed"

# -------------------------------------------------------------- 3. gcloud auth --
Write-Section "3/7  Google Cloud authentication"

$activeAcct = ""
try {
    $activeAcct = (& gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null).Trim()
} catch {}

if ($activeAcct) {
    Write-Ok "gcloud signed in as $activeAcct"
} else {
    if (Prompt-YesNo "Sign into gcloud now? (opens a browser)" $true) {
        & gcloud auth login
        $activeAcct = (& gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null).Trim()
        Write-Ok "gcloud signed in as $activeAcct"
    } else {
        Write-Err "Aborting — gcloud sign-in required."
        exit 1
    }
}

# -------------------------------------------------------------- 4. config --
Write-Section "4/7  Project configuration"

$CurrentProject = ""
try { $CurrentProject = (& gcloud config get-value project 2>$null).Trim() } catch {}
if ($CurrentProject -eq "(unset)") { $CurrentProject = "" }

$ProjectId    = Prompt-Required "GCP Project ID" $CurrentProject
$Location     = Prompt-Optional  "Discovery Engine region (global|us|eu)" "global"
$BusinessName = Prompt-Required  "Business short name (used for resource ids, e.g. 'acme')" ""
$BusinessSlug = ($BusinessName -replace '[^a-zA-Z0-9-]', '-').ToLower().Trim('-')

$BucketName   = Prompt-Required  "GCS bucket name (globally unique)" "$ProjectId-$BusinessSlug-mirror"
$DataStoreId  = Prompt-Required  "Data Store ID" "$BusinessSlug-docs"
$EngineId     = Prompt-Required  "Search Engine ID" "$BusinessSlug-search"
$SaId         = Prompt-Required  "Service Account short name" "$BusinessSlug-sync-sa"

Write-Host ""
Write-Host "Connectors — which data sources should be enabled?"

$EnableDrive   = Prompt-YesNo "  Google Drive?" $true
$DriveFolderId = ""
if ($EnableDrive) {
    $DriveFolderId = Prompt-Required "    Drive folder ID (from the folder URL: /folders/<ID>)" ""
}

$EnableLocal   = Prompt-YesNo "  Local filesystem directory?" $false
$LocalPath     = ""
if ($EnableLocal) {
    $LocalPath = Prompt-Required "    Absolute path to directory" ""
}

$EnableGmail   = Prompt-YesNo "  Gmail (Phase 2 stub, no-op for now)?" $false
$EnableOneDrive = Prompt-YesNo "  OneDrive (Phase 2 stub, no-op for now)?" $false
$EnableCsv     = Prompt-YesNo "  CSV import (Phase 2 stub, no-op for now)?" $false

Write-Host ""
Write-Host "Metadata classification"
$UseHeuristic = Prompt-YesNo "  Enable filename heuristic classifier? (recommended for flat folders)" $true
$DefaultProperty = ""
if ($UseHeuristic) {
    $DefaultProperty = Prompt-Optional "    Default property tag if filename doesn't name one" ""
}

# -------------------------------------------------------------- 5. write cfg --
Write-Section "5/7  Writing config/config.yaml"

$SaEmail  = "$SaId@$ProjectId.iam.gserviceaccount.com"
$BusinessDisplay = (Get-Culture).TextInfo.ToTitleCase($BusinessName)
$KeyPath  = "service-account.json"

function Yaml-Str([string]$s) { if ($s) { return $s } else { return '""' } }
function Yaml-Bool([bool]$b) { return $b.ToString().ToLower() }

$propertiesBlock = if ($DefaultProperty) { "`n    - $DefaultProperty" } else { "" }
$defaultPropertyLine = if ($DefaultProperty) { "$DefaultProperty" } else { "null" }
$localPathEscaped = if ($LocalPath) { $LocalPath.Replace('\','\\') } else { "" }

$cfg = @"
# Generated by install.ps1 on $(Get-Date -Format "yyyy-MM-dd HH:mm")
# Safe to edit by hand — re-running install.ps1 will overwrite.

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
  display_name: $BusinessDisplay Documents
  industry_vertical: GENERIC
  solution_types:
    - SOLUTION_TYPE_CHAT
    - SOLUTION_TYPE_SEARCH
  content_config: CONTENT_REQUIRED

engine:
  id: $EngineId
  display_name: $BusinessDisplay Intelligent Search
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
  properties: [$propertiesBlock
  ]
  heuristic_classification: $(Yaml-Bool $UseHeuristic)
  default_property: $defaultPropertyLine
  heuristic_rules:
    - { pattern: "\\.(jpg|jpeg|png|gif|bmp|tiff|webp)`$", doc_type: image }
    - { pattern: "^inv[_\\s-]|invoice|receipt|bill",        doc_type: billing }
    - { pattern: "permit|inspection|code|zoning",           doc_type: permit }
    - { pattern: "p&l|statement|bank|appraisal|balance",    doc_type: finance }
    - { pattern: "contract|closing|deed|title|ein|entity|llc|sow", doc_type: legal }

connectors:

  drive:
    enabled: $(Yaml-Bool $EnableDrive)
    root_folder_id: $(Yaml-Str $DriveFolderId)
    mirror_as: Properties
    export_workspace_as: pdf

  gmail:
    enabled: $(Yaml-Bool $EnableGmail)

  onedrive:
    enabled: $(Yaml-Bool $EnableOneDrive)

  local_files:
    enabled: $(Yaml-Bool $EnableLocal)
    path: "$localPathEscaped"
    mirror_as: Properties

  csv:
    enabled: $(Yaml-Bool $EnableCsv)
"@

$cfgPath = Join-Path $RepoRoot "config\config.yaml"
$cfg | Out-File -FilePath $cfgPath -Encoding UTF8
Write-Ok "wrote $cfgPath"

# Write .env
$envPath = Join-Path $RepoRoot ".env"
@"
GOOGLE_APPLICATION_CREDENTIALS=$RepoRoot\$KeyPath
GOOGLE_CLOUD_PROJECT=$ProjectId
"@ | Out-File -FilePath $envPath -Encoding UTF8
Write-Ok "wrote .env"

# -------------------------------------------------------------- 6. gcloud project --
Write-Section "6/7  Activating project + ADC"

Write-Step "gcloud config set project $ProjectId"
& gcloud config set project $ProjectId | Out-Null

Write-Step "Setting ADC quota project to $ProjectId"
& gcloud auth application-default set-quota-project $ProjectId 2>&1 | Out-Null

# Billing check (non-fatal)
try {
    $billing = (& gcloud beta billing projects describe $ProjectId --format="value(billingEnabled)" 2>$null).Trim()
    if ($billing -eq "True") { Write-Ok "billing enabled on $ProjectId" }
    else { Write-Warn "billing NOT enabled — bootstrap will fail on API enable. Link a billing account before proceeding." }
} catch { Write-Warn "couldn't verify billing state: $_" }

# -------------------------------------------------------------- 7. bootstrap --
Write-Section "7/7  GCP resource bootstrap"

if ($SkipBootstrap) {
    Write-Warn "skipping bootstrap (--SkipBootstrap). Run later: python scripts\bootstrap.py"
} else {
    if (Prompt-YesNo "Run the bootstrap now? (enable APIs, create SA, bucket, data store, engine)" $true) {
        & $PyExe (Join-Path $RepoRoot "scripts\bootstrap.py") --sa-id $SaId
        if ($LASTEXITCODE -ne 0) {
            Write-Err "bootstrap failed — see output above"
            exit 1
        }
    } else {
        Write-Warn "skipped. Run later with: python scripts\bootstrap.py"
    }
}

# -------------------------------------------------------------- NEXT --------
Write-Section "NEXT STEPS"

if ($EnableDrive -and $DriveFolderId) {
    Write-Host ""
    Write-Host "  IMPORTANT — share your Drive folder with the service account:" -ForegroundColor Yellow
    Write-Host "    1. Open https://drive.google.com/drive/folders/$DriveFolderId" -ForegroundColor White
    Write-Host "    2. Click Share"
    Write-Host "    3. Paste:  $SaEmail" -ForegroundColor Cyan
    Write-Host "    4. Role:   Viewer"
    Write-Host "    5. Click Share (uncheck 'Notify people' if shown)"
}

Write-Host ""
Write-Host "  Run the pipeline:"
Write-Host ""
Write-Host "    .\.venv\Scripts\Activate.ps1" -ForegroundColor Cyan
Write-Host "    python scripts\doctor.py           # verify health" -ForegroundColor Cyan
Write-Host "    python scripts\sync.py --dry-run   # preview what would sync" -ForegroundColor Cyan
Write-Host "    python scripts\sync.py             # pull data into GCS" -ForegroundColor Cyan
Write-Host "    python scripts\index.py            # extract metadata + import" -ForegroundColor Cyan
Write-Host "    python scripts\query.py ""...""     # ask questions" -ForegroundColor Cyan
Write-Host ""
Write-Host "INSTALLATION COMPLETE" -ForegroundColor Green
Write-Host ""

# ============================================================================
# Phase 3 Bootstrap — bootstrap.ps1 (patched rc2)
# Fixes:
#   - -SkipPrereqs now also tells the Python installer to skip its checks
#   - Exit code from Python installer is properly propagated
# ============================================================================

[CmdletBinding()]
param(
    [switch]$Resume,
    [switch]$Verify,
    [switch]$SkipPrereqs,
    [string]$InstallPath = "",
    [switch]$NonInteractive,
    [string]$ConfigFile = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

function Write-Banner {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " Phase 3 Bootstrap — Vertex AI RAG Turnkey Installer" -ForegroundColor Cyan
    Write-Host " HarrisPepe / vertex-ai-search" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step { param([string]$Msg) Write-Host ""; Write-Host ">>> $Msg" -ForegroundColor Green }
function Write-Info { param([string]$Msg) Write-Host "    $Msg" -ForegroundColor Gray }
function Write-Warn { param([string]$Msg) Write-Host "    ! $Msg" -ForegroundColor Yellow }
function Write-Err  { param([string]$Msg) Write-Host "    X $Msg" -ForegroundColor Red }

function Test-Cmd {
    param([string]$Name)
    $null = Get-Command $Name -ErrorAction SilentlyContinue
    return $?
}

function Get-PythonVersion {
    param([string]$PythonExe)
    try {
        $v = & $PythonExe --version 2>&1
        if ($v -match 'Python (\d+)\.(\d+)') {
            return [Version]"$($Matches[1]).$($Matches[2])"
        }
    } catch { }
    return $null
}

function Install-WithWinget {
    param([string]$Id, [string]$FriendlyName)
    if (-not (Test-Cmd "winget")) {
        Write-Err "winget is not available on this machine."
        return $false
    }
    Write-Info "Running: winget install --id $Id -e --silent"
    $p = Start-Process -FilePath "winget" `
        -ArgumentList "install", "--id", $Id, "-e", "--silent", "--accept-source-agreements", "--accept-package-agreements" `
        -Wait -PassThru -NoNewWindow
    if ($p.ExitCode -ne 0) {
        Write-Warn "winget returned exit code $($p.ExitCode) — may already be installed."
        return $false
    }
    return $true
}

function Prompt-YesNo {
    param([string]$Question, [bool]$Default = $true)
    if ($NonInteractive) { return $Default }
    $suffix = if ($Default) { "(Y/n)" } else { "(y/N)" }
    while ($true) {
        $ans = Read-Host "    ? $Question $suffix"
        if ([string]::IsNullOrWhiteSpace($ans)) { return $Default }
        switch ($ans.ToLower()) {
            "y"   { return $true }
            "yes" { return $true }
            "n"   { return $false }
            "no"  { return $false }
        }
    }
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

Write-Banner

Write-Step "Checking PowerShell version"
if ($PSVersionTable.PSVersion.Major -lt 5) {
    Write-Err "PowerShell 5.1+ required. You have $($PSVersionTable.PSVersion)."
    exit 1
}
Write-Info "PowerShell $($PSVersionTable.PSVersion) — OK"

Write-Step "Ensuring script execution policy for this session"
try {
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force -ErrorAction Stop
    Write-Info "Process-scope ExecutionPolicy = Bypass"
} catch {
    Write-Warn "Could not set process-scope execution policy: $_"
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir
if ([string]::IsNullOrWhiteSpace($InstallPath)) { $InstallPath = $ScriptDir }
Write-Info "Script directory: $ScriptDir"
Write-Info "Install target:   $InstallPath"

# --- Prereq checks (wrapper side) ---
if (-not $SkipPrereqs) {
    Write-Step "Checking Python 3.10+"
    $pythonExe = $null
    foreach ($c in @("python", "python3", "py")) {
        if (Test-Cmd $c) {
            $v = Get-PythonVersion $c
            if ($v -and $v -ge [Version]"3.10") {
                $pythonExe = $c
                Write-Info "Found $c (version $v)"
                break
            }
        }
    }
    if (-not $pythonExe) {
        Write-Warn "Python 3.10+ not found."
        if (Prompt-YesNo "Install Python 3.12 via winget now?" $true) {
            if (Install-WithWinget "Python.Python.3.12" "Python 3.12") {
                Write-Warn "Python installed. Close this window and re-run."
                exit 2
            }
        }
        Write-Err "Python 3.10+ is required."
        exit 1
    }

    Write-Step "Checking Google Cloud SDK (gcloud)"
    if (-not (Test-Cmd "gcloud")) {
        Write-Warn "gcloud CLI not found."
        if (Prompt-YesNo "Install Google Cloud SDK via winget now?" $true) {
            if (Install-WithWinget "Google.CloudSDK" "Google Cloud SDK") {
                Write-Warn "gcloud installed. Close this window and re-run."
                exit 2
            }
        }
        Write-Err "gcloud CLI is required."
        exit 1
    }
    $gcv = & gcloud --version 2>&1 | Select-Object -First 1
    Write-Info "Found: $gcv"

    Write-Step "Checking git"
    if (-not (Test-Cmd "git")) {
        Write-Warn "git not found."
        if (Prompt-YesNo "Install git via winget now?" $true) {
            Install-WithWinget "Git.Git" "Git" | Out-Null
        }
    } else {
        Write-Info "Found: $(git --version)"
    }
} else {
    Write-Warn "Skipping prereq checks (-SkipPrereqs)"
    $pythonExe = "python"
}

# --- venv ---
Write-Step "Preparing Python virtual environment"
$venvPath = Join-Path $ScriptDir ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Info "Creating .venv ..."
    & $pythonExe -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { Write-Err "Failed to create venv."; exit 1 }
}
$venvPython = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Write-Err "venv Python not found at $venvPython"; exit 1 }
Write-Info "Using venv Python: $venvPython"

# --- deps ---
Write-Step "Installing Python dependencies"
& $venvPython -m pip install --upgrade pip --quiet
$reqFile = Join-Path $ScriptDir "requirements.txt"
& $venvPython -m pip install -r $reqFile --quiet
if ($LASTEXITCODE -ne 0) { Write-Err "pip install failed."; exit 1 }
Write-Info "Dependencies installed."

# --- launch ---
Write-Step "Launching Python installer"
$pyArgs = @("-m", "installer")
if ($Resume)         { $pyArgs += "--resume" }
if ($Verify)         { $pyArgs += "--verify" }
if ($NonInteractive) { $pyArgs += "--non-interactive" }
if ($SkipPrereqs)    { $pyArgs += "--skip-prereqs" }   # <-- NEW: thread it through
if ($ConfigFile)     { $pyArgs += @("--config", $ConfigFile) }
if ($InstallPath -ne $ScriptDir) { $pyArgs += @("--install-path", $InstallPath) }

$env:PYTHONPATH  = $ScriptDir
$env:PHASE3_HOME = $ScriptDir

& $venvPython @pyArgs
$rc = $LASTEXITCODE

Write-Host ""
if ($rc -eq 0) {
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host " Phase 3 bootstrap complete." -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host " Phase 3 bootstrap exited with code $rc." -ForegroundColor Red
    Write-Host " Re-run with: .\bootstrap.ps1 -Resume" -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Red
}
exit $rc

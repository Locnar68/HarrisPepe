# ============================================================================
#  publish.ps1 — push the repo to GitHub via gh CLI.
#
#  Run from repo root:  .\publish.ps1
#  Or non-interactively:  .\publish.ps1 -RepoName my-repo -Public
# ============================================================================

[CmdletBinding()]
param(
    [string]$RepoName = "",
    [switch]$Public,
    [switch]$Private,
    [string]$Tag = "v1.0.0",
    [string]$CommitMessage = "Phase 1 — Visual-first RAG"
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor Cyan
}
function Write-Ok([string]$M)   { Write-Host "  ✓ $M" -ForegroundColor Green }
function Write-Step([string]$M) { Write-Host "  → $M" -ForegroundColor Yellow }
function Write-Err([string]$M)  { Write-Host "  ✗ $M" -ForegroundColor Red }

# ---------------------------------------------------------------- prereqs --
Write-Section "PUBLISH TO GITHUB"

try { git --version  | Out-Null; Write-Ok "git available" }
catch { Write-Err "git not found. Install: https://git-scm.com/downloads"; exit 1 }

try { gh --version | Out-Null; Write-Ok "gh CLI available" }
catch { Write-Err "gh CLI not found. Install: https://cli.github.com/"; exit 1 }

# gh auth
$authOk = $false
try { gh auth status 2>&1 | Out-Null; $authOk = ($LASTEXITCODE -eq 0) } catch {}
if (-not $authOk) {
    Write-Step "gh not authenticated, launching gh auth login"
    gh auth login
}
Write-Ok "gh authenticated"

$ghUser = (gh api user --jq .login 2>$null).Trim()
if (-not $ghUser) { Write-Err "Could not determine GitHub username"; exit 1 }
Write-Ok "GitHub user: $ghUser"

# ---------------------------------------------------------------- safety check --
Write-Section "Safety check — files that must NOT be committed"

$dangerous = @(
    "service-account.json",
    ".env",
    "config\config.yaml"
)
$found = @()
foreach ($f in $dangerous) {
    $p = Join-Path $RepoRoot $f
    if (Test-Path $p) {
        # Is it gitignored?
        Push-Location $RepoRoot
        $ignored = (git check-ignore $f 2>$null)
        Pop-Location
        if (-not $ignored) {
            $found += $f
            Write-Err "$f EXISTS and is NOT gitignored"
        } else {
            Write-Ok "$f exists but is gitignored"
        }
    } else {
        Write-Ok "$f not present"
    }
}
if ($found.Count -gt 0) {
    Write-Err "aborting — the above files would be pushed publicly. Fix .gitignore first."
    exit 1
}

# ---------------------------------------------------------------- git init / staging --
Write-Section "Preparing commit"

Push-Location $RepoRoot
try {
    if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
        Write-Step "git init -b main"
        git init -b main | Out-Null
    } else {
        Write-Ok ".git already initialized"
    }

    # Configure user.name/email if not set (local only, not global)
    $localName  = (git config user.name 2>$null)
    $localEmail = (git config user.email 2>$null)
    if (-not $localName)  { git config user.name  "$ghUser"             | Out-Null }
    if (-not $localEmail) { git config user.email "$ghUser@users.noreply.github.com" | Out-Null }

    git add -A | Out-Null

    $staged = git diff --cached --name-only
    if (-not $staged) {
        Write-Ok "nothing to commit"
    } else {
        Write-Step "committing: $CommitMessage"
        git commit -m "$CommitMessage" | Out-Null
        Write-Ok "commit created"
    }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------- repo name --
Write-Section "GitHub repo"

if (-not $RepoName) {
    $default = (Split-Path $RepoRoot -Leaf)
    $RepoName = Read-Host "Repo name [$default]"
    if ([string]::IsNullOrWhiteSpace($RepoName)) { $RepoName = $default }
}

# Visibility
if ($Public -and $Private) {
    Write-Err "Pick one: -Public or -Private, not both"; exit 1
}
$visibility = $null
if ($Public)  { $visibility = "--public"  }
if ($Private) { $visibility = "--private" }
if (-not $visibility) {
    $vis = (Read-Host "Visibility — public / private [private]").Trim().ToLower()
    if ($vis -eq "public") { $visibility = "--public" }
    else                    { $visibility = "--private" }
}

# Does the repo already exist under $ghUser?
$exists = $false
gh repo view "$ghUser/$RepoName" 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { $exists = $true }

Push-Location $RepoRoot
try {
    if ($exists) {
        Write-Step "repo $ghUser/$RepoName already exists, pushing"
        # Ensure origin is set
        $hasOrigin = (git remote 2>$null | Select-String "^origin$")
        if (-not $hasOrigin) {
            $url = "https://github.com/$ghUser/$RepoName.git"
            git remote add origin $url | Out-Null
            Write-Ok "added origin $url"
        }
        git branch -M main | Out-Null
        git push -u origin main
    } else {
        Write-Step "creating new repo: gh repo create $RepoName $visibility --source=. --push"
        gh repo create $RepoName $visibility --source=. --push
    }

    Write-Step "tagging $Tag"
    $existingTag = (git tag --list $Tag)
    if ($existingTag) {
        Write-Ok "tag $Tag already exists locally"
    } else {
        git tag -a $Tag -m "$CommitMessage" | Out-Null
    }
    git push origin $Tag 2>&1 | Out-Null
    Write-Ok "pushed tag $Tag"
} finally {
    Pop-Location
}

# ---------------------------------------------------------------- done --
Write-Section "DONE"

$url = "https://github.com/$ghUser/$RepoName"
Write-Host ""
Write-Host "Repo:  $url" -ForegroundColor Green
Write-Host "Tag:   $url/releases/tag/$Tag" -ForegroundColor Green
Write-Host ""
Write-Host "Share with Harris — he runs this on his machine:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  winget install GitHub.cli Git.Git Python.Python.3.12 Google.CloudSDK"
Write-Host "  gh auth login"
Write-Host "  cd C:\dev                         # or any directory"
Write-Host "  gh repo clone $ghUser/$RepoName"
Write-Host "  cd $RepoName"
Write-Host "  .\install.ps1"
Write-Host ""

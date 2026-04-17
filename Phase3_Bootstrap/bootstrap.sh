#!/usr/bin/env bash
# ============================================================================
# Phase 3 Bootstrap — bootstrap.sh
#
# The ONE command for Linux / macOS. Parity with bootstrap.ps1.
#
# Usage:
#   ./bootstrap.sh                              # full install
#   ./bootstrap.sh --resume                     # resume from last checkpoint
#   ./bootstrap.sh --verify                     # post-install verification
#   ./bootstrap.sh --skip-prereqs               # skip host-machine checks
#   ./bootstrap.sh --install-path /opt/vertex   # override install location
#   ./bootstrap.sh --non-interactive            # for CI
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
RESUME=false
VERIFY=false
SKIP_PREREQS=false
NON_INTERACTIVE=false
INSTALL_PATH=""
CONFIG_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --resume)          RESUME=true; shift ;;
        --verify)          VERIFY=true; shift ;;
        --skip-prereqs)    SKIP_PREREQS=true; shift ;;
        --non-interactive) NON_INTERACTIVE=true; shift ;;
        --install-path)    INSTALL_PATH="$2"; shift 2 ;;
        --config)          CONFIG_FILE="$2"; shift 2 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# Colors & output helpers
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
    CYAN=$'\033[0;36m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'
    RED=$'\033[0;31m'; GRAY=$'\033[0;90m'; NC=$'\033[0m'
else
    CYAN=""; GREEN=""; YELLOW=""; RED=""; GRAY=""; NC=""
fi

banner() {
    echo
    echo "${CYAN}============================================================${NC}"
    echo "${CYAN} Phase 3 Bootstrap — Vertex AI RAG Turnkey Installer${NC}"
    echo "${CYAN} HarrisPepe / vertex-ai-search${NC}"
    echo "${CYAN}============================================================${NC}"
    echo
}
step() { echo; echo "${GREEN}>>> $*${NC}"; }
info() { echo "${GRAY}    $*${NC}"; }
warn() { echo "${YELLOW}    ! $*${NC}"; }
err()  { echo "${RED}    X $*${NC}"; }

prompt_yn() {
    local question="$1" default="${2:-y}" ans
    if $NON_INTERACTIVE; then [[ "$default" == "y" ]]; return $?; fi
    local suffix="(Y/n)"; [[ "$default" != "y" ]] && suffix="(y/N)"
    while true; do
        read -r -p "    ? $question $suffix " ans
        ans="${ans:-$default}"
        case "$ans" in
            y|Y|yes|YES) return 0 ;;
            n|N|no|NO)   return 1 ;;
        esac
    done
}

detect_os() {
    case "$(uname -s)" in
        Linux*)  echo "linux" ;;
        Darwin*) echo "macos" ;;
        *)       echo "unknown" ;;
    esac
}

find_python() {
    for c in python3.12 python3.11 python3.10 python3 python; do
        if command -v "$c" >/dev/null 2>&1; then
            local v
            v=$("$c" --version 2>&1 | awk '{print $2}')
            local major minor
            major=$(echo "$v" | cut -d. -f1)
            minor=$(echo "$v" | cut -d. -f2)
            if [[ "$major" -eq 3 && "$minor" -ge 10 ]] || [[ "$major" -gt 3 ]]; then
                echo "$c"
                return 0
            fi
        fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
banner

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
INSTALL_PATH="${INSTALL_PATH:-$SCRIPT_DIR}"
OS=$(detect_os)
info "Script directory: $SCRIPT_DIR"
info "Install target:   $INSTALL_PATH"
info "Operating system: $OS"

# --- Prereq: Python ---
if ! $SKIP_PREREQS; then
    step "Checking Python 3.10+"
    if PYTHON_EXE=$(find_python); then
        info "Found $PYTHON_EXE ($("$PYTHON_EXE" --version))"
    else
        warn "Python 3.10+ not found."
        if prompt_yn "Attempt to install Python now?" y; then
            case "$OS" in
                macos)
                    if command -v brew >/dev/null 2>&1; then
                        brew install python@3.12
                    else
                        err "Install Homebrew first: https://brew.sh  OR  install Python from https://www.python.org/downloads/"
                        exit 1
                    fi
                    ;;
                linux)
                    if command -v apt-get >/dev/null 2>&1; then
                        sudo apt-get update && sudo apt-get install -y python3.12 python3.12-venv python3-pip || \
                        sudo apt-get install -y python3 python3-venv python3-pip
                    elif command -v dnf >/dev/null 2>&1; then
                        sudo dnf install -y python3.12 python3-pip || sudo dnf install -y python3 python3-pip
                    elif command -v pacman >/dev/null 2>&1; then
                        sudo pacman -S --noconfirm python python-pip
                    else
                        err "Unknown package manager. Install Python 3.10+ manually."
                        exit 1
                    fi
                    ;;
                *) err "Unsupported OS. Install Python 3.10+ manually."; exit 1 ;;
            esac
            PYTHON_EXE=$(find_python) || { err "Python still not found after install."; exit 1; }
        else
            err "Python 3.10+ is required."
            exit 1
        fi
    fi

    # --- Prereq: gcloud CLI ---
    step "Checking Google Cloud SDK (gcloud)"
    if ! command -v gcloud >/dev/null 2>&1; then
        warn "gcloud CLI not found."
        if prompt_yn "Install gcloud CLI now?" y; then
            case "$OS" in
                macos)
                    if command -v brew >/dev/null 2>&1; then
                        brew install --cask google-cloud-sdk
                    else
                        err "Install manually: https://cloud.google.com/sdk/docs/install-sdk"
                        exit 1
                    fi
                    ;;
                linux)
                    info "Installing gcloud via official install script..."
                    curl -sSL https://sdk.cloud.google.com | bash
                    # shellcheck disable=SC1091
                    source "$HOME/google-cloud-sdk/path.bash.inc"
                    ;;
                *) err "Install gcloud manually: https://cloud.google.com/sdk/docs/install"; exit 1 ;;
            esac
        else
            err "gcloud CLI is required."
            exit 1
        fi
    else
        info "Found: $(gcloud --version | head -1)"
    fi

    # --- Prereq: git ---
    step "Checking git"
    if ! command -v git >/dev/null 2>&1; then
        warn "git not found — recommended but not required."
    else
        info "Found: $(git --version)"
    fi
else
    warn "Skipping prereq checks (--skip-prereqs)"
    PYTHON_EXE=$(find_python || echo "python3")
fi

# --- Create venv ---
step "Preparing Python virtual environment"
VENV_PATH="$SCRIPT_DIR/.venv"
if [[ ! -d "$VENV_PATH" ]]; then
    info "Creating .venv ..."
    "$PYTHON_EXE" -m venv "$VENV_PATH"
fi
VENV_PY="$VENV_PATH/bin/python"
info "Using venv Python: $VENV_PY"

# --- Install deps ---
step "Installing Python dependencies"
"$VENV_PY" -m pip install --upgrade pip --quiet
"$VENV_PY" -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
info "Dependencies installed."

# --- Launch Python installer ---
step "Launching Python installer"
args=("-m" "installer")
$RESUME          && args+=("--resume")
$VERIFY          && args+=("--verify")
$NON_INTERACTIVE && args+=("--non-interactive")
[[ -n "$CONFIG_FILE"  ]] && args+=("--config" "$CONFIG_FILE")
[[ "$INSTALL_PATH" != "$SCRIPT_DIR" ]] && args+=("--install-path" "$INSTALL_PATH")

export PYTHONPATH="$SCRIPT_DIR"
export PHASE3_HOME="$SCRIPT_DIR"

if "$VENV_PY" "${args[@]}"; then
    echo
    echo "${GREEN}============================================================${NC}"
    echo "${GREEN} Phase 3 bootstrap complete.${NC}"
    echo "${GREEN}============================================================${NC}"
else
    rc=$?
    echo
    echo "${RED}============================================================${NC}"
    echo "${RED} Phase 3 bootstrap exited with code $rc.${NC}"
    echo "${YELLOW} Re-run with: ./bootstrap.sh --resume${NC}"
    echo "${RED}============================================================${NC}"
    exit "$rc"
fi

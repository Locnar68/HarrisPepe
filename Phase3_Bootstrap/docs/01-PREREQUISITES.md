# 01 — Prerequisites

Everything you need before running `.\bootstrap.ps1` / `./bootstrap.sh`. **If any of this is missing on the target machine, the bootstrap script will detect it and offer to install it for you** — this document exists for the cases where the automation fails or the operator wants to prepare manually.

---

## Required on the host machine

### Python 3.10 or newer

| Platform | Install method |
|---|---|
| Windows | `winget install --id Python.Python.3.12 -e --silent` |
| macOS (Homebrew) | `brew install python@3.12` |
| Ubuntu / Debian | `sudo apt-get install -y python3.12 python3.12-venv python3-pip` |
| Fedora / RHEL | `sudo dnf install -y python3.12 python3-pip` |
| Manual | https://www.python.org/downloads/ |

> **Note on PATH:** After installing Python on Windows, **close and re-open PowerShell** before re-running the bootstrap — PowerShell caches `$env:PATH` at launch.

### Google Cloud SDK (`gcloud`)

| Platform | Install method |
|---|---|
| Windows | `winget install --id Google.CloudSDK -e --silent` |
| macOS (Homebrew) | `brew install --cask google-cloud-sdk` |
| Linux (all) | `curl -sSL https://sdk.cloud.google.com \| bash` |
| Manual | https://cloud.google.com/sdk/docs/install |

After install, verify with `gcloud --version`. You do **not** need to run `gcloud init` manually — the installer will prompt you to sign in.

### Git (recommended, not strictly required)

Needed only if you intend to push Phase 3 back to the HarrisPepe GitHub repo.

| Platform | Install method |
|---|---|
| Windows | `winget install --id Git.Git -e --silent` |
| macOS | `brew install git` (or use Xcode Command Line Tools) |
| Linux | `sudo apt-get install -y git` / `sudo dnf install -y git` |

### GitHub CLI (optional)

Convenient for tagging releases and pushing Phase 3.

```powershell
winget install --id GitHub.cli -e --silent
gh auth login
```

---

## Required in the cloud

### Google Cloud account

**If you don't have one**, sign up here: **https://cloud.google.com/free**

New accounts get a $300 free credit valid for 90 days — more than enough to run Phase 3 end-to-end on a small corpus. See [`03-GCP_ACCOUNT_SETUP.md`](03-GCP_ACCOUNT_SETUP.md) for a walkthrough.

### A billing account linked to the project

Vertex AI Search refuses to provision on unbilled projects, even for trial use. You don't need to incur charges — your free credit covers the POC — but billing must be "enabled" on the project.

**Link billing:** https://console.cloud.google.com/billing — "Link a billing account" → pick project → pick billing account.

### OAuth consent screen (for Gmail connector only)

If you enable the Gmail connector during the interview, you'll need to:

1. Open **https://console.cloud.google.com/apis/credentials/consent**
2. Select user type (Internal for Workspace, External otherwise)
3. Fill in app name, support email, developer contact
4. Add scopes: `https://www.googleapis.com/auth/gmail.readonly`
5. (For External + not verified) add your own email as a Test User

The bootstrap will pause at the Gmail interview with a direct link to this page.

### OAuth 2.0 Client ID (Gmail connector only)

After the consent screen is set up:

1. **https://console.cloud.google.com/apis/credentials** → Create Credentials → OAuth client ID
2. Application type: **Desktop app**
3. Download the JSON or copy the client ID + secret

The bootstrap will ask for these values during the Gmail interview.

---

## Required for data sources

### Google Drive folder IDs

You get them from the folder URL:

```
https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                       this is the folder ID
```

The installer will ask for a comma-separated list during the Drive interview.

**Heads-up:** After the bootstrap finishes you must **share each folder with the service account's email** (the installer will print it). The SA cannot read anything in Drive until you do this.

### Gmail mailbox access

If Gmail is a personal account, only the account owner can grant access. If it's a Workspace mailbox, the Workspace admin can grant on behalf of users.

---

## Permissions your Google account needs

To run Phase 3 end-to-end, the signed-in user must be able to:

| Permission | Used for |
|---|---|
| `resourcemanager.projects.create` | Creating a new GCP project (only if you picked "new project"). If using an existing project, you need `editor` or `owner` on it. |
| `billing.resourceAssociations.create` | Linking billing to the project |
| `serviceusage.services.enable` | Enabling APIs |
| `iam.serviceAccounts.create` + `serviceAccountKeyAdmin` | Creating the pipeline's service account + key |
| `storage.admin` | Creating GCS buckets |
| `discoveryengine.admin` | Creating the data store + engine |
| `secretmanager.admin` | Creating Secret Manager secrets |
| `run.admin` + `iam.serviceAccountUser` | Deploying Cloud Run jobs |
| `cloudscheduler.admin` | Creating Scheduler entries |

**The easiest setup:** sign in as an account with the `Owner` role on the target project. Phase 3 was designed with single-operator deployments in mind.

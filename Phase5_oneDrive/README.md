# Phase 5 — OneDrive → GCS → Vertex AI Search

Syncs files from a Microsoft OneDrive folder to a Google Cloud Storage bucket,
then triggers a Vertex AI Search re-import.  Supports both manual runs and
Windows Task Scheduler–based scheduled syncs.

---

## ⚠️ SCALE-TODO — Auth must be upgraded before production

**Current auth: MSAL delegated device-code flow with a local token cache.**

This works for a pilot but will go stale:
- Microsoft refresh tokens expire after **90 days of inactivity** by default
- Azure AD policy can enforce shorter rotation
- When the token expires, the scheduled job halts silently

**What to switch to:** Azure App Registration + `client_credentials` grant  
(no user session, no expiry, proper for automation)

Full instructions are in the `# SCALE-TODO` block at the top of `onedrive_sync.py`.

---

## Files

| File | Purpose |
|------|---------|
| `bootstrap_onedrive.py` | One-time setup check — run this first |
| `onedrive_sync.py` | Main sync script (manual + scheduled) |
| `schedule_setup.py` | Registers / removes Windows Task Scheduler job |
| `secrets/.env.template` | Copy to `secrets/.env` and fill in values |
| `secrets/token_cache.json` | Written at first auth (gitignored) |
| `secrets/delta_state.json` | Tracks OneDrive delta link for incremental sync |

---

## Setup

### 1. Azure App Registration

1. Go to [portal.azure.com](https://portal.azure.com) → Azure Active Directory → App registrations → New registration
2. Name it (e.g. `harrispecpe-onedrive-sync`), single-tenant
3. Under **Authentication** → Add platform → Mobile/Desktop → set redirect URI to `https://login.microsoftonline.com/common/oauth2/nativeclient`
4. Under **API permissions** → Add `Files.Read.All` (delegated) → Grant admin consent
5. Copy **Application (client) ID** and **Directory (tenant) ID** to `secrets/.env`

### 2. Get the OneDrive Folder ID

Option A — Graph Explorer:
```
GET https://graph.microsoft.com/v1.0/me/drive/root/children
```
Find your target folder in the response and copy its `id`.

Option B — from the OneDrive web URL:
Open the folder in OneDrive web, copy the `id=` parameter from the URL.

### 3. Configure secrets/.env
```
cp secrets/.env.template secrets/.env
# Edit secrets/.env with your values
```

### 4. Install dependencies
```
pip install -r requirements.txt
```

### 5. Bootstrap check
```
python bootstrap_onedrive.py
```
This will:
- Verify all env vars are set
- Trigger the one-time device-code sign-in (if no cached token)
- Confirm OneDrive folder is accessible and list files
- Confirm GCS bucket is accessible

---

## Running a manual sync

```powershell
# Incremental (only changed files since last run)
python onedrive_sync.py

# Full re-sync
python onedrive_sync.py --force

# Dry run (no writes, just shows what would happen)
python onedrive_sync.py --dry-run
```

---

## Scheduled sync

### Option A — Task Scheduler (recommended for Windows)

```powershell
# Run as Administrator
python schedule_setup.py --install --interval 30   # every 30 minutes
python schedule_setup.py --status                  # check status
python schedule_setup.py --remove                  # unregister
```

**Important:** Run `bootstrap_onedrive.py` once interactively before starting
the scheduled task to populate the token cache.

### Option B — Keep the window open (loop mode)

```powershell
python onedrive_sync.py --schedule 30
```

---

## How it works

```
OneDrive folder
     │  Microsoft Graph API (MSAL device-code auth)
     ▼
Local memory (bytes, never written to disk)
     │  google-cloud-storage upload
     ▼
gs://<bucket>/onedrive-mirror/
     │  Vertex AI Search import (REST v1alpha)
     ▼
Vertex AI Search data store (INCREMENTAL reconciliation)
```

Delta sync: after the first full listing, OneDrive's delta API is used so
only changed/new files are downloaded on subsequent runs.  The delta link
is persisted to `secrets/delta_state.json`.

---

## Phase isolation

Phase 3 scripts are not modified.  The shared `scripts/_env.py` helper is
reused via the same env-file discovery order (`$VERTEX_ENV_FILE` →
`Phase5_OneDrive/secrets/.env` → `cwd/.env`).

---

## .gitignore additions needed

```
Phase5_OneDrive/secrets/.env
Phase5_OneDrive/secrets/token_cache.json
Phase5_OneDrive/secrets/delta_state.json
```

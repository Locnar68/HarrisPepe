# Clean Install — Copy-Paste Guide

Three blocks. Run them in order. Nothing to edit in any file.

---

## Block 1 — Clean up everything from the old install

Open a fresh PowerShell window and paste this whole block:

```powershell
cd D:\LAB\vertex-ai-search

# Kill any lingering Python process from the stuck interview
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

# Remove the old Phase3_Bootstrap folder AND any backup folders
Remove-Item -Recurse -Force .\Phase3_Bootstrap             -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\Phase3_Bootstrap.pre-rc2.bak -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\Phase3_Bootstrap.rc2.bak     -ErrorAction SilentlyContinue

# Remove any old zip copies
Remove-Item .\Phase3_Bootstrap*.zip -Force -ErrorAction SilentlyContinue
Remove-Item .\islandadvantage.yaml  -Force -ErrorAction SilentlyContinue

Write-Host "`nCleanup complete." -ForegroundColor Green
ls
```

You should see your original Phase 1/2 folders (`bootstrap/`, `cloud_run/`, `config/`, `connectors/`, `core/`, `documents/`, `ingestion/`, `metadata/`, `scripts/`, `vertex/`) and nothing Phase3-related.

**No GCP cleanup needed** — your previous attempts all stopped during the interview, before any GCP resources were created. Nothing to tear down in the cloud.

---

## Block 2 — Install the fresh rc3 bundle + config

Download these two files into `C:\Users\<you>\Downloads\`:

- **`Phase3_Bootstrap_rc3.zip`**
- **`islandadvantage.yaml`**

Then run:

```powershell
cd D:\LAB\vertex-ai-search

# Unzip rc3 into place
Expand-Archive $HOME\Downloads\Phase3_Bootstrap_rc3.zip -DestinationPath . -Force

# Drop the pre-filled config into the bootstrap folder
Copy-Item $HOME\Downloads\islandadvantage.yaml .\Phase3_Bootstrap\ -Force

# Verify it's there
ls .\Phase3_Bootstrap\islandadvantage.yaml
```

You should see the YAML file listed.

---

## Block 3 — Run it

```powershell
cd D:\LAB\vertex-ai-search\Phase3_Bootstrap
.\bootstrap.ps1 -SkipPrereqs -ConfigFile islandadvantage.yaml
```

**What will happen:**

1. Venv creation + pip install (~60 sec)
2. Banner prints
3. Step 1 — skipped (the flag tells it to)
4. Config loaded from `islandadvantage.yaml` — **interview skipped entirely**
5. Step 3 — `gcloud auth login` opens a browser. Sign in as `michael.pepe@gmail.com`.
6. Step 4 — creates project `island-advantage-realty-rag-14`
7. Step 5 — links your billing account
8. Step 6 — enables 14 APIs (~60 sec)
9. Step 7 — creates the service account + grants 7 roles + writes `secrets\service-account.json`
10. Step 8 — creates GCS buckets
11. Step 9 — creates Secret Manager placeholders
12. Step 10 — creates the Vertex AI Search data store (this is the big one; 60-180 sec)
13. Step 11 — creates the search engine
14. Step 12 — deploys the Gmail Cloud Run sync job + Scheduler
15. Step 13 — writes `secrets\.env` and `logs\last-bootstrap-report.md`
16. Prints the "Next actions" panel — **copy this, you need it for the OAuth step below**

Expected total wall-clock: **~8 minutes**.

---

## What you do AFTER the bootstrap finishes (OAuth for Gmail)

The final panel will print clickable URLs with your project ID already filled in. Follow them in order:

### 1. Configure OAuth consent screen

Open the URL from the final panel (will look like):
```
https://console.cloud.google.com/apis/credentials/consent?project=island-advantage-realty-rag-14
```

Fill out the form:

- **User type:** External (you're on personal Gmail)
- **App name:** `Island Advantage Realty RAG`
- **User support email:** `michael.pepe@gmail.com`
- **Developer contact:** `michael.pepe@gmail.com`
- Click **Save and Continue**
- **Scopes:** click "Add or Remove Scopes", check `https://www.googleapis.com/auth/gmail.readonly`, click **Update**, then **Save and Continue**
- **Test users:** click "Add Users", add `michael.pepe@gmail.com`, click **Save and Continue**
- Click **Back to Dashboard**

### 2. Create the OAuth Client ID

Open the second URL from the final panel:
```
https://console.cloud.google.com/apis/credentials?project=island-advantage-realty-rag-14
```

- Click **Create Credentials** → **OAuth client ID**
- **Application type:** Desktop app
- **Name:** `Phase 3 Gmail Sync`
- Click **Create**
- In the dialog that appears, click **Download JSON**
- Save the downloaded file to this exact path:
  ```
  D:\LAB\vertex-ai-search\Phase3_Bootstrap\secrets\gmail-oauth-client.json
  ```

### 3. Run the authorize helper

```powershell
cd D:\LAB\vertex-ai-search\Phase3_Bootstrap
.\.venv\Scripts\python.exe -m installer.connectors.gmail authorize
```

(This step is scaffolded in rc3 — it'll print instructions for the next manual step. Paste whatever it says and I'll wire up the real OAuth exchange.)

---

## If anything goes sideways

The log file captures everything:

```powershell
cd D:\LAB\vertex-ai-search\Phase3_Bootstrap\logs
Get-Content (Get-ChildItem bootstrap-*.log | Sort-Object LastWriteTime -Desc | Select-Object -First 1) | Select-Object -Last 50
```

Paste the last 50 lines back to me and I'll patch whatever broke.

---

## Summary of what the YAML contains (FYI — you don't need to edit it)

| Field | Value |
|---|---|
| Legal name | Island Advantage Realty |
| Domain | islandadvantage.com |
| Contact | Michael Pepe `<michael.pepe@gmail.com>`, 631.351.6000 |
| GCP project | `island-advantage-realty-rag-14` (will be created) |
| Billing account | `01B8C4-8D58F5-A32204` |
| Region | us-east1 |
| SA email | `island-advantage-realty-rag-sa@island-advantage-realty-rag-14.iam.gserviceaccount.com` |
| Raw bucket | `island-advantage-realty-rag-raw` |
| Processed bucket | `island-advantage-realty-rag-processed` |
| Data store | `island-advantage-realty-ds-v1` (Enterprise, Layout Parser ON) |
| Engine | `island-advantage-realty-engine-v1` |
| Gmail | ENABLED — mailbox `michael.pepe@gmail.com`, last 90 days, every 6 hours |
| Drive | DISABLED (add later by editing config/config.yaml) |

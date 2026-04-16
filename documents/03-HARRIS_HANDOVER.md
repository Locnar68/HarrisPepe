# 03 — Harris Handover / Operational Runbook

Everything needed to go from empty GCP project to "Michael can ask questions."

## 0. Prerequisites

- Windows machine with PowerShell 7+
- Python 3.10+
- Google Cloud SDK (`gcloud`)
- A GCP project with billing enabled
- Google Drive folder (or local directory) with the required structure

## 1. First-time setup

```powershell
cd D:\LAB\vertex-ai-search
.\install.ps1
```

That runs:
- Prereq check
- venv + pip install
- Interactive prompts → writes `config/config.yaml` and `.env`
- Calls `scripts/bootstrap.py` (enables APIs, creates SA + key, bucket, data store, engine)
- Prints the SA email you must share Drive folders with

## 2. Per-connector setup

### Google Drive (personal Gmail or Workspace)
1. Get the folder ID from the URL: `https://drive.google.com/drive/folders/<ID>`
2. Put it in `config.yaml → connectors.drive.root_folder_id`
3. **Share the folder with the SA email as Viewer.** This is the critical step.

### Local files
1. Put the absolute path in `config.yaml → connectors.local_files.path`
2. Make sure the files follow the `Properties/<prop>/<category>/...` layout.

### Gmail / OneDrive / CSV
Stubbed. See `04-CONNECTOR_GUIDE.md` for implementation contracts.

## 3. Daily driver commands

```powershell
.\.venv\Scripts\Activate.ps1

python scripts\doctor.py            # are we healthy?
python scripts\sync.py --dry-run    # what would sync?
python scripts\sync.py              # pull data into GCS
python scripts\index.py --discover  # see what properties / unknown folders exist
python scripts\index.py             # extract metadata + import to Vertex
python scripts\query.py "..."       # ask questions
```

## 4. Going hands-off — Cloud Run + Scheduler

```powershell
$PROJECT = (Get-Content .env | Select-String "GOOGLE_CLOUD_PROJECT=(.+)").Matches.Groups[1].Value
$SA_EMAIL = "madison-sync-sa@$PROJECT.iam.gserviceaccount.com"

# Deploy
gcloud run deploy smb-sync `
  --source . `
  --region us-central1 `
  --no-allow-unauthenticated `
  --service-account $SA_EMAIL `
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT" `
  --timeout 1800 --memory 1Gi --cpu 2

$RUN_URL = gcloud run services describe smb-sync --region us-central1 --format="value(status.url)"

# Schedule — every hour at :00
gcloud scheduler jobs create http smb-sync-hourly `
  --location us-central1 `
  --schedule "0 * * * *" `
  --uri "$RUN_URL/run" `
  --http-method POST `
  --oidc-service-account-email $SA_EMAIL `
  --attempt-deadline 1800s
```

Cloud Run reads config from the image. To change config without rebuilding: edit `config.yaml`, then re-deploy with `--source .`

## 5. Hard rules

1. **Never rename a Data Store ID.** There is no rename API. Create `...-v2` and re-index.
2. **Never check `service-account.json` into git.** `.gitignore` already covers it; don't fight it.
3. **Don't grant the SA project-wide `Owner`.** `discoveryengine.editor` + `storage.objectAdmin` is enough.
4. **Use `index --full` sparingly.** It deletes orphans — great for cleanup, dangerous after a short sync.
5. **Personal Gmail requires folder-sharing with the SA.** The native Vertex Drive connector is Workspace-only.

## 6. Sign-off checklist for PR

- [ ] `.\install.ps1` completes without prompts erroring
- [ ] `python scripts\doctor.py` all green
- [ ] `python scripts\sync.py --dry-run` shows expected files
- [ ] `python scripts\index.py` reports `failure: 0`
- [ ] A real Michael question answered via `scripts\query.py`
- [ ] (optional) Cloud Run deployed and 2 consecutive hourly runs visible in logs

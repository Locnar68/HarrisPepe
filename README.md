# HarrisPepe — AI Document Search Platform

**Zero-configuration RAG system for small businesses.** Automated setup, deployment, and sync for Google Drive, OneDrive, and Gmail powered by Vertex AI Search + Gemini.

**Current release: Phase 5** — OneDrive connector live. Full pipeline: OneDrive → GCS → Vertex AI Search → Web UI.

---

## Phase Overview

| Phase | Status | What it does |
|-------|--------|--------------|
| **Phase 3** | ✅ Complete | Core bootstrap — GCP setup, Vertex AI Search, GCS, web UI, Google Drive sync |
| **Phase 4** | 🔧 In progress | Gemini conversational front-end, job intelligence (Madison Ave) |
| **Phase 5** | ✅ Complete | OneDrive → GCS → Vertex sync with scheduled polling |

---

## Deployment Paths

| | Generic Company | Madison Ave Construction |
|---|---|---|
| **Use case** | Any small business needing document search | Restoration & renovation job intelligence |
| **Source** | Google Drive | OneDrive (Doorloop folder) |
| **Bootstrap** | `cd Phase3_Bootstrap && .\bootstrap.ps1` | `cd Phase5_oneDrive && python bootstrap_onedrive.py` |
| **UI launched** | `http://localhost:5000` | `http://localhost:5000` |
| **Sync schedule** | Cloud Scheduler (daily) | Windows Task Scheduler (every 30 min) |
| **Extra env vars** | None | Azure Client ID/Tenant ID, OneDrive folder path |

---

## 🚀 Quick Start — Phase 3 (Google Drive)

### Prerequisites

- **Git**: https://git-scm.com/downloads
- **Python 3.10+**: https://www.python.org/downloads/
- **gcloud CLI**: https://cloud.google.com/sdk/docs/install
- **GCP billing account**: https://console.cloud.google.com/billing

### One-Command Deploy

```powershell
git clone https://github.com/Locnar68/HarrisPepe.git
cd HarrisPepe
pip install -r requirements.txt
cd Phase3_Bootstrap
.\bootstrap.ps1
```

The bootstrap interviews you for company name, Drive folder ID, and sync schedule, then automatically creates all GCP resources and launches the web UI at `http://localhost:5000`.

---

## 🚀 Quick Start — Phase 5 (OneDrive)

### Prerequisites

- Python 3.10+
- gcloud CLI authenticated: `gcloud auth application-default login`
- Azure App Registration (see setup below)

### Deploy

```powershell
git clone https://github.com/Locnar68/HarrisPepe.git
cd HarrisPepe
cd Phase5_oneDrive
pip install -r requirements.txt
python bootstrap_onedrive.py
```

The bootstrap **interviews you** for all required values and saves them to `secrets/.env` automatically. No manual file editing needed.

### Azure App Registration (one-time, ~10 minutes)

1. Go to [portal.azure.com](https://portal.azure.com) → **App registrations** → **New registration**
2. Name it (e.g. `harrispecpe-onedrive-sync`), Single tenant, click **Register**
3. **Authentication** → **Add platform** → **Mobile and desktop** → check `https://login.microsoftonline.com/common/oauth2/nativeclient`
4. Enable **Allow public client flows** → Yes → Save
5. **API permissions** → Add → Microsoft Graph → Delegated → `Files.Read` → Add
6. Copy **Application (client) ID** and **Directory (tenant) ID** — bootstrap will ask for these

### Bootstrap interview values

| Question | Where to find it |
|----------|------------------|
| Azure App Client ID | portal.azure.com → App registrations → your app → Overview |
| Azure Tenant ID | portal.azure.com → App registrations → your app → Overview |
| OneDrive Folder Path | Open folder in OneDrive web — path after `/Documents/` e.g. `Doorloop` |
| GCP Project ID | console.cloud.google.com |
| GCS Bucket Name | The bucket that will mirror OneDrive files |
| Vertex Location | `global` (default) |
| Vertex Datastore ID | console.cloud.google.com → AI Applications → Data Stores |

### Sync schedule setup (after bootstrap passes)

```powershell
# Run as Administrator
python schedule_setup.py --install --interval 30
```

This registers a Windows Task Scheduler job that syncs every 30 minutes.

> ⚠️ **SCALE-TODO**: The current auth uses a device-code OAuth token that expires after ~90 days. Before production, switch to Azure App Registration + `client_credentials` grant (no expiry). Instructions are in the `SCALE-TODO` block at the top of `onedrive_sync.py`.

> ⚠️ **Machine dependency**: Windows Task Scheduler only runs when the machine is on. For production, migrate to Cloud Run Jobs on GCP (serverless, no machine needed). This is on the Phase 5 roadmap.

### Run the web UI

```powershell
cd ..
python scripts\simple_web.py
```

Open `http://localhost:5000`

---

## 🏗️ Architecture

### Phase 3 (Google Drive)

```
Google Drive Folder
        │  Cloud Run sync job (daily)
        ▼
GCS Raw Bucket → Vertex AI Search → Web UI
```

### Phase 5 (OneDrive)

```
OneDrive (Doorloop/)
        │  onedrive_sync.py (every 30 min via Task Scheduler)
        ▼
GCS Bucket (onedrive-mirror/)
        │  JSONL manifest import (searchable docs only)
        ▼
Vertex AI Search Datastore
        │
        ▼
Web UI (Flask) → http://localhost:5000
```

**What gets indexed:** PDF, DOCX, DOC, XLSX, XLS, CSV, TXT, PPTX
**What gets skipped:** JPG, PNG, and all other image formats (stored in GCS but not indexed)

---

## 📁 Folder Structure

```
HarrisPepe/
├── Phase3_Bootstrap/          # Google Drive bootstrap framework
│   ├── bootstrap.ps1          # Main entry point
│   ├── installer/             # GCP resource creation
│   ├── secrets/               # .env + service-account.json (gitignored)
│   └── scripts/               # sync, diagnose, manual_sync
│
├── Phase5_oneDrive/           # OneDrive connector
│   ├── bootstrap_onedrive.py  # One-time setup + verification interview
│   ├── onedrive_sync.py       # Manual + scheduled sync
│   ├── schedule_setup.py      # Windows Task Scheduler registration
│   ├── requirements.txt       # msal, google-cloud-storage, requests
│   └── Secrets/               # .env (gitignored), token_cache.json
│
├── deploy_test/               # Local deployment test
│   ├── deploy_local.ps1       # Full test script with flags
│   └── secrets/.env           # Pre-filled test config (gitignored)
│
├── scripts/
│   └── simple_web.py          # Web UI (works with Phase 3 + Phase 5)
│
├── requirements.txt
└── README.md
```

---

## 💡 Using the Web UI

The web UI works with both Phase 3 (Drive) and Phase 5 (OneDrive) datastores.

```powershell
# Point at Phase 5 config
$env:VERTEX_ENV_FILE = "D:\LAB\vertex-ai-search\deploy_test\secrets\.env"
python scripts\simple_web.py
```

Or use the deploy_test script:
```powershell
cd deploy_test
.\deploy_local.ps1 -SkipSync    # bootstrap + web UI only
.\deploy_local.ps1 -DryRun      # dry run sync + web UI
.\deploy_local.ps1              # full sync + web UI
```

---

## 💰 GCP Pricing Estimates

| Service | Cost |
|---------|------|
| Vertex AI Search queries | ~$2.50 per 1,000 queries |
| Cloud Storage | ~$0.02/GB/month |
| Cloud Run Jobs (Phase 3) | Negligible for daily runs |
| **Light usage (few hundred queries/month)** | **$5–15/month** |
| **Heavy usage (thousands of queries/month)** | **$25–75/month** |

New GCP accounts get **$300 free credit** which covers several months of testing.

---

## 🔐 Security

**Never committed to git:**
- `Phase3_Bootstrap/secrets/.env`
- `Phase3_Bootstrap/secrets/service-account.json`
- `Phase5_oneDrive/Secrets/.env`
- `Phase5_oneDrive/Secrets/token_cache.json`
- `Phase5_oneDrive/Secrets/delta_state.json`
- `deploy_test/secrets/.env`

---

## 🐛 Troubleshooting

```powershell
python scripts/diagnose.py
```

| Symptom | Fix |
|---------|-----|
| Uploads fail with 403 | `python scripts/ensure_gcs_buckets.py` |
| UI says OFFLINE | `python scripts/test_rag.py` |
| OneDrive 401 errors mid-sync | Run `python bootstrap_onedrive.py` to re-auth |
| OneDrive 429 rate limit | Script auto-retries with backoff |
| Vertex import 0 successes | Check manifest format — IDs must match `[a-zA-Z0-9-_]*` |
| Token expired (90 days) | Re-run `bootstrap_onedrive.py` or switch to client_credentials |

---

## 📚 Phase Roadmap

- **Phase 3** ✅ Google Drive → GCS → Vertex → Web UI
- **Phase 4** 🔧 Gemini conversational front-end + job intelligence
- **Phase 5** ✅ OneDrive → GCS → Vertex sync
- **Phase 5 (next)** 🔲 Migrate sync to Cloud Run Jobs (remove machine dependency)
- **Phase 5 (next)** 🔲 Switch auth to client_credentials (remove 90-day token expiry)
- **Phase 5 (next)** 🔲 Consolidate Phase 3 + Phase 5 bootstrap into single interview

---

## 🤝 Contributing

Handover project for Harris. Bootstrap framework is production-ready.

For issues: check troubleshooting above, review `Phase3_Bootstrap/logs/`, or contact the team.

**Built with ❤️ for seamless document search**

---

## Deployment Paths

| | Generic Company | Madison Ave Construction |
|---|---|---|
| **Use case** | Any small business needing document search | Restoration & renovation job intelligence |
| **Phase** | Phase 3 | Phase 4 |
| **Bootstrap** | `cd Phase3_Bootstrap && .\bootstrap.ps1` | Same bootstrap, then add Phase 4 env vars |
| **UI launched** | `http://localhost:5000` | `http://localhost:5000/bob` |
| **Search mode** | Vertex AI summary | Vertex retrieval + Gemini synthesis |
| **Conversation memory** | None | Multi-turn, job-context aware |
| **Document download** | View link only | Download button per source |
| **Quick questions** | Generic | Permits, loans, appraisals, owners, lenders |
| **Extra env vars** | None | `PHASE4_ENABLED=true`, `GEMINI_API_KEY`, `GDRIVE_FOLDER_IDS` |
| **Extra deps** | See requirements.txt | `google-generativeai`, `google-api-python-client`, `pdfplumber` |

### Phase 4 Setup (Madison Ave Construction only)

After running the standard bootstrap, add these to your `.env` file:

```bash
PHASE4_ENABLED=true
GEMINI_API_KEY=your-gemini-api-key-from-aistudio.google.com
GDRIVE_FOLDER_IDS=your-drive-folder-id
```

Then restart:
```powershell
cd scripts
python simple_web.py
# Browser opens automatically at http://localhost:5000/bob
```

---

## 🚀 Quick Start (10 Minutes)

### Prerequisites

Install these first (skip any you already have):
- **Git**: https://git-scm.com/downloads
- **Python 3.10+**: https://www.python.org/downloads/
- **gcloud CLI**: https://cloud.google.com/sdk/docs/install
- **GCP billing account**: https://console.cloud.google.com/billing

### One-Command Deploy

```powershell
# Clone the repo
cd D:\LAB  # or wherever you want
git clone https://github.com/Locnar68/HarrisPepe.git
cd HarrisPepe

# Install dependencies
pip install -r requirements.txt

# Run the automated bootstrap
cd Phase3_Bootstrap
.\bootstrap.ps1
```

### What Happens Next

The bootstrap will **interview you** for:
- Company name
- Google Drive folder ID  
- Sync schedule (daily at 8 AM recommended)

Then it **automatically**:
1. ✅ Creates GCP project with billing
2. ✅ Enables 14+ required APIs
3. ✅ Creates service account with proper IAM roles
4. ✅ Sets up GCS buckets (raw + processed)
5. ✅ Creates Vertex AI Search data store (Enterprise tier)
6. ✅ Creates search engine with Gemini LLM integration
7. ✅ Deploys Cloud Run sync job
8. ✅ Configures Cloud Scheduler for automated syncs
9. ✅ Triggers initial Drive sync
10. ✅ **Launches web UI at http://localhost:5000**

**Total time:** 8-10 minutes from start to finish! 🎉

---

## 📁 Share Your Drive Folder

After bootstrap completes, **share your Google Drive folder** with the service account:

**Option 1 (Easiest):**
1. Open your folder: https://drive.google.com/drive/folders/YOUR_FOLDER_ID
2. Click **Share**
3. Change to **"Anyone with the link"**
4. Set permission to **Viewer**
5. Click **Done**

**Option 2 (More secure):**
1. Share directly with the service account email (shown in completion banner)
2. Set role to **Viewer**

**Documents will be indexed in 2-5 minutes!**

---

## 💡 Using the Web UI

The web UI auto-launches at `http://localhost:5000` after bootstrap.

**Features:**
- 🔍 Natural language search across all your documents
- 💬 AI-powered answers with source citations
- 📊 Real-time indexing status (shows document count)
- 🔄 Auto-refresh every 30 seconds
- 📱 Mobile-friendly responsive design

**To restart the web UI:**
```powershell
cd scripts
python simple_web.py
```

Access from other devices on your network at `http://YOUR_IP:5000`

---

## 🏗️ Architecture

```
Google Drive Folder
        │
        │ (Cloud Run sync job - runs daily)
        ▼
GCS Raw Bucket ────────┐
                       │
        ┌──────────────┘
        │ (Cloud Run connector processing)
        ▼
GCS Processed Bucket
        │
        │ (Vertex AI Search automatic indexing)
        ▼
Vertex AI Search Data Store (Enterprise + Layout Parser)
        │
        │ (Search Engine with Gemini LLM)
        ▼
Web UI (Flask) ──────> Natural Language Answers + Citations
```

**Key Components:**
- **Cloud Run Jobs**: Serverless sync workers (no servers to manage!)
- **Cloud Scheduler**: Automated daily sync at 8 AM (configurable)
- **Vertex AI Search Enterprise**: Advanced document understanding + OCR
- **Gemini Pro**: Generates natural language answers
- **Layout Parser**: Extracts structured data from PDFs

---

## 📂 Folder Structure

```
HarrisPepe/
├── Phase3_Bootstrap/               # 🆕 Automated bootstrap framework
│   ├── bootstrap.ps1              # Main entry point - runs everything
│   ├── installer/                 # Python installer package
│   │   ├── main.py               # Orchestrator (12 steps)
│   │   ├── interview/            # Interactive prompts
│   │   ├── gcp/                  # GCP resource creation
│   │   ├── connectors/           # Cloud Run job deployment
│   │   └── banner.py             # Completion instructions
│   ├── config/                   # Generated config.yaml
│   ├── secrets/                  # .env + service-account.json
│   ├── state/                    # Resume capability
│   └── logs/                     # Bootstrap execution logs
│
├── scripts/                       # Runtime scripts
│   └── simple_web.py             # 🆕 Generic web UI (auto-launched)
│
├── requirements.txt               # 🆕 Python dependencies
├── README.md                      # This file
└── .gitignore                     # Protects secrets
```

---

## 🔧 Configuration

All configuration is **auto-generated** during bootstrap and stored in:
- `Phase3_Bootstrap/secrets/.env` - Environment variables
- `Phase3_Bootstrap/config/config.yaml` - Full config (future Phase 4)
- `Phase3_Bootstrap/secrets/service-account.json` - GCP credentials

**These files are gitignored and never committed!**

### Key Settings (in .env)

```bash
COMPANY_NAME="your-company"
GCP_PROJECT_ID="your-company-rag-XX"
GCP_REGION="us-east1"
VERTEX_DATA_STORE_ID="your-company-ds-v1"
VERTEX_ENGINE_ID="your-company-engine-v1"
VERTEX_TIER="ENTERPRISE"
GDRIVE_ENABLED="true"
GDRIVE_FOLDER_IDS="YOUR_FOLDER_ID"
GDRIVE_SYNC_SCHEDULE="0 8 * * *"  # Daily at 8 AM
```

---

## 🔄 Managing Syncs

### Trigger Manual Sync

```powershell
gcloud run jobs execute YOUR_COMPANY-gdrive-sync --region us-east1 --wait
```

### View Sync Logs

```powershell
gcloud run jobs executions list --job YOUR_COMPANY-gdrive-sync --region us-east1 --limit 5
```

### Change Sync Schedule

Edit the cron expression in `.env`:
```bash
GDRIVE_SYNC_SCHEDULE="0 */6 * * *"  # Every 6 hours
```

Then update the scheduler:
```powershell
gcloud scheduler jobs update http YOUR_COMPANY-gdrive-sched \
  --location us-east1 \
  --schedule "0 */6 * * *"
```

---

## 🐛 Troubleshooting

### Cloud Run Job Not Created?

Run the fix script:
```powershell
cd Phase3_Bootstrap
.\fix-bootstrap.ps1
```

This recreates the Cloud Run job with proper env vars and triggers initial sync.

### No Documents Showing?

Check indexing status:
```powershell
# Open web UI - it shows live document count
cd scripts
python simple_web.py

# Or check manually via API
$token = gcloud auth print-access-token
$headers = @{"Authorization" = "Bearer $token"}
$uri = "https://discoveryengine.googleapis.com/v1/projects/YOUR_PROJECT_NUMBER/locations/global/collections/default_collection/dataStores/YOUR_DATASTORE_ID/branches/default_branch/documents"
Invoke-RestMethod -Uri $uri -Headers $headers
```

### Sync Job Failing?

Most common issues:
1. **Drive folder not shared** - Share with service account email (Viewer role)
2. **Billing not enabled** - Check https://console.cloud.google.com/billing
3. **APIs not enabled** - Bootstrap should have enabled them, but verify:
   ```powershell
   gcloud services list --enabled --project YOUR_PROJECT_ID
   ```

### Resume Failed Bootstrap

If bootstrap fails mid-way:
```powershell
cd Phase3_Bootstrap
.\bootstrap.ps1 -Resume
```

Bootstrap saves state after each step, so resume picks up where it left off.

---

## 🔐 Security Best Practices

**Never commit these files:**
- ✅ `.env` - Contains project IDs and config
- ✅ `service-account.json` - GCP credentials
- ✅ `config.yaml` - May contain sensitive folder IDs
- ✅ `*.log` - May contain debugging info

**These are already in .gitignore!**

**Service Account Permissions:**
The bootstrap creates a service account with minimal required permissions:
- `roles/storage.admin` - GCS bucket access
- `roles/discoveryengine.admin` - Vertex AI Search
- `roles/secretmanager.secretAccessor` - Cloud Run env vars
- `roles/aiplatform.user` - Gemini API
- `roles/run.invoker` - Trigger Cloud Run jobs
- `roles/logging.logWriter` - Write logs

---

## 📊 What Gets Created in GCP

The bootstrap creates these resources (all names derived from company name):

| Resource | Name Pattern | Purpose |
|----------|--------------|---------|
| Project | `{company}-rag-XX` | Isolated environment |
| Service Account | `{company}-rag-sa` | Automation identity |
| GCS Buckets | `{company}-rag-raw`<br>`{company}-rag-processed` | File storage |
| Data Store | `{company}-ds-v1` | Search index |
| Engine | `{company}-engine-v1` | Search + LLM |
| Cloud Run Job | `{company}-gdrive-sync` | Sync worker |
| Scheduler | `{company}-gdrive-sched` | Cron trigger |

**Monthly cost estimate:** $20-50 depending on document volume and query frequency.

---

## 🚢 Production Deployment Checklist

Before handing off to production:

- [ ] Replace placeholder image in Cloud Run job
  ```powershell
  gcloud run jobs update YOUR_COMPANY-gdrive-sync \
    --image gcr.io/YOUR_PROJECT/gdrive-connector:latest \
    --region us-east1
  ```
- [ ] Set up proper CI/CD pipeline for connector images
- [ ] Configure backup/disaster recovery for GCS buckets
- [ ] Set up monitoring alerts for sync job failures
- [ ] Document folder sharing process for end users
- [ ] Enable Cloud Armor if exposing web UI publicly
- [ ] Set up proper DNS/load balancer for web UI
- [ ] Configure organization policies and IAM
- [ ] Set up log exports to BigQuery for analytics

---

## 🆚 Phase 2 vs Phase 3

| Feature | Phase 2 | Phase 3 |
|---------|---------|---------|
| Setup | Manual install.ps1 + multiple scripts | ✅ Single bootstrap.ps1 |
| Sync | Manual `python scripts/sync.py` | ✅ Automated Cloud Run jobs |
| Deployment | Manual `python scripts/deploy.py` | ✅ Auto-deployed during bootstrap |
| Web UI | Complex multi-file web/ folder | ✅ Single-file generic UI |
| Resume | ❌ Start over on failure | ✅ Resume from last step |
| Config | Manual config.yaml editing | ✅ Interactive interview |
| Auto-sync | Requires deploy.py | ✅ Built-in Cloud Scheduler |

---

## 📚 Advanced Topics

### Multiple Drive Folders

Edit `.env` to add more folders:
```bash
GDRIVE_FOLDER_IDS="folder1,folder2,folder3"
```

Redeploy connector:
```powershell
cd Phase3_Bootstrap
# Re-run connector deployment step
python -m installer.connectors.gdrive configure
```

### Custom Sync Schedule

Cron syntax guide:
- `0 8 * * *` - Daily at 8 AM
- `0 */6 * * *` - Every 6 hours
- `*/30 * * * *` - Every 30 minutes
- `0 8 * * 1` - Every Monday at 8 AM

### Gmail Connector (Phase 4)

Gmail sync is stubbed out in Phase 3. Full implementation coming in Phase 4:
- OAuth2 flow for user consent
- Configurable label filters
- Email thread extraction
- Attachment handling

---

## 🤝 Contributing

This is a handover project for Harris. The bootstrap framework is production-ready for Google Drive connectors.

**Phase 4 roadmap:**
- Gmail connector (OAuth flow)
- OneDrive connector
- Multi-tenant support
- Advanced filtering/tagging
- Custom metadata schemas

---

## 📄 License

MIT License - See LICENSE file

---

## 🆘 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review logs in `Phase3_Bootstrap/logs/`
3. Run `.\fix-bootstrap.ps1` for common issues
4. Contact Harris team for Phase 4 features

**Built with ❤️ for seamless document search**

---

## 🆘 Troubleshooting

Hit a snag? Run the diagnostic first:

```powershell
python scripts/diagnose.py
```

Common fixes:
- **Uploads fail with 403** → python scripts/ensure_gcs_buckets.py (bucket name collision)
- **Cloud Run job doesn't index** → python scripts/manual_sync.py (placeholder image still in place)
- **UI says OFFLINE but data exists** → python scripts/test_rag.py (verifies backend independently)

Full guide: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
Deep gotchas: [docs/LESSONS_LEARNED.md](docs/LESSONS_LEARNED.md)

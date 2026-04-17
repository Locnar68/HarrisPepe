# Vertex AI Search - Phase 3 Bootstrap

**Zero-configuration RAG system for small businesses.** Automated setup, deployment, and sync for Google Drive + Gmail powered by Vertex AI Search Enterprise + Gemini.

**Current release: Phase 3** — Turnkey bootstrap framework with auto-deployment, Cloud Run sync jobs, and integrated web UI.

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

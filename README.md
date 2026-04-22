# HarrisPepe — AI Document Search Platform

**Multi-tenant RAG system for small businesses.** Automated setup, deployment, and sync for Google Drive, OneDrive, and Gmail powered by Vertex AI Search + Gemini.

**Current release: Phase 5** — OneDrive connector live. Full pipeline: OneDrive → GCS → Vertex AI Search → Web UI.

---

## Phase Overview

| Phase | Status | What it does |
|-------|--------|--------------|
| **Phase 3** | ✅ Complete | Core bootstrap — GCP setup, Vertex AI Search, GCS, web UI, Google Drive sync |
| **Phase 4** | 🔧 In progress | Gemini conversational front-end, job intelligence |
| **Phase 5** | ✅ Complete | OneDrive → GCS → Vertex sync with scheduled polling |

---

## Architecture — Two Deployment Paths

| | Google Drive Path | OneDrive Path |
|---|---|---|
| **Source** | Google Drive folder | OneDrive (e.g. Doorloop/) |
| **Bootstrap** | `Phase3_Bootstrap/bootstrap.ps1` | `Phase5_oneDrive/bootstrap_onedrive.py` |
| **Sync** | Cloud Run Jobs (daily) | Windows Task Scheduler (every 30 min) |
| **Config** | `config/config.yaml` | `Phase5_oneDrive/Secrets/.env` |
| **UI** | `python scripts/simple_web.py` | Same |

---

## 🚀 Quick Start — Google Drive (Phase 3)

### Prerequisites

- Python 3.10+
- [gcloud CLI](https://cloud.google.com/sdk/docs/install)
- GCP billing account

### Deploy

```powershell
git clone https://github.com/Locnar68/HarrisPepe.git
cd HarrisPepe
cd Phase3_Bootstrap
.\bootstrap.ps1
```

Bootstrap interviews you for company name, Drive folder ID, and sync schedule, then automatically creates all GCP resources and launches the web UI.

---

## 🚀 Quick Start — OneDrive (Phase 5)

### Prerequisites

- Python 3.10+
- gcloud CLI: `gcloud auth application-default login`
- Azure App Registration (see below)

### Deploy

```powershell
git clone https://github.com/Locnar68/HarrisPepe.git
cd HarrisPepe\Phase5_oneDrive
pip install -r requirements.txt
python bootstrap_onedrive.py
```

### Azure App Registration (one-time, ~10 minutes)

1. [portal.azure.com](https://portal.azure.com) → **App registrations** → **New registration**
2. Name it, Single tenant, click **Register**
3. **Authentication** → **Add platform** → **Mobile and desktop** → check `https://login.microsoftonline.com/common/oauth2/nativeclient`
4. Enable **Allow public client flows** → Yes → Save
5. **API permissions** → Add → Microsoft Graph → Delegated → `Files.Read`
6. Copy **Application (client) ID** and **Directory (tenant) ID**

---

## ⚙️ Configuration

### config/config.yaml

Central config file read by all scripts. Each deployment gets its own config. Do not hardcode client-specific values — all identity values come from this file.

Key sections:

```yaml
project:
  id: your-gcp-project-id
  location: global

gcs:
  bucket: your-bucket-name
  mirror_prefix: data          # top-level prefix in bucket
  manifest_prefix: _manifests

metadata:
  properties_folder: Properties  # folder level that contains property subfolders
                                 # set to "Doorloop" for OneDrive/Doorloop deployments
  category_folders:
    "files":  document
    "photos": image
  heuristic_classification: true
  heuristic_rules:
    - { pattern: "invoice|receipt",                    doc_type: billing }
    - { pattern: "permit|inspection|certificate",      doc_type: permit }
    - { pattern: "closing|deed|title|llc|sale",        doc_type: legal }
    - { pattern: "p&l|statement|appraisal|bank",       doc_type: finance }
    - { pattern: "lease|tenant|rent|agreement",        doc_type: lease }
    - { pattern: ".",                                  doc_type: document }
```

### Multi-Client Configs

Each client gets a named config file:

```
config/
  config.yaml          # active config (never commit client-specific values)
  config.harris.yaml   # Harris / OneDrive / Doorloop deployment
```

To switch active config:
```powershell
Copy-Item config\config.harris.yaml config\config.yaml -Force
```

---

## 🗂️ Folder Structure

```
HarrisPepe/
├── bootstrap/                     # GCP resource bootstrap helpers
├── config/
│   ├── config.yaml                # Active config (gitignored if client-specific)
│   └── config.harris.yaml         # Harris OneDrive/Doorloop deployment config
├── connectors/                    # Drive, Gmail, OneDrive, CSV connectors
├── core/
│   ├── config.py                  # Config loader (single source of truth)
│   └── clients.py                 # GCP client factory
├── ingestion/
│   ├── manifest.py                # Builds JSONL manifest for Vertex import
│   │                              # Adds title + source_uri to every doc structData
│   └── inject.py                  # ImportDocuments into Vertex data store
├── metadata/
│   ├── extractor.py               # Path → metadata classifier
│   │                              # Strict (path-based) + Heuristic (filename regex)
│   │                              # properties_folder is configurable via config.yaml
│   └── schema.py                  # Schema definitions
├── scripts/
│   ├── index.py                   # Walk GCS → build manifest → import to Vertex
│   ├── manual_sync.py             # Drive → GCS → Vertex (on-demand)
│   ├── simple_web.py              # Flask web UI
│   ├── diagnose.py                # Connectivity + config diagnostics
│   ├── check_index.py             # Verify index status
│   └── _env.py                    # Shared env discovery helper
├── Phase3_Bootstrap/              # Automated bootstrap framework
│   ├── bootstrap.ps1              # Main entry point
│   ├── installer/                 # GCP resource creation (step by step)
│   ├── secrets/                   # .env + service-account.json (gitignored)
│   └── requirements.txt
├── Phase5_oneDrive/               # OneDrive connector
│   ├── bootstrap_onedrive.py      # One-time setup + verification
│   ├── onedrive_sync.py           # Incremental sync via Graph API delta
│   ├── schedule_setup.py          # Windows Task Scheduler registration
│   └── Secrets/                   # .env + token_cache.json (gitignored)
├── phase4/                        # Gemini conversational front-end (in progress)
│   ├── job_intelligence.py        # Gemini + Vertex retrieval
│   └── phase4_routes.py           # Flask routes for Phase 4 UI
├── docs/
│   └── PHASE4_TODO.md             # Known issues and deferred items
└── README.md
```

---

## 🔍 Indexing Pipeline

### How documents get structured metadata

Every document pushed to Vertex AI Search gets these fields in `structData`:

| Field | Value | Example |
|---|---|---|
| `title` | Filename | `Invoice 20364.pdf` |
| `source_uri` | Full GCS path | `gs://bucket/onedrive-mirror/Doorloop/1 Fox Run/files/Invoice 20364.pdf` |
| `property` | Property folder name | `1 Fox Run` |
| `category` | Subfolder name | `files` |
| `doc_type` | Classified type | `billing` |
| `filename` | Filename | `Invoice 20364.pdf` |
| `updated` | Last modified time | `2026-04-21T...` |

### Classification strategy

Two strategies tried in order:

**1. Strict (path-based)** — preferred when folder structure is organized:
```
<mirror_prefix>/<properties_folder>/<property>/<category>/<filename>
e.g. onedrive-mirror/Doorloop/1 Fox Run/files/Invoice.pdf
```

**2. Heuristic (filename regex)** — fallback for flat/unorganized folders.
Rules defined in `config.yaml → metadata.heuristic_rules`.

### Run indexing

```powershell
# See what would be indexed (no changes)
python scripts/index.py --discover

# Full re-index (push all docs with updated metadata)
python scripts/index.py --full

# Incremental (add new docs only)
python scripts/index.py
```

---

## 🖥️ Web UI

```powershell
# Activate venv
.\Phase3_Bootstrap\.venv\Scripts\Activate.ps1

# Set env
$env:GOOGLE_CLOUD_PROJECT = "your-project-id"
$env:GOOGLE_APPLICATION_CREDENTIALS = "Phase3_Bootstrap\secrets\service-account.json"

# Start
python scripts/simple_web.py
```

Open `http://localhost:8080`

### Required .env variables for web UI

```bash
GOOGLE_CLOUD_PROJECT=your-project-id
GCP_PROJECT_ID=your-project-id
VERTEX_DATA_STORE_ID=your-data-store-id
VERTEX_ENGINE_ID=your-engine-id
GCS_BUCKET_RAW=your-bucket-name
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
```

---

## 🔐 Credentials & Access

### Service Account Key

Each developer needs a SA key for their machine:

```powershell
# Generate a key (project owner runs this)
gcloud iam service-accounts keys create "Phase3_Bootstrap\secrets\service-account.json" `
    --iam-account="your-sa@your-project.iam.gserviceaccount.com" `
    --project="your-project-id"
```

**Never share SA key contents in chat, email, or any text channel. Share the file via Google Drive (private share) only. Revoke and regenerate if accidentally exposed.**

### ADC Setup (required once per machine)

```powershell
gcloud auth login
gcloud auth application-default login
gcloud auth application-default set-quota-project your-project-id
```

### Required IAM roles for developer accounts

```powershell
gcloud projects add-iam-policy-binding your-project-id \
    --member="user:developer@gmail.com" \
    --role="roles/discoveryengine.viewer"

gcloud projects add-iam-policy-binding your-project-id \
    --member="user:developer@gmail.com" \
    --role="roles/storage.objectViewer"

gcloud projects add-iam-policy-binding your-project-id \
    --member="user:developer@gmail.com" \
    --role="roles/serviceusage.serviceUsageConsumer"
```

---

## 💰 GCP Pricing Estimates

| Service | Cost |
|---------|------|
| Vertex AI Search queries | ~$2.50 per 1,000 queries |
| Cloud Storage | ~$0.02/GB/month |
| Cloud Run Jobs | Negligible for daily runs |
| **Light usage** | **$5–15/month** |
| **Heavy usage** | **$25–75/month** |

---

## 🐛 Troubleshooting

```powershell
python scripts/diagnose.py
```

| Symptom | Fix |
|---------|-----|
| `Permission denied on discoveryengine` | Grant `roles/discoveryengine.viewer` to your account |
| `serviceusage.services.use` error | Grant `roles/serviceusage.serviceUsageConsumer` |
| `No .env file found` | Create `.env` at repo root with required vars |
| `No module named 'click'` | Venv not active or not built — run `python -m venv Phase3_Bootstrap\.venv && pip install -r Phase3_Bootstrap\requirements.txt` |
| `No module named 'flask'` | `pip install flask python-dotenv google-generativeai` |
| `config file not found` | `config/config.yaml` missing — copy from `config.harris.yaml` or commit it |
| Search returns 0 results | Run `python scripts/index.py --full` to re-index with latest manifest |
| Titles blank in results | Run `python scripts/index.py --full` — older imports lack `title` in structData |
| P&L PDFs return no results | Scanned image PDFs — OCR fix tracked in `docs/PHASE4_TODO.md` |
| OneDrive 401 mid-sync | Re-run `python Phase5_oneDrive/bootstrap_onedrive.py` |
| OneDrive 429 rate limit | Script auto-retries with backoff — wait and retry |
| SA key creation blocked | Free trial org policy — use `gcloud auth application-default login` instead |

---

## 📋 Known Issues (Deferred)

See `docs/PHASE4_TODO.md` for full list. Key items:

- **Scanned PDFs return 0 results** — Vertex Layout Parser cannot OCR image-based PDFs. Fix: add pdfplumber/pytesseract preprocessing in `manual_sync.py` for tabular/scanned docs.
- **Hardcoded client slugs in installer** — `Phase3_Bootstrap/installer` interview should generate client slug from company name input rather than hardcoding. Fix: update `installer/interview/business.py`.
- **OneDrive token expires in 90 days** — Switch from device-code OAuth to `client_credentials` before production.
- **Windows Task Scheduler dependency** — Migrate OneDrive sync to Cloud Run Jobs for production (no machine dependency).

---

## 📚 Phase Roadmap

- **Phase 3** ✅ Google Drive → GCS → Vertex → Web UI
- **Phase 4** 🔧 Gemini conversational front-end + job intelligence
- **Phase 5** ✅ OneDrive → GCS → Vertex sync
- **Phase 5+** 🔲 Cloud Run Jobs for OneDrive sync (remove machine dependency)
- **Phase 5+** 🔲 client_credentials auth (remove 90-day token limit)
- **Phase 5+** 🔲 Unified bootstrap for Drive + OneDrive in single interview

---

*Built for Harris. Multi-tenant document search platform.*

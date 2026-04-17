# Phase 3 — Turnkey Bootstrap Framework

**Zero-assumption, one-command installer for the Vertex AI RAG pipeline.**

This is Phase 3 of the HarrisPepe / `vertex-ai-search` project. It assumes **nothing** about the machine or account running it — no prior Python, no gcloud CLI, no GCP account, no project, no billing. It walks the operator through every step, asks for every required variable, shows signup links where services are needed, and produces a fully working Vertex AI Search + Gemini RAG stack at the end.

## Status

| Phase | What it is | Status |
|---|---|---|
| Phase 1 | Visual-first RAG — shipped | ✅ locked (`v1.0`) |
| Phase 2 | Connector breadth + custom schema | ✅ locked (`v2.0`) |
| **Phase 3** | **Turnkey bootstrap framework** | **✅ complete — ready for GitHub** |

Phase 3 does **not** replace Phase 1 or Phase 2 — it wraps them. After the bootstrap finishes, the resulting environment is identical in shape to what `install.ps1` produces at the repo root, plus the additional pieces Phase 3 adds (menu-driven connectors, OAuth setup, Secret Manager, Cloud Run sync jobs).

## The one command

**Windows (PowerShell):**

```powershell
cd D:\LAB\vertex-ai-search\Phase3_Bootstrap
.\bootstrap.ps1
```

**Linux / macOS:**

```bash
cd ~/vertex-ai-search/Phase3_Bootstrap
./bootstrap.sh
```

That's it. The script will:

1. **Detect what's missing** on the host machine (Python 3.10+, gcloud CLI, git) and offer to install each one.
2. **Sign you into Google Cloud** (or send you to the signup page if you don't have an account — `https://cloud.google.com/free`).
3. **Run a structured interview** that collects every variable the pipeline needs (company name, contact info, project ID, billing account, bucket names, data-store ID, which connectors to enable).
4. **Show you a menu of connectors** — Phase 3 ships with Gmail and Google Drive enabled. OneDrive / SharePoint / SQL / file shares are stubbed for Phase 4.
5. **Create everything in GCP** — project (if needed), APIs, service account, GCS buckets, Secret Manager entries, Vertex AI Search data store (v1alpha for Layout Parser), search engine, Cloud Run sync jobs.
6. **Print a final report** with the serving-config path, the SA email to share Drive folders with, and the OAuth consent URL for Gmail.
7. **Save a resumable checkpoint** — if something fails, re-running `bootstrap.ps1` picks up where it stopped.

## What it asks you

See [`docs/02-INTERVIEW_GUIDE.md`](docs/02-INTERVIEW_GUIDE.md) for the full list. High level:

- **Company:** legal name, display name, domain, industry
- **Primary contact:** name, email, phone
- **GCP:** existing project? (Y/N), project ID, billing account
- **Storage:** bucket names (raw / processed)
- **Vertex AI:** data-store ID, engine ID
- **Connectors:** Drive folder IDs, sync schedule

Nothing is assumed — if you don't have a GCP account, you get the signup link. If you don't have billing enabled, you get the link. Hard-won lessons from the POC are baked in.

## What it produces

After a clean run, on disk you'll have:

```
<install-location>/
├── config/
│   └── config.yaml                  # your complete Phase 3 config (gitignored)
├── secrets/
│   ├── service-account.json         # SA key (gitignored)
│   └── .env                         # env vars (gitignored)
├── state/
│   └── bootstrap.state.json         # checkpoint file (gitignored)
└── logs/
    └── bootstrap-<timestamp>.log
```

And in GCP:

- A project (new or existing) with the right APIs enabled
- A service account with minimum-viable roles
- GCS buckets (raw / processed)
- Vertex AI Search data store (ENTERPRISE tier) with Layout Parser enabled
- A search engine bound to the data store
- Cloud Run job for Drive sync
- Cloud Scheduler trigger for daily sync

## Hard rules (from POC lessons, encoded in the installer)

The installer refuses to do the wrong thing. Specifically:

1. It **only uses the REST API** for Vertex AI Search (`discoveryengine.googleapis.com`) — never `gcloud discovery-engine`, which doesn't exist.
2. It **always uses `v1alpha`** for `documentProcessingConfig` and **sets Layout Parser at data-store creation time** — this cannot be patched later.
3. It **treats 404s during operation polling as success** — the LRO record is garbage-collected after completion.
4. It **appends `-v2`, `-v3`** to data-store IDs if a conflict is detected (deleted IDs are reserved for hours).
5. It **retries 5xx errors automatically** with exponential backoff (3 retries, 2s/4s/8s delays).

## Folder structure

```
Phase3_Bootstrap/
├── bootstrap.ps1                    # Windows entry point
├── bootstrap.sh                     # Linux/Mac entry point
├── cleanup.ps1                      # Windows cleanup script (pre-commit)
├── cleanup.sh                       # Linux/Mac cleanup script (pre-commit)
├── requirements.txt                 # Python dependencies
├── .env.example                     # env-var template (safe to commit)
├── .gitignore                       # protects generated secrets/state
├── README.md                        # this file
├── installer/                       # the actual Python installer
│   ├── __main__.py                  # `python -m installer`
│   ├── main.py                      # orchestrator
│   ├── banner.py                    # welcome banner
│   ├── logger.py                    # structured logging
│   ├── state.py                     # checkpoint / resume
│   ├── validators.py                # input validation
│   ├── prereqs/                     # host-machine checks
│   ├── interview/                   # Q&A modules
│   ├── gcp/                         # GCP resource creation
│   ├── connectors/                  # Gmail, GDrive (Phase 4 adds more)
│   ├── config/                      # pydantic schema + loader
│   └── utils/                       # shell, HTTP, UI
├── docs/                            # prereq guides, signup links, runbook
├── examples/                        # filled-out sample config
└── tests/                           # unit tests
```

## Pre-commit cleanup

Before pushing to GitHub, run the cleanup script to remove caches and generated files:

**Windows:**
```powershell
.\cleanup.ps1
```

**Linux/Mac:**
```bash
./cleanup.sh
```

This removes `__pycache__`, `.pytest_cache`, `.venv`, and any generated `config/`, `secrets/`, `state/`, or `logs/` directories. The `.gitignore` protects these from accidental commits, but cleanup ensures a pristine package.

## Post-install steps

After bootstrap completes:

1. **Share Drive folder with service account** — use the SA email from the final report, grant Viewer role
2. **Manually trigger first sync** — command shown in final report, or wait for scheduler
3. **Verify** — query your Vertex AI Search engine to confirm documents are indexed

## Next steps for deployment

See [`docs/08-PHASE3_RUNBOOK.md`](docs/08-PHASE3_RUNBOOK.md) for the complete staging + release procedure.

## License

MIT. Inherits from the parent repo.

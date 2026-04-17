# Phase 3 Bootstrap — Download & Install Quick-Start

You have one deliverable:

- **Phase3_Bootstrap.zip** — 63 files, ~95 KB, the complete turnkey installer framework

Everything below takes you from "zip sitting in Downloads" to "Phase 3 running against your GCP project."

---

## 1. Unzip into the repo working directory

```powershell
# Move the zip from wherever you downloaded it to the staging location
Move-Item $HOME\Downloads\Phase3_Bootstrap.zip D:\LAB\vertex-ai-search\

# Unzip in place — creates D:\LAB\vertex-ai-search\Phase3_Bootstrap\
cd D:\LAB\vertex-ai-search
Expand-Archive .\Phase3_Bootstrap.zip -DestinationPath . -Force

# Confirm the folder arrived
ls .\Phase3_Bootstrap\
```

You should see `bootstrap.ps1`, `bootstrap.sh`, `README.md`, `requirements.txt`, `.gitignore`, `.env.example`, and the `installer/`, `docs/`, `examples/`, `tests/` subfolders.

---

## 2. Lock Phase 2 in GitHub first

Before committing Phase 3, snapshot the Phase 2 state. Pick whichever applies:

```powershell
cd D:\LAB\vertex-ai-search
git checkout main
git pull

# Option A — Phase 2 is done:
git tag -a v2.0 -m "Phase 2 — Connector breadth + custom schema"
git push origin v2.0
gh release create v2.0 --title "Phase 2" --notes "Connector breadth + custom schema"

# Option B — Phase 2 is partial and you want a rollback point:
git tag -a v2.0-partial -m "Phase 2 snapshot before Phase 3 work"
git push origin v2.0-partial
```

Full procedure is in `Phase3_Bootstrap\docs\08-PHASE3_RUNBOOK.md`.

---

## 3. Add Phase 3 to a branch

```powershell
git checkout -b phase-3

# Sanity-check: confirm .gitignore is catching secrets BEFORE the add
git check-ignore -v Phase3_Bootstrap/secrets/service-account.json
git check-ignore -v Phase3_Bootstrap/config/config.yaml
git check-ignore -v Phase3_Bootstrap/.venv
# All three should report "ignored" — if not, STOP and fix .gitignore

git add Phase3_Bootstrap
git commit -m "Phase 3: turnkey bootstrap framework"
git push -u origin phase-3
```

---

## 4. Smoke-test the installer

You don't need to run the whole bootstrap to know it's healthy. Three fast checks first:

```powershell
cd D:\LAB\vertex-ai-search\Phase3_Bootstrap

# a) PowerShell entry point parses
powershell -NoProfile -Command "Get-Command -Syntax .\bootstrap.ps1"

# b) Python side — create the venv and verify the orchestrator imports
.\bootstrap.ps1 -SkipPrereqs    # This runs through prereq checks, creates .venv,
                                # installs deps, then DROPS YOU INTO THE INTERVIEW.
                                # Hit Ctrl-C at the first business-name question
                                # to back out — no GCP mutation has happened yet.

# c) Run the unit tests in the venv
.\.venv\Scripts\Activate.ps1
python -m pytest tests/ -v
deactivate
```

Expected: 85 tests pass.

---

## 5. Do a real run (when you're ready)

```powershell
cd D:\LAB\vertex-ai-search\Phase3_Bootstrap
.\bootstrap.ps1
```

Budget ~15 minutes for the interview and ~8 minutes for GCP provisioning on a normal network. If anything fails mid-run:

```powershell
.\bootstrap.ps1 -Resume    # picks up at the last successful checkpoint
```

---

## 6. What the installer will ask you

Exhaustive list is in `Phase3_Bootstrap\docs\02-INTERVIEW_GUIDE.md`. High level:

- Business: legal name, display name (suggested from legal name), domain, industry, country
- Contact: name, email, phone (optional), role
- GCP: account exists? (signup link if no), project (pick existing or create new), billing account, region
- Service account: short name + display name (derived from business)
- Storage: raw / processed / optional archive bucket names, storage class, lifecycle
- Vertex AI: data store ID, engine ID, tier (Enterprise recommended), Layout Parser (yes)
- Connectors: Gmail + Google Drive checked by default; OneDrive / SQL / FileShare are Phase 4 stubs
- Gmail specifics: OAuth client ID + secret, mailbox, label, query, cron
- Drive specifics: mode (SA vs OAuth), drive type, folder IDs, MIME allowlist, cron
- Review: final confirmation before any GCP mutation

---

## 7. What you do by hand after the installer finishes

The final screen prints these:

1. **Share each Drive folder** with the SA email it prints (Viewer role)
2. **Complete Gmail OAuth** by running `python -m installer.connectors.gmail authorize`
3. **Run `.\bootstrap.ps1 -Verify`** to confirm everything is green
4. **Swap the Cloud Run job image** from the placeholder to the real image once CI builds it

---

## 8. Where to look when something goes wrong

- `Phase3_Bootstrap\logs\bootstrap-<timestamp>.log` — every stderr line from every gcloud/REST call
- `Phase3_Bootstrap\docs\06-TROUBLESHOOTING.md` — symptom-to-fix table covering the POC learnings
- `Phase3_Bootstrap\state\bootstrap.state.json` — edit this to force re-running a step

---

## 9. What each doc covers

| File | Purpose |
|---|---|
| `README.md` | What Phase 3 is, how it wraps Phase 1/2, one-command quickstart |
| `docs/01-PREREQUISITES.md` | Every prereq + install method + signup link per platform |
| `docs/02-INTERVIEW_GUIDE.md` | Every question with type/example/notes (pre-interview worksheet) |
| `docs/03-GCP_ACCOUNT_SETUP.md` | Step-by-step for brand-new GCP users |
| `docs/06-TROUBLESHOOTING.md` | Symptom-to-fix table |
| `docs/07-ARCHITECTURE.md` | How Phase 3 maps to the reference architecture diagram |
| `docs/08-PHASE3_RUNBOOK.md` | Phase 2 lock + branching + PR procedure (for Michael) |

---

## File inventory (what's in the zip)

63 files total:

```
Phase3_Bootstrap/
├── README.md                          (1 file)
├── bootstrap.ps1                      (1)
├── bootstrap.sh                       (1)
├── requirements.txt                   (1)
├── .env.example                       (1)
├── .gitignore                         (1)
├── installer/                         (38 Python files)
│   ├── __init__.py, __main__.py, main.py, banner.py, logger.py, state.py, validators.py
│   ├── config/         (3 files)   — Pydantic schema + YAML loader
│   ├── prereqs/        (4 files)   — Python / gcloud / git checks
│   ├── interview/      (12 files)  — all Q&A modules
│   ├── gcp/            (12 files)  — all provisioning modules
│   ├── connectors/     (4 files)   — Gmail + GDrive
│   └── utils/          (4 files)   — shell, HTTP, UI helpers
├── docs/                              (6 files)
├── examples/example_config.yaml       (1 file)
└── tests/                             (4 files, 85 tests)
```

All 50 `.py` files have been syntax-verified, all 45 modules import cleanly, and all 85 tests pass.

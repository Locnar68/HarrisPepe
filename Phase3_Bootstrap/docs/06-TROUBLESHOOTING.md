# 06 — Troubleshooting

Symptom → fix table for the most common failure modes during and after Phase 3 bootstrap. **Before digging in, always check the log file** at `<install-path>/logs/bootstrap-<timestamp>.log` — the full stderr from every gcloud/REST call is captured there.

---

## Prereq / host-machine errors

### `'python' is not recognized` (Windows)

PowerShell was opened before Python was installed and cached `$env:PATH` without it. **Close PowerShell and open a new window**, then re-run `.\bootstrap.ps1`.

### `bootstrap.ps1 cannot be loaded because running scripts is disabled`

Your system-wide execution policy blocks unsigned scripts. The installer sets the policy for the current session only, but the block happens before it runs. Launch once with an explicit bypass:

```powershell
PowerShell.exe -ExecutionPolicy Bypass -File .\bootstrap.ps1
```

### `winget is not recognized`

"App Installer" is missing from the machine. Install it from the Microsoft Store, then re-run. On older Windows Server / Windows 10 builds winget may not be available at all — in that case install Python / gcloud / git manually using the links in `docs/01-PREREQUISITES.md`.

### `gcloud: command not found` even after install

Happens on macOS and Linux when the shell profile didn't reload. Either start a new shell, or `source ~/google-cloud-sdk/path.bash.inc` in the current one.

---

## Sign-in / auth errors

### `Reauthentication required`

Your gcloud session expired. Re-run:

```powershell
gcloud auth login
gcloud auth application-default login
```

Then `.\bootstrap.ps1 -Resume`.

### `insufficient authentication scopes`

You signed in as a user who lacks one of the required roles (see `docs/01-PREREQUISITES.md`). Easiest fix: re-auth as an account with **Owner** on the project.

### `403 PERMISSION_DENIED: ... is not authorized`

Usually a missing IAM binding. The installer grants 7 roles to the service account, but the **human user** running the installer also needs enough power. If it's the user, not the SA, add yourself as Owner temporarily.

---

## Project / billing errors

### `project ID already exists`

Project IDs are globally unique across all of GCP, forever. Even if you deleted yours, the ID is reserved. Pick a new ID — the installer defaults append a random 4-digit suffix; re-run with a different one.

### `Billing account ... is not accessible`

Either the billing account is closed, or your signed-in user doesn't have the Billing Account User role on it. Open **https://console.cloud.google.com/billing** and confirm the account is Active and your identity can view it.

### `API has not been enabled` (seen mid-run)

Some APIs take a minute or two to propagate after enable. The installer waits, but on slow regions you can hit this. Fix: `.\bootstrap.ps1 -Resume` — it will skip what's done and re-try the API-dependent step.

---

## Vertex AI Search — the hard-won ones (POC lessons)

### `gcloud: command 'discovery-engine' not found`

You tried to run a gcloud command the installer doesn't use. **There is no `gcloud discovery-engine` command.** All data-store and engine work goes through the REST API (`discoveryengine.googleapis.com`). The installer handles this for you — if you see it, you're invoking gcloud outside the installer.

### `400 INVALID_ARGUMENT: unknown field documentProcessingConfig`

You're hitting the wrong API version. Layout Parser config is **v1alpha only**. The installer pins v1alpha for data-store creation; if you wrote custom scripts against v1 / v1beta, switch to v1alpha for anything that touches `documentProcessingConfig`.

### `409 ALREADY_EXISTS` when creating a data store you know is gone

Data store IDs are **reserved for several hours** after deletion. The installer auto-bumps the suffix (`-v2`, `-v3`, …) up to 5 attempts. If you want a specific ID back, wait overnight.

### 404 while polling the create operation

**This is actually success.** Google garbage-collects the LRO record after completion, and the final poll lands on an empty slot. The installer treats 404-during-poll as success (see `installer/utils/http.py::poll_operation`).

### `FailedPrecondition: extractive_content_spec requires ENTERPRISE tier`

You picked Standard tier at interview time but your downstream query code uses an Enterprise-only feature. Either upgrade the engine tier or simplify the query. To upgrade:

```bash
gcloud alpha discovery-engine engines update <engine-id> \
  --tier=ENTERPRISE ...
```

…except this command doesn't exist (see above). The real path: delete and re-create the engine via REST with the new tier. The installer's Step 11 (`installer/gcp/engine.py`) shows the exact body shape.

### Summaries come back conservative / empty on form-heavy PDFs

Standard tier's summarization model is deliberately cautious. **Enterprise is recommended** for PDFs with lots of form fields, tables, or scanned pages. Re-run the installer and pick Enterprise at the Vertex interview.

### `'list' object has no attribute 'WhichOneof'` during search

Proto-library bug when iterating `derived_struct_data.snippets`. Skip that iteration path entirely and use the page-level extractive answer instead. The POC notes in the project memory cover this.

---

## Connector errors

### Drive sync returns 0 files

You almost certainly haven't shared the folder with the service account. The installer prints the exact SA email at the end of Step 7 — share every target folder with that address (Viewer role).

### `403 daily_limit_exceeded` (Gmail)

The Gmail API has per-project daily quotas. For first-time projects they can be tight. Request a quota increase at **https://console.cloud.google.com/apis/api/gmail.googleapis.com/quotas**.

### Personal Gmail refuses `drive.readonly` consent

This is the expected POC behaviour. Personal Gmail accounts cannot grant `drive.readonly`. The installer warns about this in the Drive interview and routes you to the **service-account mode** (share the folder with the SA, not OAuth). Pick SA mode and re-run.

### Cloud Run job stuck as `gcr.io/cloudrun/hello`

Expected in Phase 3. The installer deploys with a placeholder image and tells you to swap it for the real image once CI builds it:

```bash
gcloud run jobs update <job-name> \
  --image=<your-image> \
  --region=<region> --project=<project>
```

The actual sync worker source lives (or will live) in the repo root `cloud_run/` directory, built by the Harris team's CI.

---

## State / resume

### Installer keeps skipping steps I want to re-run

The state file at `<install-path>/state/bootstrap.state.json` remembers completed steps. To redo a step, open the file and remove it from `completed_steps`, then re-run. Or nuke the file and re-run without `-Resume`.

### `.env` or config look stale after a re-run

The installer writes config atomically, but if you rename buckets or change tier after the first run, you need to manually edit `config/config.yaml` and then re-run from the affected step. Easier: delete the state file AND the config, re-run the interview.

---

## Escape hatches

### Run only part of the install

Set checkpoints in the state file by hand. For example, to skip the interview (using an already-saved `config/config.yaml`):

```powershell
.\bootstrap.ps1 -Resume
```

To redo just the data store: remove the `"data_store"`, `"engine"`, `"connectors"`, and `"report"` entries from `completed_steps` and resume.

### Dry-run everything

```powershell
.\bootstrap.ps1
# ...then at the very end, before the review confirmation:
#   answer NO
# ...or from the venv:
.\.venv\Scripts\Activate.ps1
python -m installer --dry-run
```

### Full teardown

Phase 3 does **not** ship a teardown script (because the POC teardown rules vary by tier). Manual teardown for a Standard-tier deployment:

```bash
# Engine first
curl -X DELETE "https://discoveryengine.googleapis.com/v1alpha/projects/<num>/locations/global/collections/default_collection/engines/<engine-id>" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: <project-id>"

# Then data store
curl -X DELETE "https://discoveryengine.googleapis.com/v1alpha/projects/<num>/locations/global/collections/default_collection/dataStores/<ds-id>" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: <project-id>"

# Then Cloud Run jobs + Scheduler + GCS + SA
gcloud run jobs delete <job-name> --region=<region> --project=<project>
gcloud scheduler jobs delete <sched-name> --location=<region> --project=<project>
gcloud storage rm --recursive gs://<bucket>
gcloud iam service-accounts delete <sa-email> --project=<project>
```

Heads-up: data store IDs are reserved for hours after delete (see the POC lessons).

# 06 — Deployment

Going from "runs on Harris's laptop" to "runs unattended in GCP every hour."

## Prerequisites

- Bootstrap already complete (APIs, SA, bucket, data store, engine)
- `config/config.yaml` is correct
- Service account has:
  - `roles/discoveryengine.editor`
  - `roles/storage.objectAdmin`
  - `roles/run.invoker` (granted by Cloud Scheduler binding below)
- Any Drive folder is shared with the SA email

## One-time: enable Cloud Run + Scheduler

`bootstrap.py` already enables these. If not:

```powershell
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com
```

## Deploy the service

From repo root (must be repo root — the Dockerfile COPYs from there):

```powershell
$PROJECT  = (gcloud config get-value project).Trim()
$SA_EMAIL = "madison-sync-sa@$PROJECT.iam.gserviceaccount.com"

gcloud run deploy smb-sync `
  --source . `
  --region us-central1 `
  --no-allow-unauthenticated `
  --service-account $SA_EMAIL `
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT" `
  --timeout 1800 `
  --memory 1Gi `
  --cpu 2 `
  --max-instances 1 `
  --concurrency 1
```

`--max-instances 1` + `--concurrency 1` prevents two syncs from running in parallel and corrupting the incremental skip state.

## Schedule it

```powershell
$RUN_URL = (gcloud run services describe smb-sync --region us-central1 --format="value(status.url)").Trim()

gcloud scheduler jobs create http smb-sync-hourly `
  --location us-central1 `
  --schedule "0 * * * *" `
  --uri "$RUN_URL/run" `
  --http-method POST `
  --oidc-service-account-email $SA_EMAIL `
  --attempt-deadline 1800s
```

Cloud Scheduler will hit `/run` every hour with an OIDC token. Cloud Run verifies the token (SA has run.invoker via `--no-allow-unauthenticated`) and kicks off the pipeline.

## Verify

```powershell
# Trigger a run manually
gcloud scheduler jobs run smb-sync-hourly --location us-central1

# Watch logs
gcloud run services logs tail smb-sync --region us-central1
```

You should see:
```
stage 1: connectors
  » drive
  ...
stage 2: manifest
stage 3: import
```

## Updating

Any code change: `gcloud run deploy smb-sync --source .` again. It rebuilds the image and pushes a new revision.

Config change only (e.g., new property folder): also a re-deploy, because `config.yaml` is baked into the image. If you want live config, move it into a GCS object or Secret Manager and fetch at request time.

## Cost expectations

Rough monthly estimate for a single SMB:

| Component        | Usage                        | Cost           |
|------------------|------------------------------|----------------|
| Vertex AI Search | Enterprise + LLM add-on      | ~$2/GB indexed + per-query |
| GCS              | ~10 GB mirrored docs         | ~$0.20         |
| Cloud Run        | ~30s * 720 runs = 6 hrs CPU  | ~$1            |
| Scheduler        | 720 invocations              | free           |
| Drive API        | free                         | free           |

Budget alert suggested. Set one in Billing → Budgets & alerts.

## Tearing down

```powershell
gcloud scheduler jobs delete smb-sync-hourly --location us-central1
gcloud run services delete smb-sync --region us-central1
gcloud alpha discovery-engine engines delete <engine-id> --location=global --collection=default_collection
gcloud alpha discovery-engine data-stores delete <data-store-id> --location=global --collection=default_collection
gcloud storage rm -r gs://<bucket>/
```

(Order matters: engine references data store, data store references bucket.)

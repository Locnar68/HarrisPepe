# 07 — Troubleshooting

## Auth

| Symptom                                                    | Cause                                                                 | Fix |
|------------------------------------------------------------|-----------------------------------------------------------------------|-----|
| `DefaultCredentialsError: File ... not found`              | `.env` points at a key path that doesn't exist                        | Either download the key (`gcloud iam service-accounts keys create ...`) or comment out `GOOGLE_APPLICATION_CREDENTIALS`. |
| `User project denied`                                      | gcloud ADC's quota project is a different project than the one in config | `gcloud auth application-default set-quota-project <project-id>` |
| `This app is blocked` (Google OAuth screen)                | Personal Gmail trying to grant Drive scope to the gcloud shared OAuth client | Use SA + folder share. Impossible to fix via OAuth on personal Gmail. |
| `403 Request had insufficient authentication scopes` (Drive)| SA credentials without the drive.readonly scope, OR folder not shared with SA | First check the folder is shared with the SA email. Then verify `core/clients.py:drive_service()` is passing `scopes=DRIVE_SCOPES`. |
| PowerShell splits your `--scopes=a,b,c` on commas          | Unquoted comma-separated arg                                          | Wrap in quotes: `--scopes="a,b,c"` |

## Bootstrap

| Symptom                                                    | Cause                                    | Fix |
|------------------------------------------------------------|------------------------------------------|-----|
| `PermissionDenied` enabling APIs                           | SA missing `serviceusage.services.enable`| Add `roles/serviceusage.serviceUsageAdmin` or run bootstrap as a user (not SA). |
| Bucket creation fails with `Bucket name already exists`    | GCS bucket names are globally unique     | Pick a more-unique name in `config.yaml → gcs.bucket`. Convention: prefix with project id. |
| Data store creation hangs past 3 minutes                   | Rare. Usually a transient Vertex issue.  | Cancel, retry. `bootstrap.py` is idempotent. |
| `project not found or deleted` on billing query           | Quota project is a nonexistent project   | See auth table above (`set-quota-project`). |

## Sync

| Symptom                                    | Cause                                                           | Fix |
|--------------------------------------------|-----------------------------------------------------------------|-----|
| `no connectors enabled`                    | All connectors have `enabled: false`                            | Flip at least one to `true` in `config.yaml`. |
| Drive walks 0 files                        | Folder id wrong, or folder not shared with SA                   | Open folder in browser as the SA (impossible directly — try as Michael). Then re-share. |
| Sync works but only indexes Workspace docs | The folder has only Google Docs/Sheets. We export them to PDF; that works. Real issue is a Drive permission on binary files. | Ensure the share is at folder level, not per-file. |
| Cloud Run `/run` 500s with "drive auth failed" | SA key not bundled, or `.env` not in image | Don't rely on `.env` in Cloud Run. Use `--set-env-vars` at deploy time. |

## Index

| Symptom                                              | Cause                                                  | Fix |
|------------------------------------------------------|--------------------------------------------------------|-----|
| `no documents classified`                            | Sync produced files, but none match `Properties/<p>/<cat>/...` | Run `python scripts/index.py --discover` to see what's in the bucket. |
| `skipped unknown category folders: {'04-Things': 3}` | Michael made up a new category folder                  | Either add `"04-Things": <tag>` to `metadata.category_folders`, or have him move the files. |
| Import reports `failure > 0`                         | Some docs couldn't be fetched or parsed                | Check Cloud Console → Vertex AI Search → Data store → Activity for the per-doc error list. Usually bad PDF encoding. |

## Query

| Symptom                                    | Cause                                          | Fix |
|--------------------------------------------|------------------------------------------------|-----|
| Answer says "I don't have that information"| Retrieval missed the doc                        | Drop to `--mode=search`. If doc is there, rephrase. If not, check indexing. |
| `--property=X` returns nothing, `--property=x` works | Filter is case-sensitive                      | Property names must match folder names exactly. |
| Gemini answer is terse and unhelpful       | Only 1–2 small docs retrieved                  | Increase `max_return_results` in `vertex/answer.py`. Also verify the folder has real content, not just file names. |
| Indexing lag — fresh docs don't appear     | Vertex takes 5–15 min after import             | Wait. Verify op succeeded in Activity log. |

## Cloud Run

| Symptom                          | Cause                                              | Fix |
|----------------------------------|----------------------------------------------------|-----|
| Deploy fails: "COPY failed"      | Build context wasn't repo root                     | Run `gcloud run deploy --source .` from the repo root. |
| Import hits 30-min Cloud Run cap | First-time backfill of thousands of docs           | Run `scripts/index.py` once locally to backfill, let Cloud Run handle deltas. |
| Two simultaneous runs corrupt skip state | `--concurrency` > 1 or Scheduler retried during a slow run | Redeploy with `--max-instances 1 --concurrency 1`. |

## Diagnostic recipe

When in doubt, in this order:

```powershell
python scripts\doctor.py
gcloud storage ls gs://<bucket>/data/ --recursive | measure
python scripts\index.py --discover --no-import
python scripts\query.py --mode=search "a word from your corpus"
```

If steps 1–3 are green and step 4 finds nothing, indexing is still in progress — wait 10 minutes.

# Phase 3 Bootstrap — Lessons Learned

Hard-won troubleshooting knowledge from real deployments. Add to this doc whenever
a new failure mode is discovered.

---

## 1. GCS bucket names are globally unique (and they linger after deletion)

**Symptom:** Bootstrap reports success, but every upload fails with
```
403 Forbidden: ... does not have storage.objects.create access to the
Google Cloud Storage object. Permission denied on resource (or it may not exist).
```

**Root cause:** The bucket name collided with an existing bucket (possibly your
own from a prior POC in the 7-day deletion reservation window, possibly
someone else's). Bucket creation silently failed and never got retried, so all
subsequent `upload` calls target a nonexistent bucket — which GCS reports as a
403 (to prevent bucket-name enumeration), not a 404.

**Fix:** Always suffix bucket names with the project *number* (not the project
ID string — numbers are unambiguously unique per project).

```python
bucket_name = f"{company}-rag-raw-{project_number}"  # e.g. ...-raw-621629992886
```

**Recovery when already broken:** Run `python scripts/ensure_gcs_buckets.py`.
It detects the collision, re-creates with the project-number suffix, and
rewrites `.env`.

**Key insight:** The 403 error message's parenthetical "(or it may not exist)"
is LITERAL. Don't dismiss it as verbose error phrasing.

---

## 2. `GOOGLE_APPLICATION_CREDENTIALS` env var overrides everything

**Symptom:** You ran `gcloud auth application-default login` expecting your user
credentials to be used, but operations still act as the service account (or fail
with the SA's permissions).

**Root cause:** When `GOOGLE_APPLICATION_CREDENTIALS` is set (including via
`.env`), it takes priority over user ADC for all Google client libraries.

**Fix:** When you explicitly want user credentials, unset it:
```python
os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
```
Conversely, when you explicitly want service account credentials, load the key
file directly rather than relying on ADC resolution.

---

## 3. `gcloud auth application-default login` refuses Drive scope

**Symptom:**
```
ERROR: https://www.googleapis.com/auth/cloud-platform scope is required
```
when trying to add `drive.readonly` to user ADC.

**Workaround:** Don't fight it. Use a **service account** with Drive scope for
Drive access, and either the same SA or user ADC for GCP operations. The sync
script uses this hybrid pattern explicitly.

---

## 4. Drive folder must be shared with the service account

**Symptom:** `drive.files().list()` returns `files: []` even though files exist.
No error — just empty.

**Fix (simplest):** Open the folder in Drive → Share → Change to "Anyone with
the link → Viewer". This grants access to the service account without needing
to add it by email.

**Verify:** `python scripts/diagnose.py` (or the Drive listing block in
`manual_sync.py`) will show files if sharing is correct.

---

## 5. Layout Parser must be set at data store creation time

**Symptom:** PDFs are indexed but content isn't searchable — only the filename
matches. Gemini summaries return "No results could be found."

**Root cause:** `documentProcessingConfig.defaultParsingConfig.layoutParsingConfig`
cannot be patched after the data store exists.

**Fix:** Set it at creation time via the `v1alpha` REST endpoint with the correct
body. If already created wrong, the data store must be recreated — append
`-v2`, `-v3` etc. to the ID to avoid the reserved-name wait.

**Verify:** `python scripts/test_rag.py` — Step 1 reports which parser is active.

---

## 6. Indexing takes 5–15 minutes after document upload

**Symptom:** `create_document` succeeds, but searches return zero hits for a
while afterward.

**Not a bug.** Vertex AI Search needs to parse the PDF (Layout Parser), extract
chunks, generate embeddings, and build the index. This is not synchronous with
the `create_document` call.

**Verify progress:** `python scripts/check_index.py` — compares datastore
document count vs. what the engine returns. If engine count < datastore count,
indexing is still in progress.

---

## 7. Bootstrap creates infrastructure, not a sync image

**Symptom:** Cloud Run job exists but prints "Hello from Cloud Run!" and
indexes nothing.

**Root cause:** The bootstrap deploys with `gcr.io/cloudrun/hello` as a
placeholder. Actual sync connector code must be built, pushed, and swapped in:

```bash
gcloud run jobs update <job> --image=<actual-image> --region=<region>
```

**Interim:** Use `python scripts/manual_sync.py` for on-demand syncs until the
connector image is built.

---

## 8. Cloud Run env vars with slashes need a YAML file

**Symptom:** Deploy fails with weird errors if `--set-env-vars` contains values
with `/` (like MIME types or GCS URIs).

**Fix:** Use `--env-vars-file env.yaml` instead of inline `--set-env-vars`.

---

## 9. gcloud `discovery-engine` commands don't exist at top level

**Symptom:** `gcloud discovery-engine ...` → command not found.

**Fix:** Only `gcloud alpha discovery-engine ...` exists, and it's thin. For
anything substantive, use the REST API at `discoveryengine.googleapis.com`
with the Python `google-cloud-discoveryengine` SDK. The `v1alpha` endpoint is
required for `documentProcessingConfig` operations.

---

## 10. Standard tier can't do meaningful summarization

**Symptom:** Summaries are terse, miss obvious content, or fail with
`FailedPrecondition` on `extractive_content_spec`.

**Fix:** Set `VERTEX_TIER="ENTERPRISE"` in `.env` before creating the data
store. Standard tier is fine for small-scale keyword search only.

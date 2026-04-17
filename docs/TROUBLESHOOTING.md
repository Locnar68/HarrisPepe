# Troubleshooting

When something doesn't work, run the diagnostic first:

```powershell
python scripts/diagnose.py
```

It pinpoints the actual failure (bucket missing, IAM missing, SA mismatch, etc.)
instead of making you chase symptoms.

## Common failures and fixes

### 1. Upload fails with `403 ... storage.objects.create denied`

The bucket probably doesn't exist. GCS returns 403 for nonexistent buckets
(anti-enumeration behavior), and the error message says "or it may not exist" —
which is literal. The bootstrap may have silently lost a name-collision race.

**Fix:**
```powershell
python scripts/ensure_gcs_buckets.py
python scripts/manual_sync.py
```

`ensure_gcs_buckets.py` detects collisions, appends the project number for
guaranteed uniqueness, and rewrites `.env`.

### 2. Drive folder returns zero files

The service account can't see the folder. **Open the folder in Drive → Share →
"Anyone with the link → Viewer"**. Then verify:

```powershell
python scripts/diagnose.py       # checks Drive access
python scripts/manual_sync.py    # re-sync
```

### 3. Cloud Run job runs but indexes nothing

The bootstrap deploys a placeholder `gcr.io/cloudrun/hello` image. Until the
actual connector image is built and deployed, use manual sync:

```powershell
python scripts/manual_sync.py
```

### 4. Search works for filenames but not PDF content

The data store wasn't created with the Layout Parser enabled. Verify:

```powershell
python scripts/test_rag.py       # Step 1 reports parser config
```

If Layout Parser is missing, the data store must be recreated with `-v2`
suffix — `documentProcessingConfig` cannot be patched after creation.

### 5. Indexed documents aren't searchable yet

**Wait 5–15 minutes.** Indexing is async; `create_document` returns
immediately but parsing, chunking, and embedding take time. Check progress:

```powershell
python scripts/check_index.py
```

If the engine returns fewer docs than the data store contains, it's still
indexing.

### 6. Web UI says "OFFLINE" but the backend is fine

Verify the backend independently:

```powershell
python scripts/test_rag.py "list all documents"
```

If you see a Gemini-generated summary with citations, the backend is working
and the OFFLINE badge in the web UI is a stale health check — not an actual
outage.

## Utility scripts reference

| Script | Purpose |
|--------|---------|
| `scripts/diagnose.py` | One-shot root-cause diagnostic |
| `scripts/ensure_gcs_buckets.py` | Create/recover GCS buckets with collision-safe naming |
| `scripts/manual_sync.py` | On-demand Drive → GCS → Vertex AI Search sync |
| `scripts/check_index.py` | Compare data store doc count vs. engine-visible docs |
| `scripts/test_rag.py` | End-to-end RAG test with Gemini summarization |

See `docs/LESSONS_LEARNED.md` for the full set of gotchas and their explanations.

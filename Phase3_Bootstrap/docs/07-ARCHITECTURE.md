# 07 — Architecture

How Phase 3 implements each band of the reference architecture. The diagram in the root README has six vertical bands — **Sources, Ingestion/Sync, Document Processing, Storage & Indexing, Application/Retrieval, LLM/Response** — plus a cross-cutting ops band. Phase 3 wires every band at install time; the runtime pieces (query UI, the actual Cloud Run workers) are Phase 1/2 / Phase 3.1 concerns.

---

## Sources

Phase 3 ships with two source connectors enabled and three stubbed:

| Source | Status | Auth pattern |
|---|---|---|
| Gmail | ✅ enabled | OAuth 2.0 installed-app, refresh token in Secret Manager |
| Google Drive | ✅ enabled | Service account + explicit folder share (works with personal Gmail) |
| OneDrive / SharePoint | 🧱 Phase 4 | TBD — rclone-based |
| SQL database | 🧱 Phase 4 | TBD — per-DB driver |
| File share / SMB | 🧱 Phase 4 | TBD — Cloud VPN + rclone |

All source configuration flows through the interview and lands in `config/config.yaml` under `connectors[]`.

---

## Ingestion / Sync

Each enabled source becomes:

- **A Cloud Run Job** — the actual sync worker, runs to completion then exits. One job per source keeps blast radius small.
- **A Cloud Scheduler entry** — invokes the job on the cron expression picked during the interview (default: every 6 hours for Gmail, every 3 hours for Drive).

Phase 3's installer creates both resources via `gcloud run jobs create` and `gcloud scheduler jobs create http`. The job image is a **placeholder** (`gcr.io/cloudrun/hello`) at install time — the operator swaps it for the real built-in-CI image afterwards.

The sync contract every worker follows:

1. Read state (last sync cursor) from GCS raw bucket
2. Pull incremental changes since cursor
3. Write raw bytes to `gs://<raw-bucket>/<source>/<YYYY>/<MM>/<DD>/...`
4. Emit a Pub/Sub event (Phase 3.1) for downstream processing
5. Update cursor and exit 0

---

## Document Processing & Normalization

Phase 3 lets Vertex AI Search do as much of this as possible, via the **Layout Parser** (set at data-store creation time — cannot be patched later, per POC learning).

What Layout Parser handles out of the box:

- Text + attachment extraction from PDFs, DOCX, HTML
- OCR on scanned PDFs
- Structure preservation (headings, tables, lists)
- Chunking + embedding generation

What we handle ourselves (pre-upload):

- MIME-type filtering (per-connector allowlist)
- Deduplication via content hashes (keys on GCS object MD5)
- Path-based metadata extraction (e.g. `Properties/15-Northridge/06-Invoices/*.pdf` → `property=15-Northridge, category=Invoices, doc_type=billing` — the Phase 1 convention)
- ACL mapping (at this tier: one ACL per data-store — a future phase will use per-doc ACLs)

---

## Storage & Indexing

| Role | GCP resource | Naming |
|---|---|---|
| Canonical raw store | GCS bucket | `<business>-rag-raw` |
| Processed / normalized store | GCS bucket | `<business>-rag-processed` |
| Archive (optional) | GCS bucket | `<business>-rag-archive` |
| Search data store | Discovery Engine data store | `<business>-ds-v1` |
| Search engine | Discovery Engine engine | `<business>-engine-v1` |
| Metadata / audit | (Phase 3.1 — BigQuery dataset) | |
| Secrets | Secret Manager | `gmail-oauth-client-secret`, `gmail-refresh-token`, `gdrive-oauth-client-secret` (when OAuth mode) |

Hybrid search (keyword + semantic) is provided natively by Vertex AI Search — no separate Vector Search index needed at this scale.

---

## Application / Retrieval

Phase 3 doesn't ship a web UI — it creates the **search engine serving config** and leaves the application layer to Phase 1/2's `vertex/` and `scripts/query.py`. The final report prints the serving config path the query layer should use:

```
projects/<project-number>/locations/global/collections/default_collection/engines/<engine-id>/servingConfigs/default_search
```

Authentication / RBAC: the SA key in `<install>/secrets/service-account.json` is the single machine identity for all reads. Multi-tenant RBAC is a Phase 4 concern.

---

## LLM / Response

The Enterprise engine has the Gemini add-on enabled at creation time (`searchAddOns: [SEARCH_ADD_ON_LLM]` — see `installer/gcp/engine.py`). That gives:

- Prompt construction with retrieved chunks in-context
- Grounded answer with citations back to source URIs
- Optional tools / agents (email send, fetch, summarize thread) — Phase 3.1 surface

---

## Cross-cutting / operations

| Concern | Phase 3 implementation |
|---|---|
| IAM / least privilege | SA with 7 narrow roles (see `schema.py::ServiceAccountConfig.roles`) |
| Secret Manager | Plaintext client secrets scrubbed immediately after upload (see `installer/gcp/secret_manager.py`) |
| Encryption | Default GCS at-rest encryption; TLS in transit for all REST calls |
| Monitoring / logging | All gcloud stderr captured to `<install>/logs/bootstrap-*.log`. Runtime: Cloud Run + Scheduler emit to Cloud Logging |
| Alerting | Phase 4 — log-based alert policies |
| Feedback loop / eval | Phase 4 — feedback bucket + quality dashboard |
| Incremental sync / change detection | Cursor-per-source in raw bucket; Cloud Scheduler re-runs |
| Re-indexing | Delete data store, wait for reservation window to clear, re-create with `-v2` (installer handles this automatically) |

---

## End-to-end flow (matches the diagram)

```
1. User asks a question
       |
       v
   Web App / Chat UI / API  (Phase 1/2 scripts/query.py, or future web UI)
       |
       v
2. Query orchestration
   - parse filters, call servingConfigs/default_search
   - hybrid search (keyword + semantic) returns top-K chunks
   - ACL check (at data-store level for Phase 3)
       |
       v
3. Send query + retrieved chunks to Gemini via search engine
       |
       v
4. Engine returns grounded answer + citations
       |
       v
   Answer rendered in UI with citations back to Gmail / Drive source URIs
```

Steps 1 and 4 are the application layer (Phase 1/2). Steps 2 and 3 are the engine + data store created in Phase 3's Step 10 and Step 11.

---

## What Phase 3 deliberately does NOT do

- **Build / push container images.** The sync worker images are a CI concern. Phase 3 deploys Cloud Run jobs with placeholder images and prints the swap-in command.
- **Load initial content.** First-run ingestion happens when you trigger the Cloud Run job for the first time (or when Scheduler first fires it).
- **Implement per-document ACLs.** Phase 3 uses engine-wide access. Per-doc ACLs require the ACL API and a metadata table — Phase 4.
- **Run a web UI.** Query CLI is in `scripts/query.py` (Phase 1). Web UI is out of scope.
- **Handle secret rotation.** Secret Manager supports versioning, but the installer writes version 1 only. Rotation is an operational concern.

# 08 — Roadmap

Phased plan. Each phase is independently shippable.

## Phase 1 — Visual-first RAG (shipped)

- ✅ GCP bootstrap (APIs, SA, bucket, data store, engine)
- ✅ Google Drive connector with SA folder-share
- ✅ Local files connector
- ✅ Path-based metadata tagging
- ✅ JSONL manifest + ImportDocuments
- ✅ `query.py` with both `search` and `answer` modes, faceted filters
- ✅ `doctor.py` diagnostics
- ✅ Interactive `install.ps1`
- ✅ Cloud Run + Scheduler deploy path

**Exit criteria:** Michael can ask "How much did we pay the plumber at Northridge?" and get a grounded answer citing a JPG of a handwritten check.

## Phase 2 — Connector breadth (next)

Implement the three stubbed connectors. Order of business value:

1. **Gmail** — invoices and permit notices land in email before Drive. Biggest coverage win. Per-user OAuth flow (personal Gmail) or domain-wide delegation (Workspace). See `04-CONNECTOR_GUIDE.md`.
2. **OneDrive** — for clients who use Microsoft rather than Google. rclone-based.
3. **CSV** — row-as-document synthesis. Unlocks contact list / ledger / asset register ingestion.

**Exit criteria:** `python scripts/sync.py --only gmail` works against Michael's Gmail. Same for onedrive, csv.

## Phase 3 — Document drafting

The "fill in the blanks" feature. Separate from RAG retrieval.

- `templates/` directory of Word/Markdown with `{{placeholder}}` tokens
- `templates/queries.yaml` mapping each placeholder to a RAG query
- `scripts/draft.py <template> --property=15-Northridge` → fills placeholders → emits .docx

Example template (`templates/permit-renewal.md`):

```
TO: {{permit_issuer}}
RE: Renewal of permit {{permit_number}} at {{property_address}}
The permit issued on {{issue_date}} expires on {{expiry_date}}. ...
```

The drafting engine does not need ingestion logic — it calls `vertex.answer(...)` per placeholder, caches within a draft session, collates into the template.

**Exit criteria:** Michael can run `python scripts/draft.py permit-renewal --property=15-Northridge` and get a .docx ready to edit.

## Phase 4 — Multi-tenant

The current architecture is single-tenant (one GCP project, one data store, one SMB). If we want to serve multiple SMBs from one deployment:

- Namespace resources by tenant id (`<tenant>-docs`, `<tenant>-search-app`)
- Extract tenant from request context in `cloud_run/main.py`
- Each tenant gets their own GCS bucket prefix
- Per-tenant config → load from Firestore/Spanner, not `config.yaml`
- Per-tenant SA + folder-share setup, or shared SA with per-folder ACLs

This is a big lift. Don't start until you've proven Phases 1–3 work for at least one real SMB.

## Phase 5 — UX surface

CLI is fine for Harris. Michael needs something friendlier. Options, in effort order:

1. **Slack bot.** `@smb-search What did we pay the plumber?` → answer+citations in-thread.
2. **Web chat.** Flask page with a chat box, calls `vertex.answer()` behind auth.
3. **Custom GPT / Gemini Gem.** Expose `query.py` via a simple HTTPS API, wire as an action.

## Non-goals (explicitly)

- **OCR pipelines.** Gemini reads images natively at query time; pre-OCR is a cost sink.
- **AI-classified metadata.** We tag from folder paths. Deterministic beats clever.
- **Full Drive/OneDrive replication.** We index what the Properties/ tree contains. Personal photos and stray drafts should stay out.

## When to revisit

- If an SMB's `doc_type` set doesn't fit ours → update `metadata/schema.py` + docs.
- If a single data store grows past ~10M docs → consider sharding by region.
- If query latency creeps above 2s for `answer` mode → consider `search` as default and make `answer` opt-in.

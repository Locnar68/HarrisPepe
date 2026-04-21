# Known Issues & Phase 4+ TODO

Deferred work items surfaced during Phase 3 validation. Ranked by impact.

---

## 1. Layout Parser drops most rows from dense tabular PDFs — HIGH IMPACT

**Status:** Confirmed 2026-04-18 during Island Advantage POC validation.

### Symptom

The inventory PDF (`04-12-26 Inventory (1).pdf`, ~150 property rows across
5 pages) was successfully synced to GCS and registered in Vertex AI Search.
Gemini summaries return a handful of property addresses and are factually
correct — but **only about 8 out of 150+ rows are searchable**.

Test queries that should have hit but returned `Results: 0`:

| Query | In PDF? | Returned |
|---|---|---|
| `"Amityville"` | Yes, row 33 (14 Chevy Chase, $430k) | 0 results |
| `"14 Chevy Chase"` | Yes, verified visually | 0 results |
| `"430,000"` | Yes, at least once | 0 results |

Queries that DO hit (~8 addresses) are the ones Gemini surfaced in its
original "list all properties" summary.

### Root cause

Vertex AI Search's Layout Parser is optimized for document-oriented PDFs
(contracts, reports, letters). When it encounters a dense data grid — our
REO inventory table with ~13 columns × 150 rows packed into 5 pages — it
can't reliably segment rows. Most cells get dropped from the chunk output
entirely. This is the same class of problem as the Phase 1/2 finding that
"permit PDF extraction remained limited" (see LESSONS_LEARNED.md §5, §10).

Vertex AI Search is a document-oriented RAG system. Our inventory is
structured tabular data dressed up as a PDF. It's the wrong shape for
Layout Parser.

### Fix options

**Option A — Quick workaround (5 min per inventory):**

In Drive: open the inventory PDF → `File → Open with → Google Sheets` →
export as CSV → drop CSV into the same Drive folder → re-run
`scripts/manual_sync.py`. Vertex handles CSVs natively with one row per
indexable record. "Chevy Chase" will hit.

Works for ad-hoc use. Doesn't scale; doesn't belong in a handover package.

**Option B — Doc-type-aware preprocessor in `manual_sync.py` (proper fix):**

Detect tabular documents by filename/content and convert them to per-row
JSON documents before indexing.

```
if filename matches /inventory|rent[- ]roll|p&l/i
    OR if PDF tables detected via pdfplumber:
    → extract rows with pdfplumber
    → emit one Vertex Document per row with structured fields
      (address, city, price, status, etc.)
    → index as JSON instead of raw PDF
else:
    → current path (upload PDF, let Layout Parser handle it)
```

This keeps contracts, permits, deeds, closing docs on the Layout Parser
path where it actually works, and routes the tabular stuff where it
belongs.

Estimated effort: 1–2 hours for a PoC on the known inventory format;
1–2 days for robust auto-detection + multiple table schemas.

### Why this matters for handover

A customer asking "what's the price of 14 Chevy Chase?" gets a misleading
"I couldn't find anything" response today — not because the data isn't
there, but because Vertex never saw it. This needs to be fixed before any
production deployment that includes tabular inventories.

### References

- Gemini summary that appeared comprehensive but wasn't:
  `test_rag.py "list all properties in the inventory"` returned 8
  addresses with "Here are some of the properties listed" phrasing.
  The "some of" was literal — the other ~140 rows weren't indexable.
- Screenshot in original Drive folder confirms 14 Chevy Chase is on page 1,
  row 33 of the PDF.
- LESSONS_LEARNED.md §10 already flagged Standard tier's weak
  summarization for form-heavy PDFs; this is the same shape of problem.

---

## 2. `share-drive-folder.ps1` uses wrong SA email pattern — LOW IMPACT

**Status:** Latent bug, not currently biting.

Script hardcodes `$projectId-sa@...` but the installer creates
`{slug}-rag-sa@...`. Hasn't caused problems because the documented "Share
with Anyone with the link" path is simpler and usually used.

**Fix:** read SA email from `.env` (after writing `SERVICE_ACCOUNT_EMAIL`
there in `report.py`).

---

## 3. Cloud Run job runs placeholder image — MEDIUM IMPACT

**Status:** Known, documented in LESSONS_LEARNED.md §7.

The bootstrap deploys `gcr.io/cloudrun/hello` as the connector image.
Scheduled syncs do nothing. `manual_sync.py` is the workaround and the
bootstrap now invokes it directly after resource creation (main.py patch,
commit `e841263`).

**Fix for Phase 4:** build a real connector image from the `manual_sync.py`
logic, push to Artifact Registry, update the Cloud Run job to use it.

---

## 4. Only Drive connector is end-to-end validated — LOW IMPACT (unless needed)

Gmail connector code exists (`installer/connectors/gmail.py`) but was
never exercised. OneDrive is disabled. Fine for Island Advantage; needs
validation before any customer that depends on email or OneDrive ingest.

---

## 5. Repo housekeeping — COSMETIC

Untracked working-tree cruft:

- `cleanup.ps1`, `commit-fixes.ps1` — one-shot scripts, safe to delete
- `patch/`, `patch2/`, `patch3/` — old patch staging dirs, safe to delete
- `scripts/simple_web.py.bak` — delete
- `auto-repo.py.old`, `CleanUP.py.old` — delete

Either `.gitignore` or `rm`. Not blocking.

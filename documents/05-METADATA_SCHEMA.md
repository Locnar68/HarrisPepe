# 05 — Metadata Schema

The tags attached to every indexed document. Tagging is deterministic — derived from the GCS path, not inferred by AI.

## Core tags

| Tag        | Example             | Source                          |
|------------|---------------------|---------------------------------|
| `property` | `15-Northridge`     | 3rd path segment                |
| `category` | `Permits`           | 4th path segment, `NN-` stripped|
| `doc_type` | `permit`            | `config.category_folders` map   |
| `source`   | `drive`             | connector `name`                |
| `subpath`  | `2025-expired`      | 5th segment onwards (folders)   |
| `filename` | `permit_A1.pdf`     | last path segment               |
| `updated`  | `2025-08-12T14:22Z` | GCS object `updated` time       |

## Doc type enum

```
legal     — 01-Acquisition (deeds, titles, contracts)
finance   — 02-Financials (P&L, bank statements)
permit    — 04-Permits (building permits, inspections)
billing   — 06-Invoices (contractor bills, receipts)
image     — 07-Photos (progress photos, site conditions)
```

Adding a new `doc_type`? Do it in three places:

1. `metadata/schema.py` → extend the `doc_types` set in `validate()`
2. `config/config.yaml` → add the category folder to `category_folders`
3. `documents/02-FOLDER_STRUCTURE.md` → document the folder for Michael

## Filter syntax (Vertex AI Search)

Tags become filterable via the `filter` parameter on Search/Answer requests. Syntax:

```
property:    ANY("15-Northridge")
doc_type:    ANY("permit")
category:    ANY("Permits")
```

Multiple clauses are combined with `AND`:

```
property: ANY("15-Northridge") AND doc_type: ANY("permit")
```

`ANY(...)` supports multiple values: `property: ANY("15-Northridge", "22-Willow")`.

CLI usage:

```powershell
python scripts\query.py --property=15-Northridge --doc-type=permit "expire"
```

## Why no AI classifier?

We considered having Gemini read each file on ingest and assign tags. We rejected it because:

- **Cost.** That's an extra LLM call per file per sync.
- **Latency.** Bulk backfill of thousands of files would take hours.
- **Determinism.** Folder-based tagging gives identical results on re-runs. An LLM won't.
- **Debuggability.** If a search misses, we can point at a wrong folder. An LLM classifier is a black box.

The folder path is the contract. If the folder is wrong, fix the folder — don't try to train the AI around it.

## What Gemini DOES do

Visual reasoning at query time. A handwritten plumber's check in `06-Invoices/` gets:
- Tagged as `doc_type=billing` by path (deterministic)
- Read by Gemini at answer time (multimodal RAG)

So the handwriting never needs OCR preprocessing — the model reads the image pixels during `answer_query`.

## Extending the schema

For tags that can't be derived from path (e.g., contract end date, invoice amount):

**Option A — structured extraction during ingest.** Add a post-sync step that parses PDFs and writes richer `structData`. Expensive, but unlocks queries like "invoices over $5000".

**Option B — let Gemini find it at query time.** Cheap. Works well for "when does the permit expire" because it's already in the document text.

We default to B. Graduate to A only when you hit concrete queries B can't answer.

# 01 — Architecture

## Pipeline

```
┌─────────────────────┐
│   Data sources      │  Google Drive  │  Gmail  │  OneDrive  │  Local  │  CSV
└──────────┬──────────┘
           │
           │   connectors/*.py           scripts/sync.py
           ▼
┌─────────────────────┐
│   GCS mirror bucket │  gs://<bucket>/data/...
└──────────┬──────────┘
           │
           │   metadata/extractor.py     scripts/index.py
           │   ingestion/manifest.py
           ▼
┌─────────────────────┐
│  manifest.jsonl     │  gs://<bucket>/_manifests/manifest.jsonl
└──────────┬──────────┘
           │
           │   ingestion/inject.py  (ImportDocuments)
           ▼
┌─────────────────────┐
│  Vertex AI Search   │  Data Store + Engine
│  Data Store         │  Enterprise tier + LLM add-on (Gemini)
└──────────┬──────────┘
           │
           │   vertex/search.py  (ranked results)
           │   vertex/answer.py  (Gemini RAG)      scripts/query.py
           ▼
┌─────────────────────┐
│      Michael        │  Natural language answers with citations
└─────────────────────┘
```

## Separation of concerns

| Layer       | Job                                             | Don't put here           |
|-------------|-------------------------------------------------|--------------------------|
| `core/`     | config, client factories                        | business logic           |
| `bootstrap/`| one-time GCP resource creation                  | anything per-document    |
| `connectors/`| per-source ingest (Drive walk, etc.)           | metadata tagging         |
| `metadata/` | path → tags                                     | per-source logic         |
| `ingestion/`| build + upload manifest, call ImportDocuments   | content interpretation   |
| `vertex/`   | search + answer queries                         | ingestion logic          |
| `scripts/`  | thin CLI wrappers around the above              | real logic (import it)   |

## Why a GCS mirror?

- Vertex AI Search ingests from GCS URIs. You can't hand it an OAuth token for a Drive folder.
- GCS decouples the connector from the indexer — if Drive goes flaky, GCS still has the snapshot.
- Incremental is easy: stash `source_mtime` in GCS object metadata, skip unchanged blobs.
- Multiple connectors land in the same bucket. The metadata extractor doesn't care where a file came from.

## Why JSONL manifest instead of inline ingestion?

Vertex AI Search's `ImportDocuments` API takes one of three inputs:
1. A BigQuery table
2. Inline documents (small-scale only)
3. A GCS URI pointing to JSONL

Option 3 is the scalable path. Each JSONL record binds a GCS URI (the actual file) to `structData` (our metadata tags). Vertex fetches the file and indexes it with the tags attached.

## ID stability

The document id is `sha1(gs://bucket/path)`. This means:
- Re-running sync + index is idempotent — same path produces same id.
- Renaming a file (or moving it between folders) creates a NEW document id. The old one becomes an orphan until you run `index --full`.

## When things break

Diagnose top-down:
1. `python scripts/doctor.py` — infrastructure
2. `gcloud storage ls gs://<bucket>/data/` — did sync produce anything?
3. `python scripts/index.py --discover` — what does metadata see?
4. Vertex console → data store → Activity tab — any import errors?
5. `python scripts/query.py --mode=search "test"` — does retrieval work?
6. `python scripts/query.py --mode=answer "test"` — does Gemini work on top?

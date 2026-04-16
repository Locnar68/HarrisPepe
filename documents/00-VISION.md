# 00 — Vision (v4.0+)

## VERTEX AI SMB BOOTSTRAPPER

### Purpose

This project deploys a complete AI-powered search pipeline for small-to-medium businesses. It connects fragmented data sources into a single searchable system using:

- Google Cloud Storage
- Vertex AI Search
- Gemini (RAG)

### Quick Start

1. Open PowerShell
2. Navigate to project: `cd d:\lab\vertex-ai-search`
3. Run installer: `.\install.ps1`
4. Follow prompts:
   - GCP Project ID
   - Region
   - Gmail / Drive connection (optional)
   - OneDrive sync (optional)

### What This Sets Up

- Python environment
- Google Cloud CLI
- GCP project + APIs
- GCS bucket
- Vertex AI Search data store
- Ingestion pipeline
- Metadata tagging system

### Folder Structure

```
/vertex-ai-search
│
├── bootstrap/
├── connectors/
├── ingestion/
├── metadata/
├── vertex/
├── scripts/
├── config/
└── install.ps1
```

### Core Concept

The system does **NOT** rely on AI to interpret chaos.
Instead:

- Data is structured
- Metadata is derived from folders
- Vertex AI performs retrieval over structured inputs

### Example

Input file path: `Properties/15-Northridge/06-Invoices/invoice1.pdf`

Becomes:

- `property = 15-Northridge`
- `doc_type = billing`

### First Test Query

After setup, run:

```powershell
python scripts/query.py "How much did we pay the plumber?"
```

### Connectors (Planned)

- Gmail
- Google Drive
- OneDrive (rclone)
- File shares
- CSV imports

### Notes

- Do NOT overwrite Data Store IDs
- Use versioning (v1, v2)
- Always validate ingestion before querying

### Goal

Give any SMB the ability to:

- search ALL company data
- ask natural language questions
- generate documents from real data

---

**END**

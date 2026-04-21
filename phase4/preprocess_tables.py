"""
Phase 4A: Table-to-JSON Preprocessor (No-GCS version)
Posts row-level JSON documents directly into Vertex AI Search.
No GCS bucket required.

USAGE:
    python preprocess_tables.py --scan "D:\LAB\Madison\files"
    python preprocess_tables.py "Appraisal 15 Northridge Dr.pdf"
    python preprocess_tables.py --scan "D:\LAB\Madison\files" --dry-run

INSTALL:
    pip install pdfplumber google-auth requests
"""

import os, sys, json, hashlib, argparse
from pathlib import Path
import pdfplumber
from google.oauth2 import service_account
import google.auth, google.auth.transport.requests
import requests

PROJECT_ID    = os.getenv("GCP_PROJECT_ID",           "commanding-way-380716")
DATA_STORE_ID = os.getenv("VERTEX_DATA_STORE_ID",     "madison-ave-docs")
LOCATION      = "global"
BATCH_SIZE    = 100   # Vertex inline import limit per request
MIN_ROWS      = 4
MIN_COLS      = 3

def _load_creds():
    for key in [
        Path(__file__).resolve().parent.parent / "service-account.json",
        Path(__file__).resolve().parent / "service-account.json",
    ]:
        if key.exists():
            return service_account.Credentials.from_service_account_file(
                str(key), scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return creds

def _token(creds):
    req = google.auth.transport.requests.Request()
    creds.refresh(req)
    return creds.token

def _clean(cell):
    return " ".join(str(cell or "").strip().split())

def extract_tables(pdf_path):
    rows_out = []
    source = Path(pdf_path).stem
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            for tbl_idx, raw in enumerate(page.extract_tables() or []):
                if not raw or len(raw) < MIN_ROWS + 1:
                    continue
                headers = [_clean(h) or f"col_{i}" for i, h in enumerate(raw[0])]
                if len(headers) < MIN_COLS:
                    continue
                for row_idx, row in enumerate(raw[1:], 1):
                    if not any(_clean(c) for c in row):
                        continue
                    d = {"_source": source, "_page": page_num, "_table": f"t{tbl_idx+1}", "_row": row_idx}
                    for i, cell in enumerate(row):
                        if i < len(headers):
                            d[headers[i]] = _clean(cell)
                    rows_out.append(d)
    return rows_out

def rows_to_vertex_docs(rows, pdf_path):
    source = Path(pdf_path).stem
    docs = []
    for row in rows:
        seed   = f"{source}_{row['_table']}_{row['_row']}"
        doc_id = f"tbl_{hashlib.md5(seed.encode()).hexdigest()[:16]}"
        pairs  = [f"{k}: {v}" for k, v in row.items() if not k.startswith("_") and v]
        docs.append({
            "id": doc_id,
            "structData": {**row, "source_uri": f"local://{source}.pdf"},
            "content": {"mimeType": "text/plain", "rawText": f"[{source}] {' | '.join(pairs)}"}
        })
    return docs

def import_to_vertex(docs, creds, label="batch"):
    url = (f"https://discoveryengine.googleapis.com/v1/"
           f"projects/{PROJECT_ID}/locations/{LOCATION}/"
           f"collections/default_collection/dataStores/{DATA_STORE_ID}/"
           f"branches/default_branch/documents:import")
    headers = {"Authorization": f"Bearer {_token(creds)}", "Content-Type": "application/json"}

    total = 0
    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i+BATCH_SIZE]
        body  = {"inlineSource": {"documents": batch}, "reconciliationMode": "INCREMENTAL"}
        resp  = requests.post(url, json=body, headers=headers, timeout=60)
        if resp.status_code in (200, 201):
            op = resp.json().get("name","?")
            print(f"  ✓ Batch {i//BATCH_SIZE+1}: {len(batch)} docs imported — op: {op.split('/')[-1][:20]}")
            total += len(batch)
        else:
            print(f"  ✗ Batch {i//BATCH_SIZE+1} failed ({resp.status_code}): {resp.text[:200]}")
    return total

def process_pdf(pdf_path, dry_run=False):
    print(f"\n── {Path(pdf_path).name}")
    rows = extract_tables(pdf_path)
    if not rows:
        print("  → No qualifying tables. Skipping.")
        return 0
    docs = rows_to_vertex_docs(rows, pdf_path)
    print(f"  → {len(rows)} rows extracted → {len(docs)} Vertex docs")
    if dry_run:
        print(f"  → [DRY RUN] Sample: {json.dumps(docs[0], indent=2)[:300]}")
        return len(docs)
    creds = _load_creds()
    return import_to_vertex(docs, creds)

def scan_folder(folder, dry_run=False):
    pdfs = list(Path(folder).rglob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs in {folder}")
    total = 0
    for p in pdfs:
        total += process_pdf(str(p), dry_run=dry_run)
    print(f"\n✓ Done — {total} total row-docs imported")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?")
    parser.add_argument("--scan", metavar="FOLDER")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.scan:
        scan_folder(args.scan, args.dry_run)
    elif args.path:
        if Path(args.path).is_dir():
            scan_folder(args.path, args.dry_run)
        else:
            process_pdf(args.path, args.dry_run)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

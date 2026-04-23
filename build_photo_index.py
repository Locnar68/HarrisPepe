"""
build_photo_index.py
--------------------
Reads the existing import manifest from GCS, extracts photo pointer
entries, and writes photo_index.json back to GCS.

No OneDrive sync needed — works from what's already uploaded.

Usage:
  cd D:\LAB\vertex-ai-search
  python build_photo_index.py
"""
import os, json
from pathlib import Path
from dotenv import load_dotenv

# Load env
for candidate in [
    os.environ.get("VERTEX_ENV_FILE", ""),
    r"Phase3_Bootstrap\secrets\.env",
    r"Phase3_Bootstrap/secrets/.env",
]:
    if candidate and Path(candidate).exists():
        load_dotenv(candidate)
        print(f"Loaded env: {candidate}")
        break

BUCKET = (os.getenv("GCS_BUCKET_NAME") or
          os.getenv("GCS_BUCKET_RAW") or "")
SA_KEY = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or
          r"Phase3_Bootstrap\secrets\service-account.json")

if not BUCKET:
    raise SystemExit("GCS_BUCKET_NAME not set in .env")

print(f"Bucket: {BUCKET}")
print(f"SA key: {SA_KEY}")

from google.cloud import storage
from google.oauth2 import service_account

creds = service_account.Credentials.from_service_account_file(
    SA_KEY, scopes=["https://www.googleapis.com/auth/cloud-platform"])
gcs = storage.Client(credentials=creds)
bucket = gcs.bucket(BUCKET)

# Read the manifest
manifest_blob = bucket.blob("manifests/import_manifest_latest.jsonl")
if not manifest_blob.exists():
    raise SystemExit("Manifest not found in GCS — run a sync first")

print("Reading manifest...")
lines = manifest_blob.download_as_text().strip().split("\n")
print(f"  {len(lines)} entries in manifest")

# Extract photo pointer entries
photo_index = {}
count = 0
for line in lines:
    if not line.strip():
        continue
    try:
        entry = json.loads(line)
        data  = json.loads(entry.get("jsonData", "{}"))
        if data.get("document_type") != "photo_index":
            continue
        prop = data.get("property", "")
        url  = data.get("onedrive_url", "")
        cnt  = data.get("photo_count", 0)
        title = data.get("title", "")
        if prop and url:
            # Keep the entry with the most photos if property appears multiple times
            existing = photo_index.get(prop, {})
            if cnt >= existing.get("count", 0):
                photo_index[prop] = {"url": url, "count": cnt, "title": title}
                count += 1
    except Exception as e:
        continue

print(f"  Found {len(photo_index)} unique properties with photos")

if not photo_index:
    raise SystemExit("No photo_index entries found in manifest. "
                     "Run a sync with the updated onedrive_sync.py first.")

# Write photo_index.json
out = json.dumps(photo_index, indent=2)
bucket.blob("manifests/photo_index.json").upload_from_string(out)
print(f"\nWrote photo_index.json -> gs://{BUCKET}/manifests/photo_index.json")
print(f"Properties indexed: {len(photo_index)}")
print("\nSample entries:")
for k, v in list(photo_index.items())[:5]:
    print(f"  {k}: {v['count']} photos")
    print(f"    {v['url'][:80]}")

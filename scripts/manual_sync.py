"""
Manual Drive → GCS → Vertex AI Search sync.

Use this when the Cloud Run job is unavailable or you want to sync on demand.
This script uses the service account for ALL operations and requires:
  - Drive folder shared with 'Anyone with the link can view' (or SA added explicitly)
  - SA has roles/storage.admin and roles/discoveryengine.admin on the project
  - GCS bucket exists (run scripts/ensure_gcs_buckets.py first if unsure)

Usage (from repo root):
    python scripts/manual_sync.py

Reads config from Phase3_Bootstrap/secrets/.env
"""
import io
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import discoveryengine_v1, storage
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / "Phase3_Bootstrap" / "secrets" / ".env"
    sa_key = repo_root / "Phase3_Bootstrap" / "secrets" / "service-account.json"

    if not env_path.exists():
        print(f"✗ Missing .env at {env_path}")
        return 1
    if not sa_key.exists():
        print(f"✗ Missing service account key at {sa_key}")
        return 1

    load_dotenv(env_path)
    project_id = os.getenv("GCP_PROJECT_ID")
    bucket_raw = os.getenv("GCS_BUCKET_RAW")
    data_store_id = os.getenv("VERTEX_DATA_STORE_ID")
    folder_ids = [f.strip() for f in (os.getenv("GDRIVE_FOLDER_IDS") or "").split(",") if f.strip()]

    if not (project_id and bucket_raw and data_store_id and folder_ids):
        print("✗ Missing required env vars: GCP_PROJECT_ID, GCS_BUCKET_RAW, VERTEX_DATA_STORE_ID, GDRIVE_FOLDER_IDS")
        return 1

    print(f"📂 Manual sync → Vertex AI Search")
    print(f"   Project:    {project_id}")
    print(f"   Bucket:     {bucket_raw}")
    print(f"   Data Store: {data_store_id}")
    print(f"   Folders:    {folder_ids}")

    # Hybrid-safe: service account with both Drive read-only and cloud-platform scopes
    drive_creds = service_account.Credentials.from_service_account_file(
        str(sa_key), scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    gcp_creds = service_account.Credentials.from_service_account_file(
        str(sa_key), scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    print(f"   🔑 Service account: {drive_creds.service_account_email}\n")

    drive = build("drive", "v3", credentials=drive_creds, cache_discovery=False)
    storage_client = storage.Client(project=project_id, credentials=gcp_creds)
    bucket = storage_client.bucket(bucket_raw)
    vertex_client = discoveryengine_v1.DocumentServiceClient(credentials=gcp_creds)

    parent = (
        f"projects/{project_id}/locations/global"
        f"/collections/default_collection/dataStores/{data_store_id}/branches/default_branch"
    )

    total_indexed = 0
    total_skipped = 0
    for folder_id in folder_ids:
        print(f"🔍 Scanning folder: {folder_id}")
        results = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id, name, mimeType)",
        ).execute()
        files = results.get("files", [])
        print(f"   Found {len(files)} files\n")

        for file in files:
            print(f"   📄 {file['name']}")

            # 1. Download from Drive
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, drive.files().get_media(fileId=file["id"]))
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    print(f"      ↓ Download: {int(status.progress() * 100)}%")

            # 2. Upload to GCS
            blob_name = f"drive/{folder_id}/{file['name']}"
            blob = bucket.blob(blob_name)
            fh.seek(0)
            print(f"      ↑ Uploading to GCS...")
            blob.upload_from_file(fh, content_type=file["mimeType"])
            gcs_uri = f"gs://{bucket_raw}/{blob_name}"
            print(f"      ✓ {gcs_uri}")

            # 3. Create document in Vertex AI Search
            document = discoveryengine_v1.Document(
                id=file["id"],
                name=f"{parent}/documents/{file['id']}",
                struct_data={
                    "title": file["name"],
                    "uri": f"https://drive.google.com/file/d/{file['id']}",
                },
                content=discoveryengine_v1.Document.Content(
                    uri=gcs_uri,
                    mime_type=file["mimeType"],
                ),
            )
            try:
                vertex_client.create_document(
                    request=discoveryengine_v1.CreateDocumentRequest(
                        parent=parent,
                        document=document,
                        document_id=file["id"],
                    )
                )
                print(f"      ✓ Indexed in Vertex AI Search\n")
                total_indexed += 1
            except Exception as e:
                msg = str(e).lower()
                if "already exists" in msg or "alreadyexists" in msg:
                    print(f"      ℹ Already indexed\n")
                    total_skipped += 1
                else:
                    print(f"      ⚠ Index failed: {e}\n")

    print(f"✅ Sync complete: {total_indexed} indexed, {total_skipped} already present")
    print(f"   Indexing completes in 5–15 min. Check with: python scripts/check_index.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

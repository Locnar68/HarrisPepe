"""
Manual Drive → GCS → Vertex AI Search sync.

Use this when the Cloud Run job is unavailable (placeholder image) or you
want to sync on demand. Uses the service account for ALL operations.

Requires:
  - Drive folder shared with 'Anyone with the link can view', OR the SA
    added to the folder as Viewer explicitly
  - SA has roles/storage.admin and roles/discoveryengine.admin on the project
  - The GCS raw bucket exists (run scripts/ensure_gcs_buckets.py if unsure)

Usage:
    python scripts/manual_sync.py

Env discovery: $VERTEX_ENV_FILE > <cwd>/Phase3_Bootstrap/secrets/.env >
               <cwd>/.env > <repo>/Phase3_Bootstrap/secrets/.env
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import load_or_die  # noqa: E402

from google.cloud import discoveryengine_v1, storage  # noqa: E402
from google.oauth2 import service_account  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.http import MediaIoBaseDownload  # noqa: E402


def main() -> int:
    env_path, sa_key = load_or_die()

    project_id = os.getenv("GCP_PROJECT_ID")
    bucket_raw = os.getenv("GCS_BUCKET_RAW")
    data_store_id = os.getenv("VERTEX_DATA_STORE_ID")
    folder_ids = [
        f.strip()
        for f in (os.getenv("GDRIVE_FOLDER_IDS") or "").split(",")
        if f.strip()
    ]

    missing = [
        k for k, v in [
            ("GCP_PROJECT_ID", project_id),
            ("GCS_BUCKET_RAW", bucket_raw),
            ("VERTEX_DATA_STORE_ID", data_store_id),
            ("GDRIVE_FOLDER_IDS", folder_ids),
        ] if not v
    ]
    if missing:
        print(f"✗ Missing required env vars: {', '.join(missing)}")
        print(f"  loaded from: {env_path}")
        return 1

    print(f"📂 Manual sync → Vertex AI Search")
    print(f"   Project:    {project_id}")
    print(f"   Bucket:     {bucket_raw}")
    print(f"   Data Store: {data_store_id}")
    print(f"   Folders:    {folder_ids}")

    # Explicit SA creds with the right scope for each service.
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
    total_failed = 0
    for folder_id in folder_ids:
        print(f"🔍 Scanning folder: {folder_id}")
        try:
            results = drive.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType)",
            ).execute()
        except Exception as e:
            print(f"   ✗ Drive list failed: {e}")
            print(f"     → Share this folder with {drive_creds.service_account_email}")
            print(f"       (or set it to 'Anyone with the link can view').")
            total_failed += 1
            continue

        files = results.get("files", [])
        print(f"   Found {len(files)} files\n")

        for file in files:
            print(f"   📄 {file['name']}")

            # 1. Download from Drive
            try:
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(
                    fh, drive.files().get_media(fileId=file["id"])
                )
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        print(f"      ↓ Download: {int(status.progress() * 100)}%")
            except Exception as e:
                print(f"      ✗ Download failed: {e}\n")
                total_failed += 1
                continue

            # 2. Upload to GCS
            blob_name = f"drive/{folder_id}/{file['name']}"
            blob = bucket.blob(blob_name)
            fh.seek(0)
            try:
                print(f"      ↑ Uploading to GCS...")
                blob.upload_from_file(fh, content_type=file["mimeType"])
            except Exception as e:
                print(f"      ✗ GCS upload failed: {e}\n")
                total_failed += 1
                continue

            gcs_uri = f"gs://{bucket_raw}/{blob_name}"
            print(f"      ✓ {gcs_uri}")

            # 3. Create the document in Vertex AI Search
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
                    total_failed += 1

    print(f"✅ Sync complete: "
          f"{total_indexed} indexed, {total_skipped} already present, "
          f"{total_failed} failed")
    print(f"   Indexing finishes in 5–15 min. Verify with: "
          f"python scripts/check_index.py")
    return 0 if total_failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

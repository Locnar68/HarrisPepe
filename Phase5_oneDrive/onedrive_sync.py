#!/usr/bin/env python3
"""
Phase5_OneDrive/onedrive_sync.py
----------------------------------
Syncs files from a OneDrive folder to a GCS bucket, then triggers
a Vertex AI Search re-import.

Usage:
  python onedrive_sync.py               # incremental sync (delta)
  python onedrive_sync.py --force       # full re-sync regardless of delta
  python onedrive_sync.py --dry-run     # list what would sync, no writes
  python onedrive_sync.py --schedule 30 # loop every 30 minutes

SCALE-TODO: switch to client_credentials before production.
See bootstrap_onedrive.py for full instructions.
"""

import os, sys, json, time, logging, argparse, requests, msal
from datetime import datetime, timezone
from pathlib import Path
from google.cloud import storage
import google.auth
import google.auth.transport.requests

def _load_env():
    from dotenv import load_dotenv
    candidates = [
        os.environ.get("VERTEX_ENV_FILE"),
        Path(__file__).parent / "secrets" / ".env",
        Path.cwd() / "Phase5_oneDrive" / "secrets" / ".env",
        Path.cwd() / ".env",
    ]
    for c in candidates:
        if c and Path(c).exists():
            load_dotenv(c)
            return

_load_env()

AZURE_CLIENT_ID      = os.environ.get("AZURE_CLIENT_ID", "")
AZURE_TENANT_ID      = os.environ.get("AZURE_TENANT_ID", "")
ONEDRIVE_FOLDER_PATH = os.environ.get("ONEDRIVE_FOLDER_PATH", "")
GCP_PROJECT_ID       = os.environ.get("GCP_PROJECT_ID", "")
GCS_BUCKET_NAME      = os.environ.get("GCS_BUCKET_NAME", "")
VERTEX_LOCATION      = os.environ.get("VERTEX_LOCATION", "global")
VERTEX_DATASTORE     = os.environ.get("VERTEX_DATASTORE_ID", "")

SCOPES           = ["Files.Read"]
TOKEN_CACHE_PATH = Path(__file__).parent / "secrets" / "token_cache.json"
DELTA_STATE_PATH = Path(__file__).parent / "secrets" / "delta_state.json"
GRAPH_API        = "https://graph.microsoft.com/v1.0"

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("onedrive_sync")

def _get_ms_token():
    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_PATH.exists():
        cache.deserialize(TOKEN_CACHE_PATH.read_text())
    app = msal.PublicClientApplication(
        AZURE_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}",
        token_cache=cache,
    )
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result:
            log.info("Auth: using cached token")
    if not result:
        log.warning("Cached token unavailable -- starting device-code flow")
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Device flow failed: {flow.get('error_description')}")
        print("\n" + "="*60)
        print("  ACTION REQUIRED -- Microsoft sign-in")
        print("="*60)
        print(f"  1. Open:       {flow['verification_uri']}")
        print(f"  2. Enter code: {flow['user_code']}")
        print("  3. Sign in with the OneDrive account")
        print("="*60 + "\n")
        result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(
            f"Microsoft auth failed: {result.get('error_description', result)}\n"
            "SCALE-TODO: Token may have expired. See bootstrap_onedrive.py."
        )
    TOKEN_CACHE_PATH.parent.mkdir(exist_ok=True)
    TOKEN_CACHE_PATH.write_text(cache.serialize())
    return result["access_token"]

def _get_drive_id(token):
    """Get OneDrive for Business drive ID -- required for SharePoint-hosted drives."""
    r = requests.get(f"{GRAPH_API}/me/drive", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()["id"]

def _get_gcp_token():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token

def list_onedrive_files(token, force):
    delta_state = {}
    if DELTA_STATE_PATH.exists() and not force:
        try:
            delta_state = json.loads(DELTA_STATE_PATH.read_text())
        except Exception:
            pass

    delta_link = delta_state.get("delta_link")
    files = []

    if delta_link and not force:
        log.info("Using OneDrive delta link (incremental sync)")
        url = delta_link
    else:
        log.info(f"Full folder listing: {ONEDRIVE_FOLDER_PATH}")
        drive_id = _get_drive_id(token)
        log.info(f"Drive ID: {drive_id[:20]}...")
        url = f"{GRAPH_API}/drives/{drive_id}/root:/{ONEDRIVE_FOLDER_PATH}:/delta"

    while url:
        # Retry loop with backoff for Graph API rate limiting (429)
        for attempt in range(5):
            r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 20)) + 2
                log.warning(f"Rate limited by Graph API -- waiting {wait}s (attempt {attempt+1}/5)")
                time.sleep(wait)
                continue
            r.raise_for_status()
            break
        data = r.json()
        for item in data.get("value", []):
            if "deleted" in item:
                log.info(f"  Deleted on OneDrive (skipping): {item.get('name', item['id'])}")
                continue
            if "file" in item:
                files.append(item)
        url = data.get("@odata.nextLink")
        new_delta = data.get("@odata.deltaLink")
        if new_delta:
            delta_state["delta_link"] = new_delta

    DELTA_STATE_PATH.parent.mkdir(exist_ok=True)
    DELTA_STATE_PATH.write_text(json.dumps(delta_state, indent=2))
    log.info(f"OneDrive: {len(files)} file(s) to sync")
    return files

def download_file(token, item):
    download_url = item.get("@microsoft.graph.downloadUrl")
    if not download_url:
        download_url = f"{GRAPH_API}/me/drive/items/{item['id']}/content"
    r = requests.get(download_url, headers={"Authorization": f"Bearer {token}"}, stream=True)
    # If 401, silently refresh token and retry once
    if r.status_code == 401:
        log.warning("Token expired mid-sync -- refreshing token and retrying")
        token = _get_ms_token()
        r = requests.get(download_url, headers={"Authorization": f"Bearer {token}"}, stream=True)
    r.raise_for_status()
    return r.content, token

def upload_to_gcs(data, filename, item, dry_run):
    # Preserve OneDrive path structure using parentReference
    parent_path = item.get("parentReference", {}).get("path", "").split("root:")[-1].strip("/")
    gcs_path = f"onedrive-mirror/{parent_path}/{filename}" if parent_path else f"onedrive-mirror/{filename}"
    uri = f"gs://{GCS_BUCKET_NAME}/{gcs_path}"
    if dry_run:
        log.info(f"  [dry-run] Would upload -> {uri}")
        return uri
    client = storage.Client(project=GCP_PROJECT_ID)
    bucket = client.bucket(GCS_BUCKET_NAME)
    bucket.blob(gcs_path).upload_from_string(data)
    log.info(f"  Uploaded -> {uri}")
    return uri

# Searchable document types for Vertex AI Search
_SEARCHABLE_EXTS = ('.pdf', '.docx', '.doc', '.xlsx', '.xls', '.csv', '.txt', '.pptx')
_MIME_MAP = {
    '.pdf':  'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.doc':  'application/msword',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xls':  'application/vnd.ms-excel',
    '.csv':  'text/csv',
    '.txt':  'text/plain',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}


def _make_doc_id(blob_name: str) -> str:
    """Sanitize a GCS blob path into a valid Vertex document ID.
    Vertex requires: [a-zA-Z0-9-_]* only.
    """
    import re
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', blob_name)
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean[:128]


def _build_and_upload_manifest(dry_run: bool) -> str | None:
    """Scan GCS bucket for searchable documents, build a JSONL manifest,
    upload it, and return the GCS URI of the manifest.
    Skips images and other non-indexable file types.
    """
    if dry_run:
        log.info("  [dry-run] Would build and upload Vertex import manifest")
        return None

    import google.auth
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    gcs_client = storage.Client(project=GCP_PROJECT_ID, credentials=creds)
    bucket = gcs_client.bucket(GCS_BUCKET_NAME)

    lines = []
    seen_ids: set[str] = set()
    count = 0

    for blob in bucket.list_blobs(prefix="onedrive-mirror/"):
        name_lower = blob.name.lower()
        ext = next((e for e in _SEARCHABLE_EXTS if name_lower.endswith(e)), None)
        if not ext:
            continue
        uri = f"gs://{GCS_BUCKET_NAME}/{blob.name}"
        doc_id = _make_doc_id(blob.name)
        if doc_id in seen_ids:
            doc_id = f"{doc_id[:120]}_{len(seen_ids)}"
        seen_ids.add(doc_id)
        lines.append(json.dumps({
            "id": doc_id,
            "jsonData": json.dumps({
                "title": blob.name.split("/")[-1],
                "source_uri": uri,
            }),
            "content": {
                "mimeType": _MIME_MAP.get(ext, "application/pdf"),
                "uri": uri,
            },
        }))
        count += 1

    manifest_path = "manifests/import_manifest_latest.jsonl"
    bucket.blob(manifest_path).upload_from_string("\n".join(lines))
    manifest_uri = f"gs://{GCS_BUCKET_NAME}/{manifest_path}"
    log.info(f"Manifest built: {count} searchable documents -> {manifest_uri}")
    return manifest_uri


def trigger_vertex_import(dry_run):
    if not VERTEX_DATASTORE or not GCP_PROJECT_ID:
        log.warning("VERTEX_DATASTORE_ID or GCP_PROJECT_ID not set -- skipping Vertex import")
        return

    manifest_uri = _build_and_upload_manifest(dry_run)
    if dry_run:
        return

    url = (
        f"https://discoveryengine.googleapis.com/v1alpha/projects/{GCP_PROJECT_ID}"
        f"/locations/{VERTEX_LOCATION}/collections/default_collection"
        f"/dataStores/{VERTEX_DATASTORE}/branches/0/documents:import"
    )
    body = {
        "gcsSource": {
            "inputUris": [manifest_uri],
            "dataSchema": "document",
        },
        "reconciliationMode": "FULL",
    }
    token = _get_gcp_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Goog-User-Project": GCP_PROJECT_ID,
        "Content-Type": "application/json",
    }
    r = requests.post(url, headers=headers, json=body)
    if r.status_code == 200:
        log.info(f"Vertex import triggered. Operation: {r.json().get('name', '')}")
    else:
        log.error(f"Vertex import failed: {r.status_code} {r.text}")

def run_sync(dry_run=False, force=False):
    log.info("=" * 50)
    log.info(f"OneDrive sync started -- dry_run={dry_run}, force={force}")
    log.info("=" * 50)
    ms_token = _get_ms_token()
    files = list_onedrive_files(ms_token, force=force)
    if not files:
        log.info("No files to sync.")
        return
    uploaded = errors = 0
    for item in files:
        name = item["name"]
        size_kb = item.get("size", 0) // 1024
        log.info(f"Syncing: {name}  ({size_kb} KB)")
        try:
            if not dry_run:
                data, ms_token = download_file(ms_token, item)
                upload_to_gcs(data, name, item, dry_run=False)
            else:
                upload_to_gcs(b"", name, item, dry_run=True)
            uploaded += 1
        except Exception as e:
            log.error(f"  Failed: {name} -- {e}")
            errors += 1
    log.info(f"Sync complete: {uploaded} uploaded, {errors} errors")
    if uploaded > 0:
        trigger_vertex_import(dry_run=dry_run)
    log.info("=" * 50)

def run_scheduled(interval_minutes):
    log.info(f"Scheduled mode: syncing every {interval_minutes} minute(s). Ctrl+C to stop.")
    while True:
        try:
            run_sync()
        except Exception as e:
            log.error(f"Sync cycle failed: {e}")
            if "auth" in str(e).lower() or "token" in str(e).lower():
                log.error("TOKEN ERROR -- run bootstrap_onedrive.py to re-authenticate.")
        log.info(f"Next sync in {interval_minutes} minute(s)...")
        time.sleep(interval_minutes * 60)

def main():
    parser = argparse.ArgumentParser(description="OneDrive -> GCS -> Vertex AI Search sync")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--force",    action="store_true")
    parser.add_argument("--schedule", type=int, metavar="MINUTES")
    args = parser.parse_args()
    if args.schedule:
        run_scheduled(args.schedule)
    else:
        run_sync(dry_run=args.dry_run, force=args.force)

if __name__ == "__main__":
    main()

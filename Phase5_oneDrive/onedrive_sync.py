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
  python onedrive_sync.py --schedule 30 # loop every 30 minutes (Task Scheduler target)

# ============================================================
# SCALE-TODO (switch before production / multi-client use)
# ============================================================
# Current auth: MSAL delegated device-code flow with a local
# token cache (secrets/token_cache.json).
#
# Refresh tokens expire after 90 days of inactivity (sooner if
# your Azure AD policy enforces shorter rotation).  When they
# expire the scheduled job will halt and log an auth error.
#
# Production fix — switch to client_credentials:
#   1. In Azure Portal → App registrations → your app
#      → API permissions → Add "Files.Read.All" as an
#      APPLICATION permission (not delegated) → Grant admin consent
#   2. Create a client secret → copy to secrets/.env as
#      AZURE_CLIENT_SECRET
#   3. Replace _get_token() below with:
#        app = msal.ConfidentialClientApplication(
#            AZURE_CLIENT_ID,
#            authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}",
#            client_credential=AZURE_CLIENT_SECRET,
#        )
#        result = app.acquire_token_for_client(
#            scopes=["https://graph.microsoft.com/.default"]
#        )
#   4. Delete secrets/token_cache.json — no longer needed
#   5. Remove the device-code flow entirely
# ============================================================
"""

import os
import sys
import json
import time
import logging
import argparse
import tempfile
import requests
import msal
from datetime import datetime, timezone
from pathlib import Path
from google.cloud import storage
from google.oauth2 import credentials as google_credentials
import google.auth
import google.auth.transport.requests

# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------
def _load_env():
    from dotenv import load_dotenv
    candidates = [
        os.environ.get("VERTEX_ENV_FILE"),
        Path(__file__).parent / "secrets" / ".env",
        Path.cwd() / "Phase5_OneDrive" / "secrets" / ".env",
        Path.cwd() / ".env",
    ]
    for c in candidates:
        if c and Path(c).exists():
            load_dotenv(c)
            return

_load_env()

AZURE_CLIENT_ID    = os.environ.get("AZURE_CLIENT_ID", "")
AZURE_TENANT_ID    = os.environ.get("AZURE_TENANT_ID", "")
ONEDRIVE_FOLDER_PATH = os.environ.get("ONEDRIVE_FOLDER_PATH", "")
GCP_PROJECT_ID     = os.environ.get("GCP_PROJECT_ID", "")
GCS_BUCKET_NAME    = os.environ.get("GCS_BUCKET_NAME", "")
VERTEX_LOCATION    = os.environ.get("VERTEX_LOCATION", "global")
VERTEX_DATASTORE   = os.environ.get("VERTEX_DATASTORE_ID", "")

SCOPES             = ["Files.Read", "offline_access"]
TOKEN_CACHE_PATH   = Path(__file__).parent / "secrets" / "token_cache.json"
DELTA_STATE_PATH   = Path(__file__).parent / "secrets" / "delta_state.json"
GRAPH_API          = "https://graph.microsoft.com/v1.0"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("onedrive_sync")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _get_ms_token() -> str:
    """
    Acquire a Microsoft Graph access token.
    Uses cached refresh token if available; otherwise triggers device-code flow.
    """
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
        log.warning("Cached token unavailable or expired — starting device-code flow")
        print("\n" + "="*60)
        print("  ACTION REQUIRED — Microsoft sign-in needed")
        print("="*60)
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Device flow failed: {flow.get('error_description')}")
        print(f"  1. Open:       {flow['verification_uri']}")
        print(f"  2. Enter code: {flow['user_code']}")
        print("  3. Sign in with the OneDrive account")
        print("="*60 + "\n")
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(
            f"Microsoft auth failed: {result.get('error_description', result)}\n"
            "SCALE-TODO: If running as a scheduled task, token may have expired.\n"
            "Switch to client_credentials (see SCALE-TODO at top of file)."
        )

    TOKEN_CACHE_PATH.parent.mkdir(exist_ok=True)
    TOKEN_CACHE_PATH.write_text(cache.serialize())
    return result["access_token"]


def _get_gcp_token() -> str:
    """Get a GCP bearer token for Vertex AI Search REST calls."""
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token

# ---------------------------------------------------------------------------
# OneDrive helpers
# ---------------------------------------------------------------------------
def _graph_get(token: str, url: str) -> dict:
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


def list_onedrive_files(token: str, force: bool) -> list[dict]:
    """
    Return list of file items from the OneDrive folder.
    Uses delta link for incremental syncs; full listing on --force.
    """
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
        # Path-based endpoint — no folder ID needed
        url = f"{GRAPH_API}/me/drive/root:/{ONEDRIVE_FOLDER_PATH}:/delta"

    while url:
        data = _graph_get(token, url)
        for item in data.get("value", []):
            # Skip deleted items (no "file" key, but have "deleted")
            if "deleted" in item:
                log.info(f"  Deleted on OneDrive (skipping): {item.get('name', item['id'])}")
                continue
            if "file" in item:
                files.append(item)
        url = data.get("@odata.nextLink")
        new_delta = data.get("@odata.deltaLink")
        if new_delta:
            delta_state["delta_link"] = new_delta

    # Persist updated delta link
    DELTA_STATE_PATH.parent.mkdir(exist_ok=True)
    DELTA_STATE_PATH.write_text(json.dumps(delta_state, indent=2))
    log.info(f"OneDrive: {len(files)} file(s) to sync")
    return files


def download_file(token: str, item: dict) -> bytes:
    """Download a OneDrive file item and return raw bytes."""
    download_url = item.get("@microsoft.graph.downloadUrl")
    if not download_url:
        # Fall back to content endpoint
        download_url = f"{GRAPH_API}/me/drive/items/{item['id']}/content"
    r = requests.get(download_url, headers={"Authorization": f"Bearer {token}"}, stream=True)
    r.raise_for_status()
    return r.content

# ---------------------------------------------------------------------------
# GCS helpers
# ---------------------------------------------------------------------------
def upload_to_gcs(data: bytes, filename: str, dry_run: bool) -> str:
    """Upload bytes to GCS bucket. Returns gs:// URI."""
    gcs_path = f"onedrive-mirror/{filename}"
    uri = f"gs://{GCS_BUCKET_NAME}/{gcs_path}"
    if dry_run:
        log.info(f"  [dry-run] Would upload → {uri}")
        return uri
    client = storage.Client(project=GCP_PROJECT_ID)
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(gcs_path)
    blob.upload_from_string(data)
    log.info(f"  Uploaded → {uri}")
    return uri

# ---------------------------------------------------------------------------
# Vertex AI Search re-import
# ---------------------------------------------------------------------------
def trigger_vertex_import(dry_run: bool):
    """
    Trigger a Vertex AI Search document import from the GCS bucket prefix
    where OneDrive files are mirrored.
    Uses the same v1alpha REST pattern as Phase 3.
    """
    if not VERTEX_DATASTORE or not GCP_PROJECT_ID:
        log.warning("VERTEX_DATASTORE_ID or GCP_PROJECT_ID not set — skipping Vertex import")
        return

    gcs_uri = f"gs://{GCS_BUCKET_NAME}/onedrive-mirror/"
    url = (
        f"https://discoveryengine.googleapis.com/v1alpha/projects/{GCP_PROJECT_ID}"
        f"/locations/{VERTEX_LOCATION}/collections/default_collection"
        f"/dataStores/{VERTEX_DATASTORE}/branches/0/documents:import"
    )
    body = {
        "gcsSource": {
            "inputUris": [gcs_uri],
            "dataSchema": "document",
        },
        "reconciliationMode": "INCREMENTAL",
    }

    if dry_run:
        log.info(f"  [dry-run] Would POST Vertex import: {gcs_uri}")
        return

    token = _get_gcp_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Goog-User-Project": GCP_PROJECT_ID,
        "Content-Type": "application/json",
    }
    r = requests.post(url, headers=headers, json=body)
    if r.status_code == 200:
        op = r.json().get("name", "")
        log.info(f"Vertex import triggered. Operation: {op}")
    else:
        log.error(f"Vertex import failed: {r.status_code} {r.text}")

# ---------------------------------------------------------------------------
# Core sync
# ---------------------------------------------------------------------------
def run_sync(dry_run: bool = False, force: bool = False):
    log.info("=" * 50)
    log.info(f"OneDrive sync started — dry_run={dry_run}, force={force}")
    log.info("=" * 50)

    ms_token = _get_ms_token()
    files = list_onedrive_files(ms_token, force=force)

    if not files:
        log.info("No files to sync.")
        return

    uploaded = 0
    errors = 0

    for item in files:
        name = item["name"]
        size_kb = item.get("size", 0) // 1024
        modified = item.get("lastModifiedDateTime", "unknown")
        log.info(f"Syncing: {name}  ({size_kb} KB)  modified={modified}")

        try:
            if not dry_run:
                data = download_file(ms_token, item)
                upload_to_gcs(data, name, dry_run=False)
            else:
                upload_to_gcs(b"", name, dry_run=True)
            uploaded += 1
        except Exception as e:
            log.error(f"  Failed: {name} — {e}")
            errors += 1

    log.info(f"Sync complete: {uploaded} uploaded, {errors} errors")

    if uploaded > 0:
        trigger_vertex_import(dry_run=dry_run)

    log.info("=" * 50)


# ---------------------------------------------------------------------------
# Scheduled loop
# ---------------------------------------------------------------------------
def run_scheduled(interval_minutes: int):
    log.info(f"Scheduled mode: syncing every {interval_minutes} minute(s). Ctrl+C to stop.")
    while True:
        try:
            run_sync()
        except Exception as e:
            log.error(f"Sync cycle failed: {e}")
            # Auth errors get a louder warning
            if "auth" in str(e).lower() or "token" in str(e).lower():
                log.error(
                    "TOKEN ERROR in scheduled run. Refresh token may have expired.\n"
                    "Run bootstrap_onedrive.py interactively to re-authenticate, or\n"
                    "switch to client_credentials (see SCALE-TODO at top of file)."
                )
        next_run = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        log.info(f"Next sync in {interval_minutes} minute(s)...")
        time.sleep(interval_minutes * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="OneDrive → GCS → Vertex AI Search sync")
    parser.add_argument("--dry-run",  action="store_true", help="List what would sync, no writes")
    parser.add_argument("--force",    action="store_true", help="Full re-sync, ignore delta state")
    parser.add_argument("--schedule", type=int, metavar="MINUTES",
                        help="Loop and sync every N minutes (for Task Scheduler)")
    args = parser.parse_args()

    if args.schedule:
        run_scheduled(args.schedule)
    else:
        run_sync(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()

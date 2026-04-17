"""
Ensure GCS buckets exist, with automatic collision recovery.

GCS bucket names are globally unique across ALL of GCP. If the bootstrap
picks a name that's already taken (including during the 7-day deletion
reservation window after a teardown), the bucket is never created and
every subsequent upload fails with a misleading 403 ('permission denied
on resource OR IT MAY NOT EXIST').

This utility:
  1. Reads the bucket names from .env
  2. Checks if each bucket exists (and is owned by us)
  3. If missing OR the name is globally taken, retries with a
     `-{project_number}` suffix (guaranteed unique per GCP project)
  4. Rewrites .env with the resolved names

Run this if you hit 'storage.objects.create denied' errors and
scripts/diagnose.py confirms the bucket is 404.

Usage:
    python scripts/ensure_gcs_buckets.py

Env discovery: $VERTEX_ENV_FILE > <cwd>/Phase3_Bootstrap/secrets/.env >
               <cwd>/.env > <repo>/Phase3_Bootstrap/secrets/.env
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import load_or_die  # noqa: E402

from google.api_core import exceptions as gax  # noqa: E402
from google.cloud import storage  # noqa: E402
from google.oauth2 import service_account  # noqa: E402


def ensure_bucket(
    client: storage.Client,
    name: str,
    location: str,
    project_number: str,
) -> str:
    """Ensure a bucket exists. Returns the (possibly renamed) resolved name."""
    candidates = [name]
    if not name.endswith(project_number):
        candidates.append(f"{name}-{project_number}")

    for candidate in candidates:
        bucket = client.bucket(candidate)
        try:
            bucket.reload()
            print(f"   ✓ Exists: gs://{candidate}")
            return candidate
        except gax.NotFound:
            pass
        except gax.Forbidden:
            # Someone else owns this name. Fall through to the next candidate.
            print(f"   ⚠ Taken globally (403): gs://{candidate}")
            continue

        try:
            bucket = client.create_bucket(candidate, location=location)
            bucket.iam_configuration.uniform_bucket_level_access_enabled = True
            bucket.patch()
            print(f"   ✓ Created: gs://{candidate}")
            return candidate
        except gax.Conflict:
            print(f"   ⚠ Name taken globally (409): gs://{candidate}")
            continue

    print(f"   ✗ Could not create bucket with any of: {candidates}")
    sys.exit(1)


def main() -> int:
    env_path, sa_key = load_or_die()

    project_id = os.getenv("GCP_PROJECT_ID")
    project_number = os.getenv("GCP_PROJECT_NUMBER")
    region = os.getenv("GCP_REGION", "us-east1")
    bucket_raw = os.getenv("GCS_BUCKET_RAW", "")
    bucket_processed = os.getenv("GCS_BUCKET_PROCESSED", "")

    if not (project_id and project_number):
        print("✗ GCP_PROJECT_ID and GCP_PROJECT_NUMBER must be set in .env")
        print(f"  loaded from: {env_path}")
        return 1

    creds = service_account.Credentials.from_service_account_file(
        str(sa_key), scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    client = storage.Client(project=project_id, credentials=creds)

    print(f"Ensuring GCS buckets for project {project_id}")
    print(f"  Region: {region}\n")

    resolved_raw = (
        ensure_bucket(client, bucket_raw, region, project_number)
        if bucket_raw else ""
    )
    resolved_processed = (
        ensure_bucket(client, bucket_processed, region, project_number)
        if bucket_processed else ""
    )

    # Rewrite .env only if any name changed
    changed = (
        (resolved_raw and resolved_raw != bucket_raw)
        or (resolved_processed and resolved_processed != bucket_processed)
    )
    if changed:
        print(f"\n📝 Updating .env with resolved bucket names...")
        lines = env_path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            if line.startswith("GCS_BUCKET_RAW=") and resolved_raw:
                out.append(f'GCS_BUCKET_RAW="{resolved_raw}"')
            elif line.startswith("GCS_BUCKET_PROCESSED=") and resolved_processed:
                out.append(f'GCS_BUCKET_PROCESSED="{resolved_processed}"')
            else:
                out.append(line)
        env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"   ✓ .env updated at {env_path}")

    print(f"\n✅ Buckets ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())

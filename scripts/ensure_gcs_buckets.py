"""
Ensure GCS buckets exist, with automatic collision recovery.

GCS bucket names are globally unique across ALL of GCP. If the bootstrap picks
a name that's already taken (including during the 7-day deletion reservation
window after teardown), the bucket is never created and every subsequent
upload fails with a misleading 403 ('permission denied on resource OR IT MAY
NOT EXIST').

This utility:
  1. Reads the bucket names from .env
  2. Checks if each bucket exists
  3. If missing OR the name is globally taken, re-creates it with a
     project-number suffix (guaranteed unique per GCP project)
  4. Rewrites .env with the resolved names

Run this if you hit 'storage.objects.create denied' errors and
scripts/diagnose.py confirms the bucket is 404.

Usage (from repo root):
    python scripts/ensure_gcs_buckets.py
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.api_core import exceptions as gax
from google.cloud import storage
from google.oauth2 import service_account


def ensure_bucket(client: storage.Client, name: str, location: str, project_number: str) -> str:
    """Ensure a bucket exists. Returns the (possibly renamed) resolved name."""
    candidates = [name]
    # If name doesn't already end in the project number, plan a fallback that does
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

        try:
            bucket = client.create_bucket(
                candidate,
                location=location,
            )
            # Enforce uniform bucket-level access — required for simple IAM
            bucket.iam_configuration.uniform_bucket_level_access_enabled = True
            bucket.patch()
            print(f"   ✓ Created: gs://{candidate}")
            return candidate
        except gax.Conflict:
            print(f"   ⚠ Name taken globally: gs://{candidate}")
            continue

    print(f"   ✗ Could not create bucket with any of: {candidates}")
    sys.exit(1)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / "Phase3_Bootstrap" / "secrets" / ".env"
    sa_key = repo_root / "Phase3_Bootstrap" / "secrets" / "service-account.json"

    if not env_path.exists():
        print(f"✗ Missing .env at {env_path}")
        return 1

    load_dotenv(env_path)
    project_id = os.getenv("GCP_PROJECT_ID")
    project_number = os.getenv("GCP_PROJECT_NUMBER")
    region = os.getenv("GCP_REGION", "us-east1")
    bucket_raw = os.getenv("GCS_BUCKET_RAW", "")
    bucket_processed = os.getenv("GCS_BUCKET_PROCESSED", "")

    if not (project_id and project_number):
        print("✗ GCP_PROJECT_ID and GCP_PROJECT_NUMBER must be set")
        return 1

    creds = service_account.Credentials.from_service_account_file(
        str(sa_key), scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    client = storage.Client(project=project_id, credentials=creds)

    print(f"Ensuring GCS buckets for project {project_id}")
    print(f"  Region: {region}\n")

    resolved_raw = ensure_bucket(client, bucket_raw, region, project_number) if bucket_raw else ""
    resolved_processed = ensure_bucket(client, bucket_processed, region, project_number) if bucket_processed else ""

    # Rewrite .env only if names changed
    if (resolved_raw and resolved_raw != bucket_raw) or (resolved_processed and resolved_processed != bucket_processed):
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
        print(f"   ✓ .env updated")

    print(f"\n✅ Buckets ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())

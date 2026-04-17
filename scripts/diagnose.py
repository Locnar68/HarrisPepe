"""
Diagnose Vertex AI Search deployment issues.

Run this FIRST when something doesn't work. It pinpoints whether the problem is:
  - Service account key mismatch
  - Bucket that doesn't actually exist (common after global-name collision)
  - Missing IAM bindings at project OR bucket level
  - Data store / engine config issues

Usage (from repo root):
    python scripts/diagnose.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


def run(args: list[str]) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, shell=True, timeout=30)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / "Phase3_Bootstrap" / "secrets" / ".env"
    sa_key = repo_root / "Phase3_Bootstrap" / "secrets" / "service-account.json"

    if not env_path.exists() or not sa_key.exists():
        print(f"✗ Missing .env or service-account.json in Phase3_Bootstrap/secrets/")
        return 1

    load_dotenv(env_path)
    project_id = os.getenv("GCP_PROJECT_ID")
    bucket_raw = os.getenv("GCS_BUCKET_RAW")
    bucket_processed = os.getenv("GCS_BUCKET_PROCESSED", "")
    data_store_id = os.getenv("VERTEX_DATA_STORE_ID")
    engine_id = os.getenv("VERTEX_ENGINE_ID")

    # --- Step 1: Verify SA key file ---
    section("STEP 1: Service account key file")
    with open(sa_key) as f:
        sa = json.load(f)
    sa_email = sa["client_email"]
    print(f"  client_email:   {sa_email}")
    print(f"  project_id:     {sa['project_id']}")
    print(f"  private_key_id: {sa['private_key_id'][:16]}...")
    if sa["project_id"] != project_id:
        print(f"  ⚠ MISMATCH: SA project ({sa['project_id']}) != env project ({project_id})")

    # --- Step 2: Bucket existence ---
    section("STEP 2: GCS buckets")
    for name in [bucket_raw, bucket_processed]:
        if not name:
            continue
        rc, out, err = run(["gcloud", "storage", "buckets", "describe", f"gs://{name}",
                           f"--project={project_id}", "--format=value(name,location)"])
        if rc == 0:
            print(f"  ✓ gs://{name}  →  {out.strip()}")
        else:
            if "404" in err or "not found" in err.lower():
                print(f"  ✗ gs://{name}  →  DOES NOT EXIST")
                print(f"     Fix: python scripts/ensure_gcs_buckets.py")
            else:
                print(f"  ✗ gs://{name}  →  {err.strip()}")

    # --- Step 3: Bucket IAM ---
    section("STEP 3: Bucket-level IAM (for raw bucket)")
    if bucket_raw:
        rc, out, err = run(["gcloud", "storage", "buckets", "get-iam-policy", f"gs://{bucket_raw}",
                           f"--project={project_id}", "--format=json"])
        if rc == 0:
            policy = json.loads(out)
            found_sa = False
            for b in policy.get("bindings", []):
                for m in b.get("members", []):
                    if sa_email in m:
                        print(f"  ✓ SA has {b['role']} on bucket")
                        found_sa = True
            if not found_sa:
                print(f"  ℹ SA has no bucket-level bindings (may be OK if project-level storage.admin is granted)")
        else:
            print(f"  — skipped (bucket may not exist)")

    # --- Step 4: Project IAM for SA ---
    section("STEP 4: Project-level IAM for the service account")
    rc, out, err = run(["gcloud", "projects", "get-iam-policy", project_id,
                       "--flatten=bindings[].members",
                       f"--filter=bindings.members:{sa_email}",
                       "--format=value(bindings.role)"])
    if rc == 0:
        roles = [r for r in out.strip().split("\n") if r]
        print(f"  SA has {len(roles)} project-level roles:")
        for r in roles:
            print(f"    - {r}")
        required = {"roles/storage.admin", "roles/discoveryengine.admin", "roles/aiplatform.user"}
        missing = required - set(roles)
        if missing:
            print(f"\n  ⚠ Missing recommended roles: {missing}")
            for role in missing:
                print(f"    gcloud projects add-iam-policy-binding {project_id} \\")
                print(f"      --member=serviceAccount:{sa_email} --role={role}")
    else:
        print(f"  ✗ {err.strip()}")

    # --- Step 5: Data store & engine ---
    section("STEP 5: Vertex AI Search data store & engine")
    if data_store_id:
        rc, out, err = run(["gcloud", "alpha", "discovery-engine", "data-stores", "describe",
                           data_store_id, f"--project={project_id}", "--location=global",
                           "--format=value(name)"])
        if rc == 0:
            print(f"  ✓ Data store exists: {data_store_id}")
        else:
            # The gcloud alpha command may not exist; try REST
            print(f"  ℹ gcloud check inconclusive — verify via: python scripts/check_index.py")
    if engine_id:
        print(f"  ℹ Engine ID from .env: {engine_id}")
        print(f"     Verify search works with: python scripts/test_rag.py")

    print()
    print("=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("  - If buckets missing:      python scripts/ensure_gcs_buckets.py")
    print("  - If docs not indexed:     python scripts/manual_sync.py")
    print("  - If indexed but no hits:  python scripts/check_index.py")
    print("  - If UI says OFFLINE:      python scripts/test_rag.py  (verifies API works)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

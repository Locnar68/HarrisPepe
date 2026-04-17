"""GCS bucket creation with lifecycle rules."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from installer.config.schema import Phase3Config
from installer.utils import shell, ui

log = logging.getLogger(__name__)


def ensure_buckets(cfg: Phase3Config, *, dry_run: bool = False) -> None:
    ui.section("Step 8 — GCS buckets",
               "Creating raw / processed / (optional) archive buckets.")

    project = cfg.gcp.project_id
    region = cfg.gcp.region
    sclass = cfg.storage.storage_class

    for name in (cfg.storage.raw_bucket, cfg.storage.processed_bucket,
                 cfg.storage.archive_bucket):
        if not name:
            continue
        _create_bucket(project, region, sclass, name, dry_run=dry_run)
        _enable_uniform_access(name, dry_run=dry_run)
        _enable_versioning(name, dry_run=dry_run)

    # Lifecycle: raw -> archive after N days
    if (cfg.storage.archive_bucket and cfg.storage.lifecycle_days_to_archive > 0):
        _apply_lifecycle(
            bucket=cfg.storage.raw_bucket,
            days=cfg.storage.lifecycle_days_to_archive,
            archive_class="ARCHIVE",
            dry_run=dry_run,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_bucket(
    project: str,
    region: str,
    sclass: str,
    name: str,
    *,
    dry_run: bool,
) -> None:
    # Check existence first
    res = shell.run(
        ["gcloud", "storage", "buckets", "describe", f"gs://{name}",
         f"--project={project}"],
        check=False, timeout=30, dry_run=dry_run,
    )
    if not dry_run and res.ok:
        ui.success(f"bucket exists: gs://{name}")
        return

    res = shell.run(
        ["gcloud", "storage", "buckets", "create", f"gs://{name}",
         f"--project={project}",
         f"--location={region}",
         f"--default-storage-class={sclass}",
         "--uniform-bucket-level-access"],
        check=False, timeout=120, dry_run=dry_run,
    )
    if dry_run:
        ui.note(f"[dry-run] would create gs://{name}")
        return
    
    # Check if creation failed
    if not res.ok:
        err_text = (res.stderr or "").lower()
        # Bucket already exists = success (409 conflict or "already exists" message)
        if "already exists" in err_text or "409" in err_text or "not available" in err_text:
            ui.success(f"bucket exists: gs://{name}")
            return
        # Real error
        raise RuntimeError(f"Failed to create bucket {name}: {res.stderr}")
    
    ui.success(f"bucket created: gs://{name}")


def _enable_uniform_access(name: str, *, dry_run: bool) -> None:
    shell.run(
        ["gcloud", "storage", "buckets", "update", f"gs://{name}",
         "--uniform-bucket-level-access"],
        check=False, timeout=30, dry_run=dry_run,
    )


def _enable_versioning(name: str, *, dry_run: bool) -> None:
    shell.run(
        ["gcloud", "storage", "buckets", "update", f"gs://{name}",
         "--versioning"],
        check=False, timeout=30, dry_run=dry_run,
    )


def _apply_lifecycle(
    *,
    bucket: str,
    days: int,
    archive_class: str,
    dry_run: bool,
) -> None:
    policy = {
        "lifecycle": {
            "rule": [{
                "action": {"type": "SetStorageClass", "storageClass": archive_class},
                "condition": {"age": days},
            }],
        },
    }

    if dry_run:
        ui.note(f"[dry-run] would apply lifecycle rule: age>{days}d -> {archive_class} "
                f"on gs://{bucket}")
        return

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(policy, f)
        policy_path = f.name

    try:
        res = shell.run(
            ["gcloud", "storage", "buckets", "update", f"gs://{bucket}",
             f"--lifecycle-file={policy_path}"],
            check=False, timeout=60,
        )
        if res.ok:
            ui.success(f"lifecycle applied: gs://{bucket} (age>{days}d -> {archive_class})")
        else:
            ui.warn(f"lifecycle apply failed: {res.stderr.strip()[:200]}")
    finally:
        Path(policy_path).unlink(missing_ok=True)

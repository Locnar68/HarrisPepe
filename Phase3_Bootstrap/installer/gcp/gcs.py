"""GCS bucket creation with lifecycle rules.

Collision-safe: when a requested bucket name is already taken globally by
another project, we auto-retry with a `-{project_number}` suffix and mutate
the config so every downstream step uses the real (created) bucket name.

This replaces the old behavior of treating a 409 on `create` as "bucket
exists, it's ours" — which silently broke the pipeline whenever the name
was actually owned by someone else.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from installer.config.schema import Phase3Config
from installer.utils import shell, ui

log = logging.getLogger(__name__)

MAX_COLLISION_RETRIES = 3
_COLLISION_MARKERS = (
    "already exists",
    "409",
    "not available",
    "conflict",
    "already-exists",
    "bucket name not available",
    "bucket you tried to create is a reserved",
)


def ensure_buckets(cfg: Phase3Config, *, dry_run: bool = False) -> None:
    ui.section("Step 8 — GCS buckets",
               "Creating raw / processed / (optional) archive buckets.")

    project = cfg.gcp.project_id
    region = cfg.gcp.region
    sclass = cfg.storage.storage_class
    # project_number is populated by the earlier `projects` step; fall back
    # to project_id for the (rare) case where it isn't available yet.
    project_number = cfg.gcp.project_number or project

    # (attribute-on-cfg.storage, requested_name)
    slots = [
        ("raw_bucket", cfg.storage.raw_bucket),
        ("processed_bucket", cfg.storage.processed_bucket),
        ("archive_bucket", cfg.storage.archive_bucket),
    ]

    for attr, requested in slots:
        if not requested:
            continue
        final_name = _create_bucket_with_retry(
            project=project,
            project_number=project_number,
            region=region,
            sclass=sclass,
            requested_name=requested,
            dry_run=dry_run,
        )
        if final_name != requested and not dry_run:
            ui.warn(
                f"Bucket name '{requested}' was taken globally. "
                f"Using '{final_name}' instead (config will be updated)."
            )
            setattr(cfg.storage, attr, final_name)
        _enable_uniform_access(final_name, dry_run=dry_run)
        _enable_versioning(final_name, dry_run=dry_run)

    # Lifecycle: raw -> archive after N days
    if (cfg.storage.archive_bucket and cfg.storage.lifecycle_days_to_archive > 0):
        _apply_lifecycle(
            bucket=cfg.storage.raw_bucket,
            days=cfg.storage.lifecycle_days_to_archive,
            archive_class="ARCHIVE",
            dry_run=dry_run,
        )


# ---------------------------------------------------------------------------
# Creation helpers
# ---------------------------------------------------------------------------

def _create_bucket_with_retry(
    *,
    project: str,
    project_number: str,
    region: str,
    sclass: str,
    requested_name: str,
    dry_run: bool,
) -> str:
    """Create the bucket, auto-retrying with a project-number suffix on
    global-name collisions. Returns the actual bucket name that was
    created (or confirmed as ours)."""
    candidate = requested_name
    last_error: str = ""
    for attempt in range(MAX_COLLISION_RETRIES + 1):
        status, err = _try_create_bucket(
            project=project,
            region=region,
            sclass=sclass,
            name=candidate,
            dry_run=dry_run,
        )
        if status in ("ours", "created"):
            return candidate
        last_error = err
        # collision — pick a new candidate and try again
        if attempt == 0:
            candidate = f"{requested_name}-{project_number}"
        else:
            candidate = f"{requested_name}-{project_number}-{attempt + 1}"
        ui.note(f"Global-name collision — retrying with 'gs://{candidate}'")

    raise RuntimeError(
        f"Could not create a bucket after {MAX_COLLISION_RETRIES + 1} "
        f"attempts (last tried gs://{candidate}).\n"
        f"Last error: {last_error}"
    )


def _try_create_bucket(
    *,
    project: str,
    region: str,
    sclass: str,
    name: str,
    dry_run: bool,
) -> tuple[str, str]:
    """Attempt one bucket creation.

    Returns (status, error_text):
      - ("ours", "")       — bucket exists AND is owned by this project
      - ("created", "")    — bucket was just created successfully
      - ("collision", ...) — name is taken globally by someone else
    Raises RuntimeError on any other (unexpected) error.
    """
    # 1. Check if we already own it
    res = shell.run(
        ["gcloud", "storage", "buckets", "describe", f"gs://{name}",
         f"--project={project}"],
        check=False, timeout=30, dry_run=dry_run,
    )
    if dry_run:
        ui.note(f"[dry-run] would create gs://{name}")
        return ("created", "")
    if res.ok:
        ui.success(f"bucket exists (owned by this project): gs://{name}")
        return ("ours", "")

    # 2. Try to create
    res = shell.run(
        ["gcloud", "storage", "buckets", "create", f"gs://{name}",
         f"--project={project}",
         f"--location={region}",
         f"--default-storage-class={sclass}",
         "--uniform-bucket-level-access"],
        check=False, timeout=120, dry_run=dry_run,
    )
    if res.ok:
        ui.success(f"bucket created: gs://{name}")
        return ("created", "")

    err_text = (res.stderr or "")
    low = err_text.lower()
    if any(m in low for m in _COLLISION_MARKERS):
        # Could be a race where we created it between describe and create
        # on a parallel run, OR someone else owns it. Re-describe to
        # disambiguate.
        res2 = shell.run(
            ["gcloud", "storage", "buckets", "describe", f"gs://{name}",
             f"--project={project}"],
            check=False, timeout=30,
        )
        if res2.ok:
            ui.success(f"bucket exists (owned by this project): gs://{name}")
            return ("ours", "")
        return ("collision", err_text.strip()[:200])

    # Unknown error — surface it
    raise RuntimeError(f"Failed to create bucket {name}: {err_text}")


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

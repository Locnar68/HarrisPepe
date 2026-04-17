"""GCS storage interview."""

from __future__ import annotations

from installer.config.schema import BusinessConfig, GCPConfig, StorageConfig
from installer.utils import ui
from installer.validators import gcs_bucket_name


def run(business: BusinessConfig, gcp: GCPConfig) -> StorageConfig:
    ui.section(
        "2e — Storage (GCS)",
        "Two buckets are required: 'raw' for direct connector dumps, 'processed' "
        "for normalized docs.",
    )

    # Use project_id as bucket prefix. Project IDs are already globally unique
    # in GCP, so buckets derived from them inherit that uniqueness. This avoids
    # the common collision where `{display_name}-rag-raw` is already taken
    # globally by someone else's project (and the create silently succeeds as
    # "bucket exists" while actually pointing at a bucket we cannot write to).
    prefix = gcp.project_id
    raw_bucket = ui.ask_text(
        "Raw bucket name",
        default=f"{prefix}-rag-raw",
        help_text="Must be globally unique across all of GCS. 3–63 chars, "
                  "lowercase letters/digits/dashes/underscores/dots. "
                  "Prefixing with your project ID guarantees uniqueness.",
        validator=gcs_bucket_name,
    )
    processed_bucket = ui.ask_text(
        "Processed bucket name",
        default=f"{prefix}-rag-processed",
        validator=gcs_bucket_name,
    )

    storage_class = ui.ask_select(
        "Storage class for the raw/processed buckets",
        choices=["STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"],
        default="STANDARD",
    )

    # Archive bucket removed — always none
    archive_bucket = ""
    lifecycle_days = 0

    return StorageConfig(
        raw_bucket=raw_bucket,
        processed_bucket=processed_bucket,
        archive_bucket=archive_bucket,
        storage_class=storage_class,
        lifecycle_days_to_archive=lifecycle_days,
    )

"""GCS storage interview."""

from __future__ import annotations

from installer.config.schema import BusinessConfig, StorageConfig
from installer.utils import ui
from installer.validators import gcs_bucket_name


def run(business: BusinessConfig) -> StorageConfig:
    ui.section(
        "2e — Storage (GCS)",
        "Two buckets are required: 'raw' for direct connector dumps, 'processed' "
        "for normalized docs.",
    )

    prefix = business.display_name
    raw_bucket = ui.ask_text(
        "Raw bucket name",
        default=f"{prefix}-rag-raw",
        help_text="Must be globally unique across all of GCS. 3–63 chars, "
                  "lowercase letters/digits/dashes/underscores/dots.",
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

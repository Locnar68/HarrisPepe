"""Service account interview."""

from __future__ import annotations

from installer.config.schema import BusinessConfig, GCPConfig, ServiceAccountConfig
from installer.utils import ui
from installer.validators import sa_short_name


def run(business: BusinessConfig, gcp: GCPConfig) -> ServiceAccountConfig:
    ui.section(
        "2d — Service account",
        "A dedicated SA for the pipeline. It gets the minimum roles needed to "
        "manage GCS, Vertex AI Search, Secret Manager and Cloud Run.",
    )

    default_name = f"{business.display_name}-rag-sa"[:30]
    short = ui.ask_text(
        "SA short name (before @)",
        default=default_name,
        help_text="6–30 chars, lowercase letters/digits/hyphens. "
                  "Full email will be <short>@<project>.iam.gserviceaccount.com.",
        validator=sa_short_name,
    )

    display = ui.ask_text(
        "SA display name (shown in the console)",
        default=f"{business.display_name} RAG pipeline",
    )

    email = f"{short}@{gcp.project_id}.iam.gserviceaccount.com"
    ui.note(f"Full SA email will be: {email}")

    return ServiceAccountConfig(
        short_name=short,
        display_name=display,
        email=email,
    )

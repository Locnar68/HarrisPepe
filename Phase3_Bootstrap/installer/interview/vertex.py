"""
Vertex AI Search interview — minimal, only IDs.

Tier, content config, industry vertical, language, and Layout Parser are all
hardcoded. Only the data store ID and engine ID are prompted.
"""

from __future__ import annotations

from installer.config.schema import BusinessConfig, VertexConfig
from installer.utils import ui
from installer.validators import vertex_id


def run(business: BusinessConfig) -> VertexConfig:
    ui.section(
        "2f — Vertex AI Search",
        "The RAG brain. Tier=ENTERPRISE, Layout Parser=ON, content=CONTENT_REQUIRED, "
        "vertical=GENERIC, language=en — all hardcoded. You only pick IDs.",
    )

    prefix = business.display_name
    data_store_id = ui.ask_text(
        "Data store ID",
        default=f"{prefix}-ds-v1",
        help_text="Lowercase letters/digits/hyphens/underscores. "
                  "HARD RULE: if you need to re-create later, use -v2, -v3 — "
                  "deleted IDs are reserved for hours.",
        validator=vertex_id,
    )
    engine_id = ui.ask_text(
        "Engine ID",
        default=f"{prefix}-engine-v1",
        validator=vertex_id,
    )

    return VertexConfig(
        data_store_id=data_store_id,
        engine_id=engine_id,
        tier="ENTERPRISE",                     # static
        content_config="CONTENT_REQUIRED",     # static
        industry_vertical="GENERIC",           # static
        language_code="en",                    # static
        enable_layout_parser=True,             # static
    )

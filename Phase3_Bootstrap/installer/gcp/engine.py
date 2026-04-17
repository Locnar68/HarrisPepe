"""
Search engine creation.

The engine is what a client queries; it wraps one or more data stores and
controls the search behaviour (tier, company name for boosting, etc.).
"""

from __future__ import annotations

import logging

from installer.config.schema import Phase3Config
from installer.utils import http, ui

log = logging.getLogger(__name__)

DISCOVERY_HOST = "https://discoveryengine.googleapis.com"
API_VERSION = "v1alpha"


def ensure_engine(cfg: Phase3Config, *, dry_run: bool = False) -> None:
    ui.section(
        "Step 11 — Search engine",
        f"Creating engine '{cfg.vertex.engine_id}' bound to data store "
        f"'{cfg.vertex.data_store_id}' ({cfg.vertex.tier}).",
    )

    if dry_run:
        ui.note(f"[dry-run] would create engine {cfg.vertex.engine_id}")
        return

    if _engine_exists(cfg):
        ui.success(f"engine already exists: {cfg.vertex.engine_id}")
        return

    _create_engine(cfg)


def _engine_exists(cfg: Phase3Config) -> bool:
    pn = cfg.gcp.project_number or cfg.gcp.project_id
    url = (
        f"{DISCOVERY_HOST}/{API_VERSION}/projects/{pn}/locations/{cfg.gcp.location}"
        f"/collections/{cfg.vertex.collection}/engines/{cfg.vertex.engine_id}"
    )
    resp = http.get(url, project_id=cfg.gcp.project_id, allow_404=True)
    return resp.status_code == 200


def _create_engine(cfg: Phase3Config) -> None:
    pn = cfg.gcp.project_number or cfg.gcp.project_id
    parent = (
        f"projects/{pn}/locations/{cfg.gcp.location}"
        f"/collections/{cfg.vertex.collection}"
    )
    url = (
        f"{DISCOVERY_HOST}/{API_VERSION}/{parent}/engines"
        f"?engineId={cfg.vertex.engine_id}"
    )

    body = {
        "displayName": f"{cfg.business.display_name} search engine",
        "dataStoreIds": [cfg.vertex.data_store_id],
        "solutionType": "SOLUTION_TYPE_SEARCH",
        "industryVertical": cfg.vertex.industry_vertical,
        "searchEngineConfig": {
            "searchTier": (
                "SEARCH_TIER_ENTERPRISE" if cfg.vertex.tier == "ENTERPRISE"
                else "SEARCH_TIER_STANDARD"
            ),
            "searchAddOns": (
                ["SEARCH_ADD_ON_LLM"] if cfg.vertex.tier == "ENTERPRISE" else []
            ),
        },
        "commonConfig": {
            "companyName": cfg.business.display_name,
        },
    }

    ui.note("Calling engines.create (v1alpha)...")
    resp = http.post(
        url,
        project_id=cfg.gcp.project_id,
        json_body=body,
        expected_ok=(200, 201, 202),
    )
    op = resp.json()
    op_name = op.get("name", "")
    if op_name:
        ui.note(f"Polling LRO: {op_name}")
        http.poll_operation(
            op_name,
            project_id=cfg.gcp.project_id,
            host=DISCOVERY_HOST,
            api_version=API_VERSION,
        )

    ui.success(f"engine created: {cfg.vertex.engine_id}")
    ui.note(f"Serving config: {cfg.serving_config_path()}")

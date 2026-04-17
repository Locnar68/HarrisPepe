"""
Vertex AI Search data store creation.

REST-only, v1alpha endpoint, Layout Parser configured at creation time.

POC learnings encoded here:

* The ``gcloud discovery-engine`` commands **do not exist** — we use REST.
* ``documentProcessingConfig`` (where Layout Parser lives) is ONLY accepted by
  the ``v1alpha`` endpoint, and ONLY at data-store creation time. Setting it
  later returns a PATCH success but has no effect.
* Deleted data-store IDs are reserved for hours. If CREATE returns
  ``ALREADY_EXISTS`` or ``RESOURCE_EXHAUSTED``, we automatically bump the
  suffix to ``-v2``, ``-v3`` and retry.
* The LRO name returned by CREATE may 404 during polling — that's a success
  signal (see ``utils/http.poll_operation``).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from installer.config.schema import Phase3Config
from installer.utils import http, ui

log = logging.getLogger(__name__)

DISCOVERY_HOST = "https://discoveryengine.googleapis.com"
API_VERSION = "v1alpha"
MAX_ID_RETRIES = 5


def ensure_data_store(cfg: Phase3Config, *, dry_run: bool = False) -> None:
    ui.section(
        "Step 10 — Vertex AI Search data store",
        f"Creating data store '{cfg.vertex.data_store_id}' with Layout Parser "
        f"{'enabled' if cfg.vertex.enable_layout_parser else 'disabled'}.",
    )

    if dry_run:
        ui.note(f"[dry-run] would create data store {cfg.vertex.data_store_id}")
        return

    # Does it already exist?
    if _data_store_exists(cfg):
        ui.success(f"data store already exists: {cfg.vertex.data_store_id}")
        return

    # Try to create; on ID conflict, bump -v2/-v3 and retry
    attempts = 0
    base_id = cfg.vertex.data_store_id
    while attempts < MAX_ID_RETRIES:
        try:
            _create_data_store(cfg)
            return
        except _IDReservedError:
            attempts += 1
            new_id = _bump_suffix(base_id, attempts)
            ui.warn(
                f"Data store ID '{cfg.vertex.data_store_id}' is reserved "
                f"(likely from a recent delete). Trying '{new_id}'..."
            )
            cfg.vertex.data_store_id = new_id

    raise RuntimeError(
        f"Could not create data store after {MAX_ID_RETRIES} ID attempts."
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

class _IDReservedError(Exception):
    """Raised when the chosen data-store ID is in the reserved-after-delete window."""


def _data_store_exists(cfg: Phase3Config) -> bool:
    url = f"{DISCOVERY_HOST}/{API_VERSION}/{cfg.data_store_path()}"
    resp = http.get(url, project_id=cfg.gcp.project_id, allow_404=True)
    return resp.status_code == 200


def _create_data_store(cfg: Phase3Config) -> None:
    parent = cfg.data_store_parent()
    url = (
        f"{DISCOVERY_HOST}/{API_VERSION}/{parent}/dataStores"
        f"?dataStoreId={cfg.vertex.data_store_id}"
    )

    body = {
        "displayName": f"{cfg.business.display_name} RAG data store",
        "industryVertical": cfg.vertex.industry_vertical,
        "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
        "contentConfig": cfg.vertex.content_config,
    }

    # Layout Parser — MUST be set here, cannot be patched later.
    if cfg.vertex.enable_layout_parser:
        body["documentProcessingConfig"] = {
            "defaultParsingConfig": {
                "layoutParsingConfig": {},
            },
            # Optional per-MIME overrides go here if needed.
        }

    # Request Enterprise features at create time if selected
    if cfg.vertex.tier == "ENTERPRISE":
        # Enterprise features are enabled on the engine, not the data store,
        # but we record the intent here for the report.
        pass

    ui.note("Calling dataStores.create (v1alpha)...")
    try:
        resp = http.post(
            url,
            project_id=cfg.gcp.project_id,
            json_body=body,
            expected_ok=(200, 201, 202),
        )
    except Exception as e:
        msg = str(e).lower()
        if "already exists" in msg or "resource_exhausted" in msg:
            raise _IDReservedError() from e
        raise

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

    ui.success(f"data store created: {cfg.vertex.data_store_id}")


def _bump_suffix(data_store_id: str, attempt: int) -> str:
    """Take 'foo-ds-v1' -> 'foo-ds-v2' -> 'foo-ds-v3' ... ; or append -v2 if no vN yet."""
    m = re.match(r"^(.*?)(-v(\d+))?$", data_store_id)
    if not m:
        return f"{data_store_id}-v{attempt + 1}"
    base, _, num = m.groups()
    base_num = int(num) if num else 1
    return f"{base}-v{base_num + attempt}"

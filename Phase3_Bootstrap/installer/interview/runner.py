"""
Interview orchestrator.

Runs each interview section in order, assembles a :class:`Phase3Config`,
and returns it. Each section is self-contained and writes its answers back
into a partial config dict so a resumed run can skip already-answered bits.

Section order (matters — later sections depend on earlier ones):

    1. Business
    2. Contact
    3. GCP (project, billing, region)
    4. Service account (name is derived from business display_name)
    5. Storage (bucket names are derived from business display_name)
    6. Vertex AI Search (data store, engine, tier, layout parser)
    7. Connectors menu  →  per-enabled connector questions
    8. Security / final review
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from installer.config.schema import (
    ConnectorConfig,
    Phase3Config,
    PathsConfig,
)
from installer.interview import (
    business as _business,
    contact as _contact,
    gcp as _gcp,
    gdrive_iv as _gdrive,
    gmail_iv as _gmail,
    storage as _storage,
    vertex as _vertex,
    connectors_menu as _connectors_menu,
    review as _review,
)
from installer.state import BootstrapState
from installer.utils import ui

log = logging.getLogger(__name__)


def run_interview(
    *,
    state: BootstrapState,
    install_path: Path,
    non_interactive: bool = False,
) -> Phase3Config:
    """Collect every variable needed to provision the pipeline."""
    ui.set_non_interactive(non_interactive)

    ui.section(
        "Step 2 — Interactive interview",
        "We'll ask about your business, GCP, storage, Vertex AI, and "
        "which repositories to connect. About 15 minutes. You can press "
        "Ctrl-C at any time — re-run with --resume to continue.",
    )

    # ---- 2a. Business ----------------------------------------------------
    business = _business.run()

    # ---- 2b. Contact -----------------------------------------------------
    contact = _contact.run(business)

    # ---- 2c. GCP ---------------------------------------------------------
    gcp = _gcp.run(business)

    # ---- 2d. Service account --------------------------------------------
    from installer.interview import service_account as _sa
    service_account = _sa.run(business, gcp)

    # ---- 2e. Storage -----------------------------------------------------
    storage = _storage.run(business)

    # ---- 2f. Vertex AI Search -------------------------------------------
    vertex = _vertex.run(business)

    # ---- 2g. Connectors --------------------------------------------------
    selected = _connectors_menu.run()
    connectors: list[ConnectorConfig] = []

    # Build each enabled connector's config
    for name in ("gmail", "gdrive", "onedrive", "sql", "fileshare"):
        enabled = name in selected
        if not enabled:
            connectors.append(ConnectorConfig(name=name, enabled=False))
            continue
        if name == "gmail":
            connectors.append(_gmail.run(business, gcp))
        elif name == "gdrive":
            connectors.append(_gdrive.run(business, gcp))
        else:
            # onedrive / sql / fileshare — stubs for Phase 4
            ui.warn(f"Connector '{name}' is a Phase 4 stub — disabled for now.")
            connectors.append(ConnectorConfig(name=name, enabled=False))

    # ---- 2h. Paths -------------------------------------------------------
    paths = PathsConfig(install_path=str(install_path.resolve()))

    # ---- 2i. Assemble ----------------------------------------------------
    cfg = Phase3Config(
        business=business,
        contact=contact,
        gcp=gcp,
        service_account=service_account,
        storage=storage,
        vertex=vertex,
        connectors=connectors,
        paths=paths,
    )

    # ---- 2j. Review ------------------------------------------------------
    _review.run(cfg)

    return cfg

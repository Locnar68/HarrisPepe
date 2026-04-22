"""
Interview orchestrator -- unified Phase 3 + 4 + 5.

Section order:
  1. Business
  2. Contact
  3. GCP (project, billing, region)
  4. Service account
  5. Storage (bucket names derived from gcp.project_id)
  6. Vertex AI Search (data store, engine, tier, layout parser)
  7. Gemini / Phase 4 chat  <-- NEW
  8. Connectors menu  -->  Gmail / GDrive / OneDrive  <-- OneDrive now live
  9. Paths
 10. Assemble
 11. Review
"""

from __future__ import annotations

import logging
from pathlib import Path

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
    gemini_iv as _gemini,
    onedrive_iv as _onedrive,
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
    """Collect every variable needed to provision the full pipeline."""
    ui.set_non_interactive(non_interactive)

    ui.section(
        "Step 2 -- Interactive interview",
        "We'll ask about your business, GCP, storage, Vertex AI, Gemini\n"
        "chat, and which data sources to connect.  About 15-20 minutes.\n"
        "Press Ctrl-C at any time -- re-run with --resume to continue.",
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
    storage = _storage.run(business, gcp)

    # ---- 2f. Vertex AI Search -------------------------------------------
    vertex = _vertex.run(business)

    # ---- 2g. Gemini / Phase 4 chat  (NEW) -------------------------------
    gemini = _gemini.run()

    # ---- 2h. Connectors --------------------------------------------------
    selected = _connectors_menu.run()
    connectors: list[ConnectorConfig] = []

    for name in ("gmail", "gdrive", "onedrive", "sql", "fileshare"):
        enabled = name in selected
        if not enabled:
            connectors.append(ConnectorConfig(name=name, enabled=False))
            continue
        if name == "gmail":
            connectors.append(_gmail.run(business, gcp))
        elif name == "gdrive":
            connectors.append(_gdrive.run(business, gcp))
        elif name == "onedrive":
            connectors.append(_onedrive.run())
        else:
            # sql / fileshare -- future stubs
            ui.warn(f"Connector '{name}' is not yet implemented -- skipping.")
            connectors.append(ConnectorConfig(name=name, enabled=False))

    # ---- 2i. Paths -------------------------------------------------------
    paths = PathsConfig(install_path=str(install_path.resolve()))

    # ---- 2j. Assemble ----------------------------------------------------
    cfg = Phase3Config(
        business=business,
        contact=contact,
        gcp=gcp,
        service_account=service_account,
        storage=storage,
        vertex=vertex,
        gemini=gemini,
        connectors=connectors,
        paths=paths,
    )

    # ---- 2k. Review ------------------------------------------------------
    _review.run(cfg)

    return cfg

"""
Connector wiring.

After GCP resources exist, we deploy a Cloud Run job per enabled connector
(for the sync worker) and a Cloud Scheduler entry (to trigger it on cron).

Phase 3 ships two: Gmail and Google Drive. OneDrive / SQL / File Share live
in ``Phase4_Connectors/`` (not shipped yet).
"""

from __future__ import annotations

import logging
from pathlib import Path

from installer.config.schema import Phase3Config
from installer.connectors import gdrive, gmail
from installer.utils import ui

log = logging.getLogger(__name__)


def configure_selected(
    cfg: Phase3Config,
    *,
    install_path: Path,
    dry_run: bool = False,
    non_interactive: bool = False,
) -> None:
    ui.section("Step 12 — Connectors",
               "Deploying Cloud Run sync jobs and Scheduler triggers.")

    for c in cfg.connectors:
        if not c.enabled:
            continue
        if c.name == "gmail":
            gmail.configure(cfg, c, install_path=install_path, dry_run=dry_run)
        elif c.name == "gdrive":
            gdrive.configure(cfg, c, install_path=install_path, dry_run=dry_run)
        else:
            ui.warn(f"Connector '{c.name}' is a Phase 4 stub — skipping.")

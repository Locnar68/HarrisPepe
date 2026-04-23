"""
Connector wiring.

After GCP resources exist, we deploy a Cloud Run job per enabled connector
(for the sync worker) and a Cloud Scheduler entry (to trigger it on cron).

Phase 3 ships two: Gmail and Google Drive. OneDrive is live in Phase 5.
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
    ui.section("Step 12 \u2014 Connectors",
               "Deploying Cloud Run sync jobs and Scheduler triggers.")

    for c in cfg.connectors:
        if not c.enabled:
            continue
        if c.name == "gmail":
            gmail.configure(cfg, c, install_path=install_path, dry_run=dry_run)
        elif c.name == "gdrive":
            gdrive.configure(cfg, c, install_path=install_path, dry_run=dry_run)
        elif c.name == "onedrive":
            _configure_onedrive(cfg, c, install_path=install_path, dry_run=dry_run)
        else:
            ui.warn(f"Connector '{c.name}' is a Phase 4 stub \u2014 skipping.")


def _configure_onedrive(cfg, connector, *, install_path: Path, dry_run: bool = False) -> None:
    """Run the initial OneDrive -> GCS -> Vertex sync."""
    import os
    import subprocess
    import sys

    sync_script = install_path.parent / "Phase5_oneDrive" / "onedrive_sync.py"
    if not sync_script.exists():
        ui.warn(f"OneDrive sync script not found at {sync_script} \u2014 skipping.")
        ui.note("Run manually: python Phase5_oneDrive/onedrive_sync.py --force")
        return

    if dry_run:
        ui.note(f"[dry-run] Would run: python {sync_script} --force")
        return

    env = os.environ.copy()
    env_file = install_path / "secrets" / ".env"
    if env_file.exists():
        try:
            from dotenv import dotenv_values
            env.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})
        except Exception:
            pass

    ui.note("\nRunning initial OneDrive -> GCS -> Vertex sync...")
    ui.note("   Large libraries may take 20-30 min.")
    ui.note("   Check the Admin panel in Bob for live index status.\n")

    rc = subprocess.call([sys.executable, str(sync_script), "--force"], env=env)
    if rc == 0:
        ui.success("OneDrive sync complete. Open Bob and check Admin panel for doc count.")
    else:
        ui.warn(f"OneDrive sync exited with code {rc}.")
        ui.note(f"Retry manually: python {sync_script} --force")
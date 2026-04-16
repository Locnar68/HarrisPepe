"""OneDrive connector — STUB (Phase 2).

Design contract:
  - Use `rclone copy <remote>:<source_path> :gcs:<bucket>/<mirror_prefix>/<mirror_as>/`
  - `rclone` binary must be on PATH (or RCLONE_BIN env).
  - rclone.conf must define the OneDrive remote (see documents/04-CONNECTOR_GUIDE.md).
  - For personal Gmail/OneDrive this is the only path that works without Workspace.

Implementation sketch in sync():
  import subprocess
  args = ["rclone", "copy", f"{remote}:{source}", f":gcs:{bucket}/{gcs_base}",
          "--config", conf, "--fast-list", "--stats", "30s"]
  proc = subprocess.run(args, ...)
  # parse rclone stats from stdout for SyncStats
"""
from __future__ import annotations

from connectors.base import Connector, SyncStats


class OneDriveConnector(Connector):
    name = "onedrive"

    def sync(self, dry_run: bool = False, force: bool = False, log=print) -> SyncStats:
        stats = SyncStats()
        stats.notes.append(
            "onedrive connector not yet implemented — see documents/04-CONNECTOR_GUIDE.md"
        )
        log("  [stub] onedrive connector is a Phase 2 deliverable")
        return stats

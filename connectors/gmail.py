"""Gmail connector — STUB (Phase 2).

Design contract for the implementer:
  - Search messages matching cfg['query'] (Gmail search syntax).
  - For each match:
      * extract the body as text
      * save attachments
  - Upload to gs://<bucket>/<mirror_prefix>/Gmail/<YYYY>/<MM>/<msg_id>/{body.txt,attach_N.*}
  - Stamp GCS metadata with source="gmail" + source_id=<msg_id> + source_mtime=<internalDate>

Auth:
  - Personal Gmail: impossible with SA alone. Use per-user OAuth client_id.json
    flow (offline access) and store refreshable token.
  - Workspace: use domain-wide delegation — SA impersonates each user.
  See documents/04-CONNECTOR_GUIDE.md for the full writeup.
"""
from __future__ import annotations

from connectors.base import Connector, SyncStats


class GmailConnector(Connector):
    name = "gmail"

    def sync(self, dry_run: bool = False, force: bool = False, log=print) -> SyncStats:
        stats = SyncStats()
        stats.notes.append(
            "gmail connector not yet implemented — see documents/04-CONNECTOR_GUIDE.md"
        )
        log("  [stub] gmail connector is a Phase 2 deliverable")
        return stats

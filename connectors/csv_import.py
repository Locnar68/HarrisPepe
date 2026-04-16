"""CSV connector — STUB (Phase 2).

Design contract:
  - Parse the CSV.
  - For each row, emit a synthetic JSON document to GCS with the row's fields
    flattened into structData (and a rendered text blob for retrieval).
  - Good for: contact lists, invoice ledgers, asset registers.

This is different from other connectors because we're not mirroring files —
we're synthesising documents from rows. The inject step still works on them
because Vertex AI Search's JSONL schema supports inline `content` + `structData`.

See documents/04-CONNECTOR_GUIDE.md for the row-to-document mapping strategy.
"""
from __future__ import annotations

from connectors.base import Connector, SyncStats


class CSVConnector(Connector):
    name = "csv"

    def sync(self, dry_run: bool = False, force: bool = False, log=print) -> SyncStats:
        stats = SyncStats()
        stats.notes.append(
            "csv connector not yet implemented — see documents/04-CONNECTOR_GUIDE.md"
        )
        log("  [stub] csv connector is a Phase 2 deliverable")
        return stats

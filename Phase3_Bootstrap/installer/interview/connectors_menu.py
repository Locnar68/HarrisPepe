"""
Connector selection.

Previously this was a multi-select checkbox list, which turned out to be
error-prone: it's easy to accidentally toggle a choice you didn't mean to.
Now we ask once per connector, Y/N. Clearer, slower by a few seconds,
but nobody enables connectors they didn't want.
"""

from __future__ import annotations

from installer.utils import ui


def run() -> list[str]:
    ui.section(
        "2g — Repositories / connectors",
        "Pick which data sources you want the pipeline to ingest. "
        "You can always add more later by re-running with --resume.",
    )

    names: list[str] = []

    if ui.ask_bool("Enable Gmail connector? (indexes a mailbox)", default=True):
        names.append("gmail")

    if ui.ask_bool("Enable Google Drive connector? (indexes folders)", default=True):
        names.append("gdrive")

    # Phase 4 stubs — mention once, don't prompt
    ui.note("(OneDrive / SharePoint / SQL / File share connectors ship in Phase 4.)")

    if not names:
        ui.warn("No connectors selected — you'll have a working Vertex AI Search "
                "data store but nothing will populate it. You can re-run the "
                "bootstrap later to enable connectors.")
    return names

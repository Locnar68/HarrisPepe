"""
Connector selection menu.

Asks once per connector Y/N.  OneDrive is now a first-class option --
the old "ships in Phase 4" stub is gone.
"""

from __future__ import annotations
from installer.utils import ui


def run() -> list[str]:
    ui.section(
        "2h -- Data source connectors",
        "Pick which sources to index into Vertex AI Search.\n"
        "You can always add more later by re-running with --resume.",
    )

    names: list[str] = []

    if ui.ask_bool("Enable Gmail connector? (indexes a mailbox)", default=True):
        names.append("gmail")

    if ui.ask_bool("Enable Google Drive connector? (indexes Drive folders)", default=True):
        names.append("gdrive")

    if ui.ask_bool("Enable OneDrive / SharePoint connector? (indexes OneDrive folders)", default=False):
        names.append("onedrive")

    # sql / fileshare remain future stubs -- mention once, don't prompt
    ui.note("(SQL / File share connectors are available as future add-ons.)")

    if not names:
        ui.warn(
            "No connectors selected -- Vertex AI Search data store will be\n"
            "created but nothing will populate it. Re-run with --resume to\n"
            "enable connectors later."
        )

    return names

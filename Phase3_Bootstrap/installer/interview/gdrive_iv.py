"""
Google Drive connector interview.

Simplified: always use service-account mode, static MIME allowlist, ask only
for folder IDs + schedule (text input, no arrow-key menu).
"""

from __future__ import annotations

from installer.config.schema import BusinessConfig, ConnectorConfig, GCPConfig
from installer.utils import ui


DEFAULT_MIMES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.document",
    "application/msword",
    "text/plain",
    "text/html",
    "image/png",
    "image/jpeg",
]


def run(business: BusinessConfig, gcp: GCPConfig) -> ConnectorConfig:
    ui.section(
        "Google Drive connector",
        "Service-account mode. After install you'll share each folder with "
        "the SA email the installer prints — that's how access is granted.",
    )

    ui.note(
        "HOW TO GET A FOLDER ID:\n"
        "  1. Open the folder in your browser (drive.google.com)\n"
        "  2. Look at the URL — it ends with /folders/FOLDER_ID\n"
        "  3. Copy everything after /folders/\n\n"
        "  Example URL:\n"
        "    https://drive.google.com/drive/folders/1aBcDeFg1234567890XyZ\n"
        "  Folder ID:\n"
        "    1aBcDeFg1234567890XyZ\n"
    )

    folder_ids_raw = ui.ask_text(
        "Folder IDs (comma-separated)",
        help_text="Paste one or many folder IDs, separated by commas. "
                  "You can also leave this blank and add folder IDs to config.yaml later.",
        required=False,
    )
    folder_ids = [f.strip() for f in folder_ids_raw.split(",") if f.strip()]

    ui.note(
        "SYNC SCHEDULE (cron format: min hour dom mon dow)\n"
        "  Common examples:\n"
        "    0 */3 * * *   — every 3 hours\n"
        "    0 */6 * * *   — every 6 hours\n"
        "    0 8 * * *     — daily at 8am\n"
        "    0 */1 * * *   — every hour\n"
    )
    cron = ui.ask_text(
        "Sync frequency (cron)",
        default="0 8 * * *",
        help_text="Standard 5-field cron expression.",
    )

    return ConnectorConfig(
        name="gdrive",
        enabled=True,
        schedule_cron=cron,
        options={
            "mode": "service_account",            # static
            "drive_type": "specific_folders",     # static
            "folder_ids": folder_ids,
            "mime_allowlist": DEFAULT_MIMES,      # static
        },
        secret_refs={},                           # no secrets needed for SA mode
    )

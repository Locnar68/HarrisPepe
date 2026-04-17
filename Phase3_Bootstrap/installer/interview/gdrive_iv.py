"""
Google Drive connector interview.

Simplified: always use service-account mode, static MIME allowlist, ask only
for folder IDs + schedule (arrow-key selection menu).
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

    cron = ui.ask_select(
        "Sync frequency",
        choices=[
            "0 */3 * * *  (every 3 hours)",
            "0 */6 * * *  (every 6 hours)",
            "0 */8 * * *  (every 8 hours)",
            "0 8 * * *    (once daily at 8am)",
            "0 */1 * * *  (every hour)",
        ],
        default="0 8 * * *    (once daily at 8am)",
    )
    # Extract just the cron expression (strip the description)
    cron = cron.split()[0] + " " + cron.split()[1] + " " + cron.split()[2] + " " + cron.split()[3] + " " + cron.split()[4]

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

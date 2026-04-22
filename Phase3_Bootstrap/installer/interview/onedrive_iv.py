"""
Phase 5 -- OneDrive / SharePoint connector interview section.

Collects Azure App credentials and folder path.
Microsoft device-flow auth happens on FIRST SYNC, not here.

Writes env vars:
    ONEDRIVE_ENABLED, AZURE_CLIENT_ID, AZURE_TENANT_ID,
    ONEDRIVE_FOLDER_PATH, ONEDRIVE_SYNC_SCHEDULE
"""

from __future__ import annotations
from installer.config.schema import ConnectorConfig
from installer.utils import ui

_SCHEDULE_CHOICES = [
    "0 */3 * * *   (every 3 hours)",
    "0 */6 * * *   (every 6 hours)",
    "0 */8 * * *   (every 8 hours)",
    "0 8 * * *     (once daily at 8 am)",
    "0 */1 * * *   (every hour)",
]
_SCHEDULE_CRONS = [
    "0 */3 * * *",
    "0 */6 * * *",
    "0 */8 * * *",
    "0 8 * * *",
    "0 */1 * * *",
]


def run() -> ConnectorConfig:
    ui.section(
        "OneDrive / SharePoint connector",
        "Syncs files from a OneDrive folder to GCS, then indexes them\n"
        "in Vertex AI Search.  Requires an Azure App Registration.\n\n"
        "Microsoft sign-in (device flow) happens on the FIRST sync run --\n"
        "you won't be prompted here.",
    )

    ui.note(
        "HOW TO CREATE AN AZURE APP REGISTRATION (one-time setup):\n"
        "  1. portal.azure.com > Azure Active Directory\n"
        "     > App registrations > New registration\n"
        "  2. Name it anything, e.g. 'HarrisPepe-OneDrive'\n"
        "  3. Supported account types: 'Accounts in this org directory only'\n"
        "  4. Copy the Application (client) ID and Directory (tenant) ID\n"
        "     from the Overview page\n"
        "  5. API permissions > Add > Microsoft Graph > Delegated\n"
        "     > Files.Read  (or Files.Read.All for SharePoint)\n"
        "  6. Authentication tab > Allow public client flows: YES\n"
    )

    client_id = ui.ask_text(
        "Azure App Client ID",
        help_text="Format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        required=True,
    )

    tenant_id = ui.ask_text(
        "Azure Tenant ID",
        help_text="Format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        required=True,
    )

    ui.note(
        "ONEDRIVE FOLDER PATH:\n"
        "  Relative path inside OneDrive -- NOT a URL.\n"
        "  Examples:\n"
        "    Documents/ClientFiles\n"
        "    Shared Documents/Madison Ave Jobs\n"
        "  Leave blank to index from the OneDrive root.\n"
    )

    folder_path = ui.ask_text(
        "OneDrive folder path",
        help_text="e.g. Documents/ClientFiles  (leave blank for root)",
        required=False,
    ) or ""

    choice = ui.ask_select(
        "Sync frequency",
        choices=_SCHEDULE_CHOICES,
        default=_SCHEDULE_CHOICES[3],
    )
    cron = _SCHEDULE_CRONS[_SCHEDULE_CHOICES.index(choice)]

    ui.success(
        "OneDrive connector configured.\n"
        "  On first sync you will be prompted to sign in via browser device flow.\n"
        "  Token is cached locally -- subsequent syncs are silent."
    )

    return ConnectorConfig(
        name="onedrive",
        enabled=True,
        schedule_cron=cron,
        options={
            "azure_client_id": client_id,
            "azure_tenant_id": tenant_id,
            "folder_path": folder_path,
        },
        secret_refs={},
    )

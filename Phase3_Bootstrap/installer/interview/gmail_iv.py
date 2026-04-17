"""
Gmail connector interview.

**Deferred-OAuth pattern** — we collect only the mailbox target, label, and
schedule during the interview. OAuth client ID / secret / refresh token are
acquired *after* the project exists, via:

    python -m installer.connectors.gmail authorize

This avoids the chicken-and-egg problem where the interview would otherwise
link you to the Cloud console for a project that won't be created for
several more steps.
"""

from __future__ import annotations

from installer.config.schema import BusinessConfig, ConnectorConfig, GCPConfig
from installer.utils import ui
from installer.validators import email as email_v


def run(business: BusinessConfig, gcp: GCPConfig) -> ConnectorConfig:
    ui.section(
        "Gmail connector",
        "Just the mailbox target and schedule here — OAuth credentials are "
        "configured AFTER the project is provisioned.",
    )

    # Default suggestion: an address on the business domain, or the user's
    # personal address if that's what's in play. Let the user override either way.
    default_mailbox = f"info@{business.domain}"
    user_email = ui.ask_text(
        "Mailbox email to sync",
        default=default_mailbox,
        help_text="The inbox whose mail will be indexed. Can be a personal "
                  "@gmail.com address or an @your-domain address.",
        validator=email_v,
    )

    label = ui.ask_text(
        "Gmail label to sync",
        default="INBOX",
        help_text="'INBOX' for everything in the inbox, or a custom label "
                  "(e.g. 'RAG-Indexed') to scope tightly.",
    )
    query = ui.ask_text(
        "Gmail search query (optional)",
        default="newer_than:90d",
        help_text="Any Gmail search query. 'newer_than:90d' limits to the "
                  "last 90 days. Leave blank for no extra filter.",
        required=False,
    )

    schedule = ui.ask_select(
        "Sync frequency",
        choices=[
            "0 */6 * * *   — every 6 hours (default)",
            "0 */3 * * *   — every 3 hours",
            "0 * * * *     — every hour",
            "0 8 * * *     — daily at 8am",
            "custom",
        ],
        default="0 */6 * * *   — every 6 hours (default)",
    )
    if schedule == "custom":
        cron = ui.ask_text(
            "Custom cron expression",
            default="0 */6 * * *",
            help_text="Standard 5-field cron (min hour dom mon dow).",
        )
    else:
        cron = " ".join(schedule.split()[:5])

    ui.note("OAuth will be set up after provisioning — the final report "
            "explains exactly what to do.")

    return ConnectorConfig(
        name="gmail",
        enabled=True,
        schedule_cron=cron,
        options={
            "user_email": user_email,
            "label": label,
            "query": query,
            "oauth_deferred": True,
        },
        secret_refs={
            # Populated post-install by `authorize` subcommand
            "client_secret_name": "gmail-oauth-client-secret",
            "refresh_token_name": "gmail-refresh-token",
        },
    )

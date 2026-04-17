"""
Gmail connector — configure deployment + OAuth `authorize` subcommand.

Usage:

    # Deploy-time (run by the bootstrap orchestrator)
    configure(cfg, conn, install_path=..., dry_run=False)

    # Runtime — user runs this once to complete OAuth and populate the
    # refresh-token secret:
    python -m installer.connectors.gmail authorize
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from installer.config.schema import ConnectorConfig, Phase3Config
from installer.connectors.base import deploy_cloud_run_job, deploy_scheduler
from installer.utils import ui

log = logging.getLogger(__name__)


def configure(
    cfg: Phase3Config,
    conn: ConnectorConfig,
    *,
    install_path: Path,
    dry_run: bool = False,
) -> None:
    ui.note(f"Configuring Gmail connector (schedule: {conn.schedule_cron})")

    job = f"{cfg.business.display_name}-gmail-sync"[:63]
    sched = f"{cfg.business.display_name}-gmail-sched"[:128]

    env_vars = {
        "GCP_PROJECT_ID": cfg.gcp.project_id,
        "COMPANY_NAME": cfg.business.display_name,
        "GCS_BUCKET_RAW": cfg.storage.raw_bucket,
        "GCS_BUCKET_PROCESSED": cfg.storage.processed_bucket,
        "VERTEX_DATA_STORE_ID": cfg.vertex.data_store_id,
        "GMAIL_USER_EMAIL": conn.options.get("user_email", ""),
        "GMAIL_LABEL_FILTER": conn.options.get("label", "INBOX"),
        "GMAIL_QUERY": conn.options.get("query", ""),
        "GMAIL_OAUTH_CLIENT_ID": conn.options.get("client_id", ""),
        "GMAIL_OAUTH_CLIENT_SECRET_REF":
            conn.secret_refs.get("gmail-oauth-client-secret_ref", ""),
        "GMAIL_REFRESH_TOKEN_REF":
            conn.secret_refs.get("gmail-refresh-token_ref", ""),
    }

    deploy_cloud_run_job(cfg, conn, job_name=job, env_vars=env_vars, dry_run=dry_run)
    deploy_scheduler(cfg, conn, scheduler_name=sched, job_name=job, dry_run=dry_run)

    ui.note("Next: run `python -m installer.connectors.gmail authorize` to "
            "complete OAuth and populate the refresh-token secret.")


# ---------------------------------------------------------------------------
# OAuth authorize flow (stub)
# ---------------------------------------------------------------------------

def authorize() -> int:
    """Run the OAuth installed-app flow and store the refresh token.

    This is a STUB in Phase 3 — the full flow (launch browser, handle
    redirect, exchange auth code) lives in the separate ``phase3-oauth-helper``
    package which the real CI build installs into the Cloud Run image.
    """
    ui.section("Gmail OAuth", "Obtain a refresh token and push it to Secret Manager.")
    ui.warn(
        "This installer ships only the scaffolding. To complete the OAuth flow:\n\n"
        "  1. Copy your OAuth client JSON to ./secrets/gmail-oauth-client.json\n"
        "  2. Run:  python -m installer.connectors.gmail run-oauth\n"
        "  3. A browser tab will open; sign in as the mailbox owner.\n"
        "  4. The installer will push the resulting refresh token to\n"
        "     Secret Manager as the version referenced by\n"
        "     GMAIL_REFRESH_TOKEN_REF.\n\n"
        "The `run-oauth` subcommand is implemented in installer/connectors/oauth_helper.py\n"
        "(Phase 3.1 — next release)."
    )
    return 0


if __name__ == "__main__":
    # Simple argv dispatch so users can run:
    #   python -m installer.connectors.gmail authorize
    if len(sys.argv) >= 2 and sys.argv[1] == "authorize":
        sys.exit(authorize())
    print("Usage: python -m installer.connectors.gmail authorize")
    sys.exit(2)

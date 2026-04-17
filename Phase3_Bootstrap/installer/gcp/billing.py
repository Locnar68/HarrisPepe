"""Link a billing account to the project."""

from __future__ import annotations

import json
import logging

from installer.config.schema import Phase3Config
from installer.utils import shell, ui

log = logging.getLogger(__name__)

BILLING_URL = "https://console.cloud.google.com/billing"


def ensure_billing(
    cfg: Phase3Config,
    *,
    dry_run: bool = False,
    non_interactive: bool = False,
) -> None:
    ui.section("Step 5 — Billing",
               "Vertex AI Search requires billing to be enabled on the project.")

    if not cfg.gcp.billing_account_id:
        ui.warn("No billing account ID provided during the interview.")
        ui.show_link("Link billing in the console",
                     f"{BILLING_URL}/linkedaccount?project={cfg.gcp.project_id}")
        if non_interactive:
            raise RuntimeError(
                "Billing not linked. In non-interactive mode, billing must be "
                "pre-configured. Aborting."
            )
        if not ui.ask_bool(
            "Have you now linked billing in the console? Continue anyway?",
            default=False,
        ):
            raise RuntimeError("Billing is required. Exiting.")
        return

    # Check current binding
    res = shell.run(
        ["gcloud", "billing", "projects", "describe", cfg.gcp.project_id,
         "--format=json"],
        check=False, timeout=30, dry_run=dry_run,
    )
    if not dry_run and res.ok:
        try:
            data = json.loads(res.stdout)
            current = (data.get("billingAccountName", "") or "").split("/")[-1]
            if current == cfg.gcp.billing_account_id and data.get("billingEnabled"):
                ui.success(f"Billing already linked: {current}")
                return
        except json.JSONDecodeError:
            pass

    # Link
    ui.note(f"Linking billing account {cfg.gcp.billing_account_id}...")
    res = shell.run(
        ["gcloud", "billing", "projects", "link", cfg.gcp.project_id,
         f"--billing-account={cfg.gcp.billing_account_id}"],
        check=False, timeout=60, dry_run=dry_run,
    )
    if dry_run:
        return
    if not res.ok:
        raise RuntimeError(
            f"Failed to link billing account: {res.stderr}\n"
            f"You may need to do this manually at {BILLING_URL}"
        )
    ui.success(f"Billing linked: {cfg.gcp.billing_account_id}")

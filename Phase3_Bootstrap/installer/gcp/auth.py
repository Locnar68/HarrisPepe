"""
Ensure the user is signed in to gcloud.

This runs before any project work so we can:

* detect if no credentials exist and run ``gcloud auth login``
* set the active project via ``gcloud config set project``
* register application-default credentials for SDK libraries
* set the quota project so the X-Goog-User-Project header is not required
  for every REST call (belt-and-braces — we set the header anyway)
"""

from __future__ import annotations

import json
import logging

from installer.config.schema import Phase3Config
from installer.utils import shell, ui

log = logging.getLogger(__name__)


def ensure_login(cfg: Phase3Config, *, dry_run: bool = False) -> None:
    ui.section("Step 3 — Google Cloud sign-in",
               "Making sure gcloud has valid credentials for this machine.")

    active = _active_account()
    if active:
        ui.success(f"Signed in as: {active}")
    else:
        ui.warn("No active gcloud account — launching `gcloud auth login`.")
        if not dry_run:
            shell.run(["gcloud", "auth", "login", "--brief"], timeout=600)
            active = _active_account()
            if not active:
                raise RuntimeError("Sign-in did not complete successfully.")
            ui.success(f"Signed in as: {active}")

    # --- ADC for Python client libs --------------------------------------
    if not _has_adc():
        ui.note("Setting up Application Default Credentials...")
        if not dry_run:
            shell.run(
                ["gcloud", "auth", "application-default", "login", "--brief"],
                timeout=600,
            )
        ui.success("Application-default credentials configured.")

    # --- Active project --------------------------------------------------
    if not dry_run and cfg.gcp.project_exists:
        # Only set as active if the project already exists — otherwise this
        # happens after Step 4 creates it.
        shell.run(
            ["gcloud", "config", "set", "project", cfg.gcp.project_id],
            timeout=30,
        )
        shell.run(
            ["gcloud", "auth", "application-default", "set-quota-project",
             cfg.gcp.project_id],
            check=False,  # harmless failure if already set
            timeout=30,
        )
        ui.success(f"Active project: {cfg.gcp.project_id}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _active_account() -> str:
    res = shell.run(
        ["gcloud", "auth", "list",
         "--filter=status:ACTIVE", "--format=value(account)"],
        check=False, timeout=30,
    )
    return (res.stdout or "").strip()


def _has_adc() -> bool:
    """Check if application-default credentials already exist."""
    res = shell.run(
        ["gcloud", "auth", "application-default", "print-access-token"],
        check=False, timeout=30,
    )
    return bool(res.ok and res.stdout.strip())

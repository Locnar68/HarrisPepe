"""
GCP project creation / verification.

If ``cfg.gcp.project_exists`` is True, we only confirm the project is visible
and grab its project_number. Otherwise we create a fresh project under the
chosen org/folder (or no parent, for personal accounts).
"""

from __future__ import annotations

import json
import logging

from installer.config.schema import Phase3Config
from installer.utils import shell, ui

log = logging.getLogger(__name__)


def ensure_project(cfg: Phase3Config, *, dry_run: bool = False) -> None:
    ui.section("Step 4 — GCP project",
               "Verify or create the project that will host all resources.")

    if cfg.gcp.project_exists:
        _describe_existing(cfg, dry_run=dry_run)
    else:
        _create_new(cfg, dry_run=dry_run)

    # Set it active regardless
    if not dry_run:
        shell.run(
            ["gcloud", "config", "set", "project", cfg.gcp.project_id],
            timeout=30,
        )
        shell.run(
            ["gcloud", "auth", "application-default", "set-quota-project",
             cfg.gcp.project_id],
            check=False, timeout=30,
        )


def _describe_existing(cfg: Phase3Config, *, dry_run: bool) -> None:
    res = shell.run(
        ["gcloud", "projects", "describe", cfg.gcp.project_id,
         "--format=json"],
        check=False, timeout=30, dry_run=dry_run,
    )
    if dry_run:
        ui.note(f"[dry-run] would describe project {cfg.gcp.project_id}")
        return
    if not res.ok:
        raise RuntimeError(
            f"Could not describe project '{cfg.gcp.project_id}'.\n"
            f"gcloud stderr:\n{res.stderr}\n"
            "Possible causes: project doesn't exist, or your account lacks access."
        )
    data = json.loads(res.stdout)
    cfg.gcp.project_number = str(data.get("projectNumber", ""))
    ui.success(f"Project confirmed: {cfg.gcp.project_id} "
               f"(number: {cfg.gcp.project_number})")


def _create_new(cfg: Phase3Config, *, dry_run: bool) -> None:
    args = ["gcloud", "projects", "create", cfg.gcp.project_id,
            f"--name={cfg.business.display_name}"]
    if cfg.gcp.organization_id:
        args.append(f"--organization={cfg.gcp.organization_id}")
    elif cfg.gcp.folder_id:
        args.append(f"--folder={cfg.gcp.folder_id}")

    ui.note(f"Creating project '{cfg.gcp.project_id}'...")
    res = shell.run(args, check=False, timeout=180, dry_run=dry_run)
    if dry_run:
        ui.note(f"[dry-run] would create {cfg.gcp.project_id}")
        return

    if not res.ok and "already exists" not in (res.stderr or ""):
        raise RuntimeError(
            f"Failed to create project '{cfg.gcp.project_id}':\n{res.stderr}"
        )

    # Re-describe to get the project_number
    _describe_existing(cfg, dry_run=False)
    ui.success(f"Project created: {cfg.gcp.project_id}")

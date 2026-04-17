"""
Service account creation + role grant + key file.

Idempotent: detects existing SA and skips creation. Role binding is done one
role at a time so a partial failure doesn't roll back successful grants.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from installer.config.schema import Phase3Config
from installer.utils import shell, ui

log = logging.getLogger(__name__)


def ensure_service_account(
    cfg: Phase3Config,
    *,
    install_path: Path,
    dry_run: bool = False,
) -> None:
    ui.section("Step 7 — Service account",
               f"Creating {cfg.service_account.email} and granting "
               f"{len(cfg.service_account.roles)} roles.")

    sa = cfg.service_account
    project = cfg.gcp.project_id

    # --- Check if SA already exists --------------------------------------
    res = shell.run(
        ["gcloud", "iam", "service-accounts", "describe", sa.email,
         f"--project={project}"],
        check=False, timeout=30, dry_run=dry_run,
    )

    if not dry_run and res.ok:
        ui.success(f"SA already exists: {sa.email}")
    else:
        res = shell.run(
            ["gcloud", "iam", "service-accounts", "create", sa.short_name,
             f"--display-name={sa.display_name}",
             f"--project={project}"],
            check=False, timeout=60, dry_run=dry_run,
        )
        if not dry_run and not res.ok and "already exists" not in (res.stderr or ""):
            raise RuntimeError(f"Failed to create SA: {res.stderr}")
        ui.success(f"SA created: {sa.email}")

    # --- Grant each role -------------------------------------------------
    for role in sa.roles:
        res = shell.run(
            ["gcloud", "projects", "add-iam-policy-binding", project,
             f"--member=serviceAccount:{sa.email}",
             f"--role={role}",
             "--condition=None"],
            check=False, timeout=60, dry_run=dry_run,
        )
        if dry_run:
            ui.note(f"[dry-run] would grant {role}")
        elif res.ok:
            ui.success(f"granted: {role}")
        else:
            ui.warn(f"role grant for {role} failed (may already be bound): "
                    f"{res.stderr.strip()[:120]}")

    # --- Create JSON key -------------------------------------------------
    key_path = install_path / "secrets" / "service-account.json"
    cfg.service_account.key_path = str(key_path)
    if dry_run:
        ui.note(f"[dry-run] would write key to {key_path}")
        return

    if key_path.exists():
        ui.warn(f"Key file already exists at {key_path}; leaving it in place.")
        return

    key_path.parent.mkdir(parents=True, exist_ok=True)
    res = shell.run(
        ["gcloud", "iam", "service-accounts", "keys", "create",
         str(key_path),
         f"--iam-account={sa.email}",
         f"--project={project}"],
        check=False, timeout=60,
    )
    if not res.ok:
        raise RuntimeError(f"Failed to create SA key: {res.stderr}")

    # Harden perms on POSIX
    try:
        os.chmod(key_path, 0o600)
    except (OSError, NotImplementedError):
        pass

    ui.success(f"SA key written: {key_path}")
    ui.warn("This file contains private key material. It is gitignored. "
            "Do NOT commit it, email it, or paste into chats.")

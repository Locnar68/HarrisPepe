"""
Secret Manager integration.

For each enabled connector, we:

1. Read the secret values collected at interview time from ``connector.secret_refs``
2. Create (or update) a secret in Secret Manager under the project
3. Store the resource path back into ``secret_refs`` so the runtime can read it
4. Scrub the plaintext value from the in-memory config

Refresh tokens are placeholders at install time — they get populated later
by the connector's ``authorize`` subcommand, which performs the OAuth flow.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from installer.config.schema import Phase3Config
from installer.utils import shell, ui

log = logging.getLogger(__name__)


def ensure_secrets(
    cfg: Phase3Config,
    *,
    install_path: Path,
    dry_run: bool = False,
) -> None:
    ui.section("Step 9 — Secret Manager",
               "Storing OAuth client secrets securely. Refresh tokens get "
               "populated later via the connector `authorize` command.")

    project = cfg.gcp.project_id
    any_secrets = False

    for conn in cfg.connectors:
        if not conn.enabled:
            continue

        refs = dict(conn.secret_refs)  # copy
        secret_value = refs.pop("client_secret_value", None)
        secret_name = refs.get("client_secret_name")

        if not (secret_value and secret_name):
            continue

        any_secrets = True
        _create_or_update_secret(
            project=project,
            secret_name=secret_name,
            value=secret_value,
            dry_run=dry_run,
        )

        # Also pre-create the refresh-token secret as an empty version-0 shell
        rt_name = refs.get("refresh_token_name")
        if rt_name:
            _ensure_secret_empty(project, rt_name, dry_run=dry_run)

        # Scrub in-memory plaintext
        conn.secret_refs = {k: v for k, v in conn.secret_refs.items()
                            if k != "client_secret_value"}
        conn.secret_refs[f"{secret_name}_ref"] = (
            f"projects/{cfg.gcp.project_number or project}"
            f"/secrets/{secret_name}/versions/latest"
        )
        if rt_name:
            conn.secret_refs[f"{rt_name}_ref"] = (
                f"projects/{cfg.gcp.project_number or project}"
                f"/secrets/{rt_name}/versions/latest"
            )

    if not any_secrets:
        ui.note("No connector secrets to write.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_or_update_secret(
    *,
    project: str,
    secret_name: str,
    value: str,
    dry_run: bool,
) -> None:
    exists = _secret_exists(project, secret_name, dry_run=dry_run)
    if not exists:
        res = shell.run(
            ["gcloud", "secrets", "create", secret_name,
             f"--project={project}",
             "--replication-policy=automatic"],
            check=False, timeout=30, dry_run=dry_run,
        )
        if not dry_run and not res.ok and "already exists" not in (res.stderr or ""):
            raise RuntimeError(f"Failed to create secret {secret_name}: {res.stderr}")
        ui.success(f"secret created: {secret_name}")

    # Add new version with the value via stdin — never put secret on command line
    if dry_run:
        ui.note(f"[dry-run] would add new version to secret {secret_name}")
        return

    res = shell.run(
        ["gcloud", "secrets", "versions", "add", secret_name,
         f"--project={project}",
         "--data-file=-"],
        input_text=value,
        check=False, timeout=30,
    )
    if not res.ok:
        raise RuntimeError(f"Failed to add version to {secret_name}: {res.stderr}")
    ui.success(f"secret version added: {secret_name}")


def _ensure_secret_empty(project: str, name: str, *, dry_run: bool) -> None:
    """Pre-create an empty secret container for refresh tokens."""
    if _secret_exists(project, name, dry_run=dry_run):
        return
    res = shell.run(
        ["gcloud", "secrets", "create", name,
         f"--project={project}",
         "--replication-policy=automatic"],
        check=False, timeout=30, dry_run=dry_run,
    )
    if dry_run:
        ui.note(f"[dry-run] would create empty secret {name}")
        return
    if res.ok:
        ui.success(f"secret placeholder created: {name} (populate via `authorize`)")


def _secret_exists(project: str, name: str, *, dry_run: bool) -> bool:
    if dry_run:
        return False
    res = shell.run(
        ["gcloud", "secrets", "describe", name, f"--project={project}"],
        check=False, timeout=20,
    )
    return res.ok

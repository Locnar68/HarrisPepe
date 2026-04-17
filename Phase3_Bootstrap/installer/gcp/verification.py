"""
Post-install verification (called via `bootstrap.ps1 -Verify` or `--verify`).

Runs a series of read-only checks against the live GCP resources to confirm
everything came up correctly. Reports as a PASS/FAIL table at the end.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.table import Table

from installer.config.loader import load_config
from installer.state import BootstrapState
from installer.utils import http, shell, ui

log = logging.getLogger(__name__)
_console = Console()


def run(state: BootstrapState, install_path: Path) -> int:
    ui.section("Verification", "Read-only sanity checks against live resources.")
    cfg_path = install_path / "config" / "config.yaml"
    if not cfg_path.exists():
        ui.warn(f"No config found at {cfg_path}. Nothing to verify.")
        return 2
    cfg = load_config(cfg_path)

    checks: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
        ("gcloud signed in", _check_gcloud_auth),
        ("project accessible", lambda: _check_project(cfg)),
        ("raw bucket exists", lambda: _check_bucket(cfg.storage.raw_bucket)),
        ("processed bucket exists", lambda: _check_bucket(cfg.storage.processed_bucket)),
        ("service account exists", lambda: _check_sa(cfg)),
        ("data store reachable", lambda: _check_data_store(cfg)),
        ("engine reachable", lambda: _check_engine(cfg)),
    ]

    if cfg.storage.archive_bucket:
        checks.insert(3, ("archive bucket exists",
                          lambda: _check_bucket(cfg.storage.archive_bucket)))

    t = Table(show_header=True, header_style="bold cyan")
    t.add_column("Check", no_wrap=True)
    t.add_column("Status")
    t.add_column("Detail")

    all_ok = True
    for label, fn in checks:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"exception: {e}"
        t.add_row(
            label,
            "[green]PASS[/]" if ok else "[red]FAIL[/]",
            detail,
        )
        if not ok:
            all_ok = False

    _console.print(t)

    if all_ok:
        ui.success("All checks passed.")
        return 0
    ui.warn("Some checks failed — inspect details above.")
    return 1


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_gcloud_auth() -> tuple[bool, str]:
    res = shell.run(
        ["gcloud", "auth", "list",
         "--filter=status:ACTIVE", "--format=value(account)"],
        check=False, timeout=20,
    )
    acct = (res.stdout or "").strip()
    return (bool(acct), acct or "no active account")


def _check_project(cfg) -> tuple[bool, str]:
    res = shell.run(
        ["gcloud", "projects", "describe", cfg.gcp.project_id,
         "--format=value(projectNumber)"],
        check=False, timeout=30,
    )
    if res.ok:
        return True, f"projectNumber={res.stdout.strip()}"
    return False, res.stderr.strip()[:120]


def _check_bucket(name: str) -> tuple[bool, str]:
    res = shell.run(
        ["gcloud", "storage", "buckets", "describe", f"gs://{name}",
         "--format=value(name)"],
        check=False, timeout=30,
    )
    return (res.ok, f"gs://{name}" if res.ok else res.stderr.strip()[:120])


def _check_sa(cfg) -> tuple[bool, str]:
    res = shell.run(
        ["gcloud", "iam", "service-accounts", "describe",
         cfg.service_account.email,
         f"--project={cfg.gcp.project_id}",
         "--format=value(email)"],
        check=False, timeout=30,
    )
    return (res.ok, cfg.service_account.email if res.ok else res.stderr.strip()[:120])


def _check_data_store(cfg) -> tuple[bool, str]:
    url = f"https://discoveryengine.googleapis.com/v1alpha/{cfg.data_store_path()}"
    resp = http.get(url, project_id=cfg.gcp.project_id, allow_404=True)
    return (resp.status_code == 200, f"HTTP {resp.status_code}")


def _check_engine(cfg) -> tuple[bool, str]:
    pn = cfg.gcp.project_number or cfg.gcp.project_id
    url = (
        f"https://discoveryengine.googleapis.com/v1alpha/"
        f"projects/{pn}/locations/{cfg.gcp.location}"
        f"/collections/{cfg.vertex.collection}/engines/{cfg.vertex.engine_id}"
    )
    resp = http.get(url, project_id=cfg.gcp.project_id, allow_404=True)
    return (resp.status_code == 200, f"HTTP {resp.status_code}")

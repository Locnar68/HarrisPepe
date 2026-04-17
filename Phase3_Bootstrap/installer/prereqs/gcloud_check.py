"""Check the gcloud CLI is installed and responsive."""

from __future__ import annotations

import logging

from installer.utils import shell, ui

log = logging.getLogger(__name__)


def check() -> None:
    if not shell.which("gcloud"):
        raise RuntimeError(
            "gcloud CLI not found on PATH. Re-run bootstrap.ps1 / bootstrap.sh — "
            "its install step can bring this in via winget / brew / apt."
        )

    res = shell.run(["gcloud", "--version"], check=False, timeout=30)
    if not res.ok:
        raise RuntimeError(
            f"`gcloud --version` returned {res.returncode}. stderr:\n{res.stderr}"
        )

    first_line = (res.stdout or "").splitlines()[0] if res.stdout else "(unknown)"
    ui.success(f"gcloud: {first_line}")
    log.debug("gcloud versions:\n%s", res.stdout)

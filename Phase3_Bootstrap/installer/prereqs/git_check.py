"""Check git — non-fatal, warn only if missing."""

from __future__ import annotations

from installer.utils import shell, ui


def check() -> None:
    if not shell.which("git"):
        ui.warn("git is not installed. Not required to bootstrap, but you'll "
                "need it to push Phase 3 back to the HarrisPepe repo.")
        return
    res = shell.run(["git", "--version"], check=False, timeout=10)
    if res.ok:
        ui.success(res.stdout.strip())
    else:
        ui.warn("git found but `git --version` failed — check your install.")

"""
Host-machine prerequisite checks.

The PowerShell / bash bootstrap scripts already installed the binaries. By
the time Python runs, they should all be on PATH. This module just *verifies*
that — if something is missing it means the install script failed silently,
and we want the user to see a clear error rather than a cryptic stack trace
later.
"""

from __future__ import annotations

import logging

from installer.prereqs import git_check, gcloud_check, python_check
from installer.utils import ui

log = logging.getLogger(__name__)


def run_checks(*, non_interactive: bool = False) -> None:
    """Run all prereq checks. Raises RuntimeError on fatal missing deps."""
    ui.section("Step 1 — Host prerequisites",
               "Verify Python, gcloud, and git are present and usable.")

    python_check.check()
    gcloud_check.check()
    git_check.check()  # non-fatal — warns only

    ui.success("All required tools detected.")

"""Check Python version."""

from __future__ import annotations

import sys

from installer.utils import ui

MIN_MAJOR = 3
MIN_MINOR = 10


def check() -> None:
    v = sys.version_info
    if (v.major, v.minor) < (MIN_MAJOR, MIN_MINOR):
        raise RuntimeError(
            f"Python {MIN_MAJOR}.{MIN_MINOR}+ required, got {v.major}.{v.minor}.{v.micro}. "
            "Re-run bootstrap.ps1 / bootstrap.sh so the wrapper installs a new Python."
        )
    ui.success(f"Python {v.major}.{v.minor}.{v.micro}")

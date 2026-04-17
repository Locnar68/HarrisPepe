"""Structured logging setup."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from rich.logging import RichHandler


def setup_logging(log_dir: Path, verbose: int = 0) -> None:
    """Configure root logger with a rotating-ish file handler and Rich console."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"bootstrap-{time.strftime('%Y%m%d-%H%M%S')}.log"

    level = logging.INFO
    if verbose >= 2:
        level = logging.DEBUG
    elif verbose == 1:
        level = logging.INFO

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # handlers control their own level

    # Clear any prior handlers (idempotent for resume runs)
    for h in list(root.handlers):
        root.removeHandler(h)

    file_h = logging.FileHandler(log_file, encoding="utf-8")
    file_h.setLevel(logging.DEBUG)
    file_h.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s"
    ))
    root.addHandler(file_h)

    console_h = RichHandler(
        level=level,
        rich_tracebacks=True,
        show_path=False,
        show_time=False,
        markup=True,
    )
    console_h.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(console_h)

    # Quiet noisy libraries unless very verbose
    if verbose < 2:
        for noisy in ("urllib3", "google.auth", "google.auth.transport",
                      "google.api_core", "googleapiclient"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).debug("Log file: %s", log_file)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

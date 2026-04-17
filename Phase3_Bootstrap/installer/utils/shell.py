"""
Shell execution helpers.

All subprocess calls go through here so we can:

* apply a sane default timeout
* normalize stdout/stderr capture
* honour ``--dry-run`` everywhere
* log the exact command that was run (for troubleshooting)
* resolve Windows commands via PATHEXT (gcloud.cmd etc.)
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional, Sequence, Union

log = logging.getLogger(__name__)

Command = Union[str, Sequence[str]]


@dataclass
class ShellResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def __bool__(self) -> bool:
        return self.ok


class ShellError(RuntimeError):
    def __init__(self, cmd: str, result: ShellResult):
        self.cmd = cmd
        self.result = result
        super().__init__(
            f"Command failed ({result.returncode}): {cmd}\n"
            f"--- stderr ---\n{result.stderr.strip()}\n"
        )


def _resolve_win_command(args: list) -> list:
    """On Windows, Python's subprocess does NOT consult PATHEXT when given a
    list of arguments with ``shell=False``. That means ``gcloud`` (which is
    actually ``gcloud.cmd``) fails with WinError 2. Resolve the first token
    via ``shutil.which`` so the absolute path is passed instead.
    """
    if not args or os.name != "nt":
        return args
    first = str(args[0])
    # If it's already an absolute path or has an extension, leave it alone
    if os.path.isabs(first) or os.path.splitext(first)[1]:
        return args
    resolved = shutil.which(first)
    if resolved:
        new = list(args)
        new[0] = resolved
        return new
    return args


def run(
    cmd: Command,
    *,
    check: bool = True,
    timeout: Optional[int] = 120,
    env: Optional[dict] = None,
    cwd: Optional[str] = None,
    dry_run: bool = False,
    input_text: Optional[str] = None,
) -> ShellResult:
    """Run a shell command and return its result."""
    if isinstance(cmd, str):
        pretty = cmd
        shell = True
        args: Command = cmd
    else:
        args = _resolve_win_command(list(cmd))
        pretty = " ".join(shlex.quote(str(c)) for c in args)
        shell = False

    log.debug("$ %s", pretty)

    if dry_run:
        log.info("[dry-run] %s", pretty)
        return ShellResult(0, "", "")

    try:
        proc = subprocess.run(
            args,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=cwd,
            input=input_text,
        )
    except subprocess.TimeoutExpired as e:
        log.error("Command timed out after %ss: %s", timeout, pretty)
        raise ShellError(pretty, ShellResult(124, "", str(e))) from e
    except FileNotFoundError as e:
        raise ShellError(pretty, ShellResult(127, "", f"not found: {e}")) from e

    result = ShellResult(proc.returncode, proc.stdout or "", proc.stderr or "")
    if check and not result.ok:
        raise ShellError(pretty, result)
    return result


def which(cmd: str) -> Optional[str]:
    """Lightweight shutil.which wrapper — does not depend on stdlib import order."""
    return shutil.which(cmd)

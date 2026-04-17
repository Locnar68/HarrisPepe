"""
Unified interactive UI helpers.

All interview prompts go through this module so:

* ``--non-interactive`` mode can fail fast when a value is missing
* validation runs in a loop — invalid input never aborts the install
* defaults are shown consistently
* answers are echoed back so the user can confirm
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional, Sequence

import questionary
from rich.console import Console
from rich.panel import Panel

from installer.validators import ValidationError

log = logging.getLogger(__name__)
_console = Console()


class NonInteractiveAbort(RuntimeError):
    """Raised when a required value is missing in --non-interactive mode."""


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_is_noninteractive: bool = False


def set_non_interactive(enabled: bool) -> None:
    """Toggle the module-wide non-interactive flag."""
    global _is_noninteractive
    _is_noninteractive = bool(enabled)


def is_non_interactive() -> bool:
    return _is_noninteractive or bool(os.environ.get("PHASE3_NON_INTERACTIVE"))


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------

def section(title: str, subtitle: str = "") -> None:
    body = f"[bold]{title}[/]"
    if subtitle:
        body += f"\n[dim]{subtitle}[/]"
    _console.print(Panel(body, border_style="cyan"))


def note(msg: str) -> None:
    _console.print(f"[dim]  {msg}[/]")


def warn(msg: str) -> None:
    _console.print(f"[yellow]  ! {msg}[/]")


def success(msg: str) -> None:
    _console.print(f"[green]  + {msg}[/]")


def show_link(label: str, url: str) -> None:
    _console.print(f"[dim]  {label}:[/] [link={url}]{url}[/link]")


# ---------------------------------------------------------------------------
# Input primitives
# ---------------------------------------------------------------------------

def ask_text(
    question: str,
    *,
    default: str = "",
    validator: Optional[Callable[[str], str]] = None,
    help_text: str = "",
    required: bool = True,
) -> str:
    """Ask for free-text input; re-prompt on validation failure."""
    if help_text:
        note(help_text)

    if is_non_interactive():
        if default:
            log.info("[non-interactive] %s = %s", question, default)
            return validator(default) if validator else default
        if not required:
            return ""
        raise NonInteractiveAbort(f"Missing required value: {question}")

    while True:
        raw = questionary.text(question, default=default).ask()
        if raw is None:  # Ctrl-C
            raise KeyboardInterrupt()
        raw = raw.strip()
        if not raw and not required:
            return ""
        if not raw and required and not default:
            warn("This field is required.")
            continue
        try:
            return validator(raw) if validator else raw
        except ValidationError as e:
            warn(str(e))


def ask_bool(question: str, *, default: bool = True) -> bool:
    if is_non_interactive():
        log.info("[non-interactive] %s = %s", question, default)
        return default
    ans = questionary.confirm(question, default=default).ask()
    if ans is None:
        raise KeyboardInterrupt()
    return bool(ans)


def ask_select(
    question: str,
    choices: Sequence[str],
    *,
    default: Optional[str] = None,
) -> str:
    if is_non_interactive():
        pick = default or choices[0]
        log.info("[non-interactive] %s = %s", question, pick)
        return pick
    ans = questionary.select(question, choices=list(choices), default=default).ask()
    if ans is None:
        raise KeyboardInterrupt()
    return ans


def ask_multi_select(
    question: str,
    choices: Sequence[str],
    *,
    defaults: Optional[Sequence[str]] = None,
) -> list[str]:
    if is_non_interactive():
        pick = list(defaults or [])
        log.info("[non-interactive] %s = %s", question, pick)
        return pick
    # questionary.checkbox returns a list
    formatted = [
        questionary.Choice(c, checked=(c in (defaults or [])))
        for c in choices
    ]
    ans = questionary.checkbox(question, choices=formatted).ask()
    if ans is None:
        raise KeyboardInterrupt()
    return list(ans)


def ask_secret(question: str, *, required: bool = True) -> str:
    """Password-style prompt; value is not echoed to the terminal."""
    if is_non_interactive():
        if not required:
            return ""
        raise NonInteractiveAbort(
            f"Secret prompts not allowed in --non-interactive mode: {question}"
        )
    ans = questionary.password(question).ask()
    if ans is None:
        raise KeyboardInterrupt()
    ans = ans.strip()
    if not ans and required:
        warn("This field is required.")
        return ask_secret(question, required=True)
    return ans


def ask_int(
    question: str,
    *,
    default: Optional[int] = None,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    while True:
        raw = ask_text(
            question,
            default=str(default) if default is not None else "",
            required=True,
        )
        try:
            v = int(raw)
        except ValueError:
            warn(f"'{raw}' is not a valid integer.")
            continue
        if minimum is not None and v < minimum:
            warn(f"Must be >= {minimum}.")
            continue
        if maximum is not None and v > maximum:
            warn(f"Must be <= {maximum}.")
            continue
        return v

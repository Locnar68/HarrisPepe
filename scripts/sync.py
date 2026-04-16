"""`python scripts/sync.py` — pull data from every enabled connector into GCS.

Reads `connectors:` from config.yaml, instantiates each enabled connector,
calls its .sync() method, and aggregates stats.
"""
from __future__ import annotations

import _path  # noqa: F401
import sys

import click
from rich.console import Console
from rich.table import Table

from core import load_config
from connectors import build as build_connector
from connectors.base import SyncStats

console = Console()


@click.command()
@click.option("--dry-run", is_flag=True, help="Walk sources, don't upload.")
@click.option("--force", is_flag=True, help="Re-upload even if unchanged.")
@click.option("--only", multiple=True,
              help="Run only these connectors (can be repeated). "
                   "Default: all enabled in config.yaml.")
def main(dry_run: bool, force: bool, only: tuple[str, ...]) -> None:
    cfg = load_config()
    targets = list(only) if only else cfg.enabled_connectors()

    if not targets:
        console.print(
            "[yellow]no connectors enabled.[/yellow] "
            "Edit config/config.yaml to flip `enabled: true` on one."
        )
        sys.exit(0)

    console.rule(f"[bold]{'DRY RUN: ' if dry_run else ''}Sync {targets}[/bold]")

    overall = SyncStats()
    per_connector: dict[str, SyncStats] = {}

    for name in targets:
        ccfg = cfg.connector_cfg(name)
        if not ccfg and name not in cfg.enabled_connectors():
            console.print(f"[yellow]skip {name}: no config section[/yellow]")
            continue
        console.print(f"\n[bold cyan]» {name}[/bold cyan]")
        try:
            conn = build_connector(name, cfg, ccfg)
            stats = conn.sync(dry_run=dry_run, force=force, log=console.print)
        except Exception as e:
            console.print(f"[red]connector {name} failed: {e}[/red]")
            stats = SyncStats()
            stats.errors = 1
            stats.notes.append(str(e))
        per_connector[name] = stats
        overall.merge(stats)

    table = Table(title="sync summary")
    table.add_column("connector")
    table.add_column("walked", justify="right")
    table.add_column("uploaded", justify="right", style="green")
    table.add_column("same", justify="right", style="dim")
    table.add_column("skip ext", justify="right", style="dim")
    table.add_column("errors", justify="right", style="red")
    table.add_column("bytes", justify="right")
    for name, s in per_connector.items():
        table.add_row(
            name, str(s.walked), str(s.uploaded), str(s.skipped_same),
            str(s.skipped_ext), str(s.errors), f"{s.bytes:,}",
        )
    console.print(table)
    for n, s in per_connector.items():
        for note in s.notes:
            console.print(f"  [dim]{n}: {note}[/dim]")

    if overall.errors:
        sys.exit(2)


if __name__ == "__main__":
    main()

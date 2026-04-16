"""`python scripts/bootstrap.py` — idempotently create all GCP resources.

What runs (in order, each step is a no-op if the resource exists):
  1. Enable required APIs
  2. Ensure the service account + roles + key
  3. Ensure the GCS bucket
  4. Ensure the Data Store
  5. Ensure the Search Engine

Safe to re-run after any failure; picks up where it left off.
"""
from __future__ import annotations

import _path  # noqa: F401
import sys
import time

import click
from rich.console import Console

from core import load_config
from bootstrap import (
    enable_apis,
    ensure_service_account,
    grant_project_roles,
    create_key_if_missing,
    ensure_bucket,
    ensure_data_store,
    ensure_engine,
)

console = Console()


@click.command()
@click.option("--skip-apis", is_flag=True, help="Skip the API-enable step.")
@click.option("--skip-sa", is_flag=True, help="Skip service-account + key work.")
@click.option("--sa-id", default="madison-sync-sa",
              help="Short name of the service account (without @project.iam...).")
def main(skip_apis: bool, skip_sa: bool, sa_id: str) -> None:
    cfg = load_config()
    console.rule(f"[bold]Bootstrapping {cfg.project_id}[/bold]")
    console.print(
        f"data store=[cyan]{cfg.data_store_id}[/cyan]  "
        f"engine=[cyan]{cfg.engine_id}[/cyan]  "
        f"bucket=[cyan]{cfg.bucket}[/cyan]  "
        f"location=[cyan]{cfg.location}[/cyan]"
    )
    t0 = time.time()

    if not skip_apis:
        console.print("\n[bold]1/5[/bold] APIs")
        enable_apis(cfg, log=console.print)

    if not skip_sa:
        console.print("\n[bold]2/5[/bold] Service account")
        email = ensure_service_account(cfg, sa_id, log=console.print)
        grant_project_roles(cfg, email, log=console.print)
        if cfg.sa_key_path:
            from pathlib import Path
            key_path = Path(cfg.sa_key_path)
            if not key_path.is_absolute():
                from core.config import REPO_ROOT
                key_path = REPO_ROOT / key_path
            create_key_if_missing(email, key_path, log=console.print)

    console.print("\n[bold]3/5[/bold] GCS bucket")
    ensure_bucket(cfg, log=console.print)

    console.print("\n[bold]4/5[/bold] Data Store")
    ensure_data_store(cfg, log=console.print)

    console.print("\n[bold]5/5[/bold] Engine")
    ensure_engine(cfg, log=console.print)

    console.rule(f"[green]done in {time.time() - t0:.1f}s[/green]")
    console.print(
        "\nNext:\n"
        "  [cyan]python scripts/sync.py[/cyan]    — pull data from enabled connectors\n"
        "  [cyan]python scripts/index.py[/cyan]   — extract metadata + inject to Vertex\n"
        "  [cyan]python scripts/query.py \"...\"[/cyan] — ask questions"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        console.print(f"[red]bootstrap failed:[/red] {e}")
        sys.exit(1)

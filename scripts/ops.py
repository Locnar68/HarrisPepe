"""`python scripts/ops.py [OP_NAME]` — check ImportDocuments operation status.

Without args: lists recent operations on the data store branch.
With an op name: prints detailed status.

Examples:
    python scripts/ops.py
    python scripts/ops.py projects/.../operations/import-documents-9104872345655301256
"""
from __future__ import annotations

import _path  # noqa: F401
import sys

import click
from rich.console import Console
from rich.table import Table

from core import load_config, document_client

console = Console()


@click.command()
@click.argument("op_name", required=False)
@click.option("--limit", default=10, show_default=True)
def main(op_name: str | None, limit: int) -> None:
    cfg = load_config()
    client = document_client(cfg)
    ops_client = client.transport.operations_client

    if op_name:
        op = ops_client.get_operation(name=op_name)
        console.rule(f"[bold]{op.name.split('/')[-1]}[/bold]")
        console.print(f"  name:   [cyan]{op.name}[/cyan]")
        console.print(f"  done:   [bold]{op.done}[/bold]")
        if op.error and op.error.message:
            console.print(f"  [red]error: {op.error.code} {op.error.message}[/red]")
        # Metadata has success_count / failure_count on ImportDocumentsMetadata
        if op.metadata and op.metadata.value:
            try:
                from google.cloud import discoveryengine_v1 as de
                md = de.ImportDocumentsMetadata.deserialize(op.metadata.value)
                console.print(f"  success: [green]{md.success_count}[/green]")
                console.print(f"  failure: [red]{md.failure_count}[/red]")
                if md.create_time:
                    console.print(f"  create: {md.create_time}")
                if md.update_time:
                    console.print(f"  update: {md.update_time}")
            except Exception as e:
                console.print(f"  [dim]could not parse metadata: {e}[/dim]")
        return

    # List recent operations on the branch.
    console.rule(f"[bold]Recent operations on {cfg.data_store_id}[/bold]")
    try:
        page = ops_client.list_operations(
            name=cfg.branch_name, filter_="", page_size=limit,
        )
    except TypeError:
        # Some client versions use `filter` instead of `filter_`
        page = ops_client.list_operations(
            name=cfg.branch_name, filter="", page_size=limit,
        )

    t = Table()
    t.add_column("operation", overflow="fold")
    t.add_column("done", justify="center")
    t.add_column("success", justify="right")
    t.add_column("failure", justify="right")
    n = 0
    for op in page.operations:
        n += 1
        if n > limit:
            break
        success = failure = ""
        if op.metadata and op.metadata.value:
            try:
                from google.cloud import discoveryengine_v1 as de
                md = de.ImportDocumentsMetadata.deserialize(op.metadata.value)
                success = str(md.success_count)
                failure = str(md.failure_count)
            except Exception:
                pass
        done_icon = "[green]✓[/green]" if op.done else "[yellow]…[/yellow]"
        t.add_row(op.name.split("/")[-1], done_icon, success, failure)
    console.print(t)
    if n == 0:
        console.print("[dim]no operations found[/dim]")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        console.print(f"[red]error:[/red] {e}")
        sys.exit(1)

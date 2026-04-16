"""`python scripts/query.py "..."` — ask questions of the indexed data.

Two modes:
  answer (default) — Gemini reads the top-ranked docs and gives a grounded
                     natural-language answer with citations.
  search           — raw ranked list of hits with metadata.

Filters:
  --property=15-Northridge
  --doc-type=permit
  --category=Permits
"""
from __future__ import annotations

import _path  # noqa: F401
import sys
import textwrap

import click
from google.api_core import exceptions as gax
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core import load_config
from vertex.search import search
from vertex.answer import answer

console = Console()


@click.command()
@click.argument("query", required=True)
@click.option("--mode", type=click.Choice(["answer", "search"]), default="answer",
              show_default=True)
@click.option("--property", "property_", default=None, help="Filter by property name.")
@click.option("--doc-type", default=None, help="legal|finance|permit|billing|image")
@click.option("--category", default=None, help="Permits|Financials|Photos|...")
@click.option("--page-size", default=10, show_default=True)
def main(query: str, mode: str, property_, doc_type, category, page_size: int) -> None:
    cfg = load_config()

    try:
        if mode == "answer":
            a = answer(cfg, query, property_=property_, doc_type=doc_type, category=category)
            console.print(Panel(
                textwrap.fill(a.text or "(no answer)", width=100),
                title=f"answer",
                border_style="green",
            ))
            if a.sources:
                console.print("\n[bold]sources[/bold]")
                for s in a.sources:
                    loc = f"{s['property']}/{s['category']}/{s['title']}".strip("/")
                    console.print(f"  [cyan]{s['reference_id']}[/cyan]  {loc}")
        else:
            hits = search(cfg, query,
                          property_=property_, doc_type=doc_type, category=category,
                          page_size=page_size)
            table = Table(title=f"search results")
            table.add_column("#", style="dim", width=3)
            table.add_column("property")
            table.add_column("doc_type")
            table.add_column("filename")
            table.add_column("uri", overflow="fold")
            for h in hits:
                table.add_row(str(h.rank), h.property, h.doc_type, h.filename, h.uri)
            console.print(table)
            if not hits:
                console.print("[yellow]no hits[/yellow]")
    except gax.NotFound as e:
        sys.exit(f"[error] {e.message}\nDid you run bootstrap + sync + index?")
    except gax.InvalidArgument as e:
        sys.exit(f"[error] {e.message}")


if __name__ == "__main__":
    main()

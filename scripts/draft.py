"""`python scripts/draft.py` — generate documents from templates + RAG.

Usage:
    python scripts/draft.py --list
    python scripts/draft.py property-summary --preview
    python scripts/draft.py property-summary -p 15-Northridge
    python scripts/draft.py property-summary -p 15-Northridge -o output/report.pdf
    python scripts/draft.py property-summary -p 15-Northridge -o output/report.docx
"""
from __future__ import annotations

import _path  # noqa: F401
import re
import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from core import load_config
from core.config import REPO_ROOT
from drafting.engine import DraftingEngine, load_query_map
from drafting.writer import write_markdown, write_docx, write_pdf

console = Console()
TEMPLATE_DIR = REPO_ROOT / "templates"
QUERIES_FILE = TEMPLATE_DIR / "queries.yaml"


def find_template(name):
    for ext in [".md", ".docx", ".txt", ""]:
        p = TEMPLATE_DIR / f"{name}{ext}"
        if p.exists(): return p
    return None


def list_templates():
    table = Table(title="Available Templates", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Fields", style="yellow")
    table.add_column("File", style="dim")
    for f in sorted(TEMPLATE_DIR.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        phs = sorted(set(re.findall(r"\{\{(.+?)\}\}", text)))
        table.add_row(f.stem, f"{len(phs)}", f.name)
    console.print(table)


def preview_template(template_path, query_map):
    text = template_path.read_text(encoding="utf-8")
    phs = sorted(set(re.findall(r"\{\{(.+?)\}\}", text)))
    table = Table(title=f"Placeholders in {template_path.name}", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Placeholder", style="cyan")
    table.add_column("Mode", style="yellow", width=7)
    table.add_column("Query", style="white")
    table.add_column("Filter", style="dim")
    for i, p in enumerate(phs, 1):
        spec = query_map.get(p)
        if spec: table.add_row(str(i), p, "mapped", spec.get("query", p), spec.get("doc_type", "-"))
        else: table.add_row(str(i), p, "smart", p.replace("_", " "), "-")
    console.print(table)
    console.print(f"\n  Total: {len(phs)} placeholders")


@click.command()
@click.argument("template", required=False)
@click.option("--property", "-p", "property_", default=None)
@click.option("--doc-type", "-d", default=None)
@click.option("--output", "-o", default=None, help="Output file (.md, .docx, or .pdf)")
@click.option("--delay", default=4.0, show_default=True)
@click.option("--list", "list_", is_flag=True)
@click.option("--preview", is_flag=True)
def main(template, property_, doc_type, output, delay, list_, preview):
    if list_:
        list_templates(); return

    if not template:
        console.print("[red]Specify a template name, or use --list.[/red]")
        list_templates(); sys.exit(1)

    template_path = find_template(template)
    if not template_path:
        console.print(f"[red]Template not found:[/red] {template}")
        list_templates(); sys.exit(1)

    query_map = load_query_map(QUERIES_FILE)
    if preview:
        preview_template(template_path, query_map); return

    cfg = load_config()
    if not property_: property_ = cfg.default_property
    if property_: console.print(f"  Property: [cyan]{property_}[/cyan]")

    template_text = template_path.read_text(encoding="utf-8")
    total = len(set(re.findall(r"\{\{(.+?)\}\}", template_text)))
    console.rule(f"[bold]Filling: {template_path.name}  ({total} fields, ~{total*delay:.0f}s est.)[/bold]")
    console.print(f"  Delay: {delay}s between queries\n")

    engine = DraftingEngine(cfg, property_=property_, doc_type=doc_type, delay=delay, log=console.print)
    start = time.time()
    filled, results = engine.fill(template_text, query_map)
    elapsed = time.time() - start

    table = Table(show_lines=True)
    table.add_column("Placeholder", style="cyan", max_width=25)
    table.add_column("", width=2)
    table.add_column("Answer (first 80 chars)", style="white", max_width=80)
    table.add_column("Sources", style="dim", max_width=30)
    ok = 0
    for r in results:
        status = "[green]Y[/green]" if r.success else "[red]X[/red]"
        table.add_row(r.placeholder, status, r.answer[:80]+("..." if len(r.answer)>80 else ""), ", ".join(r.sources[:3]) if r.sources else "-")
        if r.success: ok += 1

    console.print(); console.print(table)
    console.print(f"\n  Resolved: [{'green' if ok==len(results) else 'yellow'}]{ok}/{len(results)}[/] ({elapsed:.1f}s)")

    if not output:
        output = f"output/{template_path.stem}-filled.md"
    output_path = Path(output)
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output

    # Get branding from config.
    co = cfg.raw.get("company", {}) or {}
    logo = co.get("logo", "")
    if logo and not Path(logo).is_absolute():
        logo = str(REPO_ROOT / logo)

    if output_path.suffix == ".pdf":
        write_pdf(filled, output_path,
                  title=template_path.stem.replace("-"," ").title(),
                  company=co.get("name", ""),
                  phone=co.get("phone", ""),
                  email=co.get("email", ""),
                  address=co.get("address", ""),
                  website=co.get("website", ""),
                  tagline=co.get("tagline", ""),
                  logo_path=logo,
                  property_name=property_ or "")
        console.print(f"  [green]Wrote:[/green] {output_path}  (.pdf)")
    elif output_path.suffix == ".docx":
        write_docx(filled, output_path, title=template_path.stem)
        console.print(f"  [green]Wrote:[/green] {output_path}  (.docx)")
    else:
        write_markdown(filled, output_path)
        console.print(f"  [green]Wrote:[/green] {output_path}  (.md)")

    if ok < len(results):
        console.print(f"\n  [yellow]Tip:[/yellow] {len(results)-ok} unanswered. Wait a minute and re-run, or increase --delay.")
    console.print()


if __name__ == "__main__":
    main()

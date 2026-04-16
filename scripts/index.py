"""`python scripts/index.py` — walk GCS, build manifest, import to Vertex AI Search."""
from __future__ import annotations

import _path  # noqa: F401
import sys
from collections import Counter

import click
from rich.console import Console
from rich.table import Table

from core import load_config, storage_client
from ingestion.manifest import build_manifest, upload_manifest, write_manifest
from ingestion.inject import import_documents
from metadata.extractor import classify_strict, classify_heuristic

console = Console()


def _discover(cfg) -> dict:
    gcs = storage_client(cfg)
    bucket = gcs.bucket(cfg.bucket)

    seen_properties_strict: set[str] = set()
    skipped_categories: Counter[str] = Counter()
    strict_ok = 0
    heuristic_ok = 0
    unclassified = 0
    unclassified_samples: list[str] = []

    for blob in bucket.list_blobs(prefix=f"{cfg.mirror_prefix}/"):
        if blob.name.endswith("/"):
            continue
        strict = classify_strict(cfg, blob.name)
        if strict:
            strict_ok += 1
            seen_properties_strict.add(strict["property"])
            continue
        parts = blob.name.split("/")
        if (len(parts) >= 5 and parts[0] == cfg.mirror_prefix
                and parts[1] == "Properties"):
            seen_properties_strict.add(parts[2])
            if parts[3] not in cfg.category_folders:
                skipped_categories[parts[3]] += 1
        heur = classify_heuristic(cfg, blob.name)
        if heur:
            heuristic_ok += 1
        else:
            unclassified += 1
            if len(unclassified_samples) < 10:
                unclassified_samples.append(parts[-1])

    return {
        "strict": strict_ok,
        "heuristic": heuristic_ok,
        "unclassified": unclassified,
        "unclassified_samples": unclassified_samples,
        "seen_properties_strict": sorted(seen_properties_strict),
        "skipped_categories": dict(skipped_categories),
    }


@click.command()
@click.option("--full", is_flag=True,
              help="FULL reconciliation: delete Vertex docs missing from manifest.")
@click.option("--no-import", is_flag=True,
              help="Build + upload manifest, but skip the ImportDocuments step.")
@click.option("--no-wait", is_flag=True,
              help="Kick off the import and return immediately.")
@click.option("--local-manifest", type=click.Path(), default=None,
              help="Also write a local copy of manifest.jsonl to this path.")
@click.option("--discover", is_flag=True,
              help="Print a classifier report; don't modify anything.")
def main(full: bool, no_import: bool, no_wait: bool, local_manifest: str | None, discover: bool) -> None:
    cfg = load_config()
    console.rule(f"[bold]Indexing {cfg.data_store_id}[/bold]")

    if discover:
        d = _discover(cfg)
        t = Table(title="classifier report")
        t.add_column("bucket state")
        t.add_column("count", justify="right")
        t.add_row("matched by strict path classifier",        str(d["strict"]))
        t.add_row("matched by heuristic filename classifier", str(d["heuristic"]))
        t.add_row("unclassified (will NOT be indexed)",       str(d["unclassified"]))
        console.print(t)
        if d["seen_properties_strict"]:
            console.print(f"  properties seen via strict layout: {d['seen_properties_strict']}")
        if d["skipped_categories"]:
            console.print(f"  [yellow]unknown category folders (add to config.yaml → "
                          f"category_folders):[/yellow] {d['skipped_categories']}")
        if d["unclassified_samples"]:
            console.print(f"  [dim]unclassified samples:[/dim] {d['unclassified_samples']}")
            console.print("  [dim]→ add filename rules to metadata.heuristic_rules, "
                          "or organize into Properties/<prop>/<cat>/...[/dim]")
        console.print("")
        return

    records = build_manifest(cfg, log=console.print)
    if not records:
        console.print("[yellow]no documents classified — run "
                      "[cyan]python scripts/index.py --discover[/cyan] to see why.[/yellow]")
        sys.exit(1)

    by_prop: Counter[str] = Counter(r.structData["property"] for r in records)
    by_type: Counter[str] = Counter(r.structData["doc_type"] for r in records)
    console.print(f"  by property: {dict(by_prop)}")
    console.print(f"  by doc_type: {dict(by_type)}")

    if local_manifest:
        p = write_manifest(records, local_manifest)
        console.print(f"  local copy: [cyan]{p}[/cyan]")

    upload_manifest(cfg, records, log=console.print)

    if no_import:
        console.print("[yellow]--no-import given, stopping here[/yellow]")
        return

    if no_wait:
        result = import_documents(cfg, full=full, wait=False, log=console.print)
        op_name = result.get("op", "<op-name>")
        console.print(
            "\n[yellow]fire-and-forget.[/yellow] Check progress any of these ways:\n"
            f"  1. [cyan]python scripts/ops.py[/cyan]   (lists recent operations)\n"
            f"  2. [cyan]python scripts/ops.py {op_name}[/cyan]\n"
            f"  3. Browser: https://console.cloud.google.com/ai-applications/"
            f"data-stores/{cfg.data_store_id}/activity?project={cfg.project_id}"
        )
        return

    # Live heartbeat while the op runs server-side.
    with console.status("[cyan]waiting for import...[/cyan]", spinner="dots") as status:
        def _on_poll(p: dict) -> None:
            elapsed = p.get("elapsed", 0)
            s = p.get("success")
            f = p.get("failure")
            if p.get("done"):
                return
            status.update(
                f"[cyan]waiting for import "
                f"[dim]({elapsed:4.0f}s  success={s}  failure={f})[/dim][/cyan]"
            )
        result = import_documents(
            cfg, full=full, wait=True, log=console.print,
            on_poll=_on_poll, poll_interval_sec=3.0,
        )

    console.rule("[green]done[/green]")
    console.print(
        f"  elapsed={result.get('elapsed_sec')}s  "
        f"success=[green]{result.get('success')}[/green]  "
        f"failure=[red]{result.get('failure')}[/red]"
    )
    console.print(
        "\n[dim]Note: indexing has a 5–15 min settling lag after import completes. "
        "If a query returns nothing, wait and retry.[/dim]"
    )


if __name__ == "__main__":
    main()

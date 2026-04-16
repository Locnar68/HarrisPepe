"""`python scripts/doctor.py` — health check the whole stack.

Non-destructive. Prints green/yellow/red for each check."""
from __future__ import annotations

import _path  # noqa: F401
import os
import sys
from pathlib import Path

from google.api_core import exceptions as gax
from rich.console import Console

from core import (
    load_config,
    data_store_client,
    engine_client,
    storage_client,
)

console = Console()


def check(name: str, ok: bool, note: str = "") -> None:
    icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
    line = f"  {icon} {name}"
    if note:
        line += f" — [dim]{note}[/dim]"
    console.print(line)


def main() -> None:
    console.rule("[bold]doctor[/bold]")
    cfg = load_config()
    issues = 0

    # --- env ---
    check("config/config.yaml loaded", True,
          f"project={cfg.project_id}, loc={cfg.location}")

    adc = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if adc:
        p = Path(adc)
        ok = p.exists()
        check("GOOGLE_APPLICATION_CREDENTIALS file exists", ok, str(p))
        if not ok:
            issues += 1
    else:
        check("GOOGLE_APPLICATION_CREDENTIALS", True,
              "not set — using gcloud ADC")

    env_project = os.getenv("GOOGLE_CLOUD_PROJECT")
    check("GOOGLE_CLOUD_PROJECT matches config",
          env_project in (cfg.project_id, None),
          env_project or "not set")

    # --- bucket (via list, not buckets.get — objectAdmin is enough) ---
    try:
        gcs = storage_client(cfg)
        bucket = gcs.bucket(cfg.bucket)
        total = 0
        mirror_count = 0
        manifest_count = 0
        for b in bucket.list_blobs(max_results=10000):
            total += 1
            if b.name.startswith(f"{cfg.mirror_prefix}/"):
                mirror_count += 1
            elif b.name.startswith(f"{cfg.manifest_prefix}/"):
                manifest_count += 1
        check(
            f"GCS bucket gs://{cfg.bucket} readable", True,
            f"{total} total objects  "
            f"({mirror_count} under {cfg.mirror_prefix}/, "
            f"{manifest_count} under {cfg.manifest_prefix}/)"
        )
    except Exception as e:
        check(f"GCS bucket gs://{cfg.bucket}", False, str(e).splitlines()[0])
        issues += 1

    # --- data store ---
    try:
        ds = data_store_client(cfg).get_data_store(name=cfg.data_store_name)
        check(f"Data Store {cfg.data_store_id}", True, ds.display_name)
    except gax.NotFound:
        check(f"Data Store {cfg.data_store_id}", False, "not found")
        issues += 1
    except Exception as e:
        check(f"Data Store {cfg.data_store_id}", False, str(e).splitlines()[0])
        issues += 1

    # --- engine ---
    try:
        eng = engine_client(cfg).get_engine(name=cfg.engine_name)
        check(f"Engine {cfg.engine_id}", True, eng.display_name)
    except gax.NotFound:
        check(f"Engine {cfg.engine_id}", False, "not found")
        issues += 1
    except Exception as e:
        check(f"Engine {cfg.engine_id}", False, str(e).splitlines()[0])
        issues += 1

    # --- connectors ---
    enabled = cfg.enabled_connectors()
    check("enabled connectors", bool(enabled), ", ".join(enabled) or "none")

    # --- metadata mode ---
    heur = (cfg.raw.get("metadata", {}) or {}).get("heuristic_classification")
    if heur:
        n_rules = len((cfg.raw.get("metadata", {}) or {}).get("heuristic_rules", []) or [])
        check("classifier mode", True,
              f"heuristic (fallback) enabled with {n_rules} rules")
    else:
        check("classifier mode", True, "strict path-only")

    console.rule(
        f"[green]all green[/green]" if issues == 0
        else f"[red]{issues} issue(s) found[/red]"
    )
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()

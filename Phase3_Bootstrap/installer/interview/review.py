"""
Final review screen.

Displays the assembled config in a nicely-formatted table and asks the user
to confirm before we start mutating GCP.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from installer.config.schema import Phase3Config
from installer.utils import ui

_console = Console()


def run(cfg: Phase3Config) -> None:
    ui.section("2h — Review", "Everything we're about to create in GCP.")

    t = Table(show_header=True, header_style="bold cyan")
    t.add_column("Area", no_wrap=True)
    t.add_column("Setting", no_wrap=True)
    t.add_column("Value")

    t.add_row("Business", "Legal name", cfg.business.legal_name)
    t.add_row("", "Display name", cfg.business.display_name)
    t.add_row("", "Domain", cfg.business.domain)
    t.add_row("", "Industry", cfg.business.industry)
    t.add_row("Contact", "Name", cfg.contact.full_name)
    t.add_row("", "Email", cfg.contact.email)
    t.add_row("", "Phone", cfg.contact.phone or "(none)")
    t.add_row("GCP", "Project ID", cfg.gcp.project_id)
    t.add_row("", "Project exists", str(cfg.gcp.project_exists))
    t.add_row("", "Region", cfg.gcp.region)
    t.add_row("", "Billing account", cfg.gcp.billing_account_id or "(link later)")
    t.add_row("SA", "Short name", cfg.service_account.short_name)
    t.add_row("", "Email", cfg.service_account.email or "(derived)")
    t.add_row("Storage", "Raw bucket", cfg.storage.raw_bucket)
    t.add_row("", "Processed bucket", cfg.storage.processed_bucket)
    t.add_row("", "Archive bucket", cfg.storage.archive_bucket or "(none)")
    t.add_row("", "Storage class", cfg.storage.storage_class)
    t.add_row("Vertex", "Data store ID", cfg.vertex.data_store_id)
    t.add_row("", "Engine ID", cfg.vertex.engine_id)
    t.add_row("", "Tier", cfg.vertex.tier)
    t.add_row("", "Layout Parser", str(cfg.vertex.enable_layout_parser))

    for c in cfg.connectors:
        if not c.enabled:
            continue
        key_bits = []
        for k, v in c.options.items():
            if k in ("client_secret_value",):
                continue
            if isinstance(v, list):
                key_bits.append(f"{k}={len(v)} items")
            elif isinstance(v, str) and len(v) > 40:
                key_bits.append(f"{k}={v[:37]}...")
            else:
                key_bits.append(f"{k}={v}")
        t.add_row(f"Connector: {c.name}", "schedule", c.schedule_cron)
        t.add_row("", "options", ", ".join(key_bits) or "(none)")

    _console.print(t)

    if not ui.ask_bool(
        "Proceed and create these resources in GCP?",
        default=True,
    ):
        raise SystemExit(
            "Aborted by user before any GCP mutation. "
            "Re-run bootstrap.ps1 with --resume to restart from the interview."
        )

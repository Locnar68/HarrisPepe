"""Terminal banners: welcome, section headers, final summary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

_console = Console()

_BANNER = r"""
  ____  _                        _____
 |  _ \| |__   __ _ ___  ___    |___ /
 | |_) | '_ \ / _` / __|/ _ \     |_ \
 |  __/| | | | (_| \__ \  __/    ___) |
 |_|   |_| |_|\__,_|___/\___|   |____/
       Vertex AI RAG — turnkey bootstrap
"""


def print_banner() -> None:
    _console.print(f"[bold cyan]{_BANNER}[/]", highlight=False)
    _console.print(
        "[dim]Zero-assumption installer. Gmail + Google Drive connectors enabled.[/]\n"
    )


def print_section(title: str) -> None:
    _console.print(Panel.fit(title, style="bold green"))


def print_completion(cfg: Any, install_path: Path) -> None:
    """Final summary with next actions the operator must take by hand."""
    t = Table(title="Phase 3 — Bootstrap Summary", show_header=False, box=None)
    t.add_column("Key", style="bold cyan", no_wrap=True)
    t.add_column("Value")

    t.add_row("Company", cfg.business.display_name)
    t.add_row("GCP Project", cfg.gcp.project_id)
    t.add_row("Region", cfg.gcp.region)
    t.add_row("Data Store", cfg.vertex.data_store_id)
    t.add_row("Engine", cfg.vertex.engine_id)
    t.add_row("Tier", cfg.vertex.tier)
    t.add_row("Raw bucket", f"gs://{cfg.storage.raw_bucket}")
    t.add_row("Processed bucket", f"gs://{cfg.storage.processed_bucket}")
    if cfg.storage.archive_bucket:
        t.add_row("Archive bucket", f"gs://{cfg.storage.archive_bucket}")
    t.add_row("Service account", cfg.service_account.email)
    t.add_row("SA key file", str(install_path / "secrets" / "service-account.json"))
    t.add_row("Install path", str(install_path))

    enabled = [c.name for c in cfg.connectors if c.enabled]
    t.add_row("Connectors enabled", ", ".join(enabled) or "(none)")

    _console.print(t)

    # Next-action checklist
    _console.print()
    _console.print(Panel(
        _next_actions_text(cfg, install_path),
        title="Next actions (manual)",
        style="yellow",
    ))


def _next_actions_text(cfg: Any, install_path: Path) -> str:
    lines: list[str] = []
    sa_email = cfg.service_account.email
    step = 1

    gmail = cfg.connector("gmail")
    if gmail and gmail.enabled:
        lines.append(
            f"{step}. Complete Gmail OAuth setup (the project now exists, so the\n"
            "   console links will actually work):\n\n"
            f"   a. Open: https://console.cloud.google.com/apis/credentials/consent"
            f"?project={cfg.gcp.project_id}\n"
            "      - User type: External (for personal Gmail) or Internal (Workspace)\n"
            "      - Add scope: https://www.googleapis.com/auth/gmail.readonly\n"
            "      - (External only) add your Gmail as a Test User\n\n"
            f"   b. Open: https://console.cloud.google.com/apis/credentials"
            f"?project={cfg.gcp.project_id}\n"
            "      - Create OAuth 2.0 Client ID of type 'Desktop app'\n"
            "      - Download the client_secret JSON file\n"
            f"      - Save it as: {install_path / 'secrets' / 'gmail-oauth-client.json'}\n\n"
            "   c. Run the authorize helper:\n"
            "      python -m installer.connectors.gmail authorize\n"
            "      (A browser will open. Sign in as the mailbox owner.)"
        )
        step += 1

    gdrive = cfg.connector("gdrive")
    if gdrive and gdrive.enabled:
        folder_ids = gdrive.options.get("folder_ids", [])
        if folder_ids:
            lines.append(
                f"{step}. Share Drive folder (choose ONE method):\n"
                f"   \n"
                f"   EASIEST - Share with 'Anyone with the link' (Viewer):\n"
                + "\n".join(
                    f"   - Open: https://drive.google.com/drive/folders/{fid}"
                    for fid in folder_ids
                ) +
                "\n   - Click Share > Change to 'Anyone with the link' > Viewer > Done\n"
                f"   \n"
                f"   OR - Share directly with service account:\n"
                f"   - SA email: {sa_email}\n"
                f"   - Run: .\\share-drive-folder.ps1 (requires folder owner permissions)"
            )
        else:
            lines.append(
                f"{step}. Add Drive folders: edit config/config.yaml, put folder IDs\n"
                "   under connectors[name=gdrive].options.folder_ids, then\n"
                "   share each folder with the SA email (Viewer):\n"
                f"   SA email: {sa_email}"
            )
        step += 1

    lines.append(
        f"{step}. Verify end-to-end:\n"
        f"   python -m installer --verify --install-path {install_path}"
    )
    step += 1

    # Manual sync command for gdrive - REMOVED since auto-sync runs
    # Web UI will auto-launch, so no need to show manual command
    
    return "\n\n".join(lines)

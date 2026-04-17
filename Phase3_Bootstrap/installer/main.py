"""
installer.main — orchestrator
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
import webbrowser
import subprocess
from pathlib import Path
from typing import Optional
from threading import Timer

from installer import __version__
from installer.banner import print_banner, print_completion
from installer.logger import get_logger, setup_logging
from installer.state import BootstrapState, Step


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="installer",
        description="Phase 3 — Turnkey bootstrap for the Vertex AI RAG pipeline.",
    )
    p.add_argument("--install-path", default=None)
    p.add_argument("--config", default=None)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--non-interactive", action="store_true")
    p.add_argument("--skip-prereqs", action="store_true",
                   help="Skip host-machine prerequisite checks.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--version", action="version",
                   version=f"Phase 3 Bootstrap {__version__}")
    p.add_argument("--verbose", "-v", action="count", default=0)
    return p


def run(args: argparse.Namespace) -> int:
    install_path = Path(
        args.install_path or os.environ.get("PHASE3_HOME") or Path.cwd()
    ).resolve()
    (install_path / "config").mkdir(parents=True, exist_ok=True)
    (install_path / "secrets").mkdir(parents=True, exist_ok=True)
    (install_path / "state").mkdir(parents=True, exist_ok=True)
    (install_path / "logs").mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(install_path / "secrets", 0o700)
    except (OSError, NotImplementedError):
        pass

    setup_logging(install_path / "logs", verbose=args.verbose)
    log = get_logger(__name__)
    log.info("Phase 3 Bootstrap v%s starting", __version__)
    log.info("Install path: %s", install_path)

    print_banner()

    state = BootstrapState(install_path / "state" / "bootstrap.state.json")
    if args.resume:
        state.load()
        log.info("Resuming. Last completed step: %s",
                 state.last_completed_step or "(none)")
    else:
        state.reset(keep_config=bool(args.config))

    if args.verify:
        from installer.gcp import verification
        return verification.run(state, install_path)

    # ---- Step 1 — prereqs ----
    if not state.is_done(Step.PREREQS):
        if args.skip_prereqs:
            log.info("Skipping host prereq checks (--skip-prereqs).")
            from installer.utils import ui
            ui.section("Step 1 — Host prerequisites (skipped)",
                       "Called with --skip-prereqs. "
                       "Assuming Python + gcloud + git are all present.")
        else:
            from installer.prereqs import run_checks
            run_checks(non_interactive=args.non_interactive)
        state.mark_done(Step.PREREQS)

    # ---- Step 2 — interview / load config ----
    from installer.config.loader import load_config, save_config
    from installer.interview.runner import run_interview

    config_path = install_path / "config" / "config.yaml"

    if args.config:
        cfg = load_config(Path(args.config))
        save_config(cfg, config_path)
    elif config_path.exists() and state.is_done(Step.INTERVIEW):
        cfg = load_config(config_path)
    else:
        cfg = run_interview(
            state=state,
            install_path=install_path,
            non_interactive=args.non_interactive,
        )
        save_config(cfg, config_path)
        state.mark_done(Step.INTERVIEW)

    state.config = cfg
    state.save()

    from installer.gcp import auth as gcp_auth
    if not state.is_done(Step.GCP_AUTH):
        gcp_auth.ensure_login(cfg, dry_run=args.dry_run)
        state.mark_done(Step.GCP_AUTH)

    from installer.gcp import projects
    if not state.is_done(Step.PROJECT):
        projects.ensure_project(cfg, dry_run=args.dry_run)
        state.mark_done(Step.PROJECT)

    from installer.gcp import billing
    if not state.is_done(Step.BILLING):
        billing.ensure_billing(cfg, dry_run=args.dry_run,
                               non_interactive=args.non_interactive)
        state.mark_done(Step.BILLING)

    from installer.gcp import apis
    if not state.is_done(Step.APIS):
        apis.enable_apis(cfg, dry_run=args.dry_run)
        state.mark_done(Step.APIS)

    from installer.gcp import service_accounts
    if not state.is_done(Step.SERVICE_ACCOUNT):
        service_accounts.ensure_service_account(
            cfg, install_path=install_path, dry_run=args.dry_run
        )
        state.mark_done(Step.SERVICE_ACCOUNT)

    from installer.gcp import gcs
    if not state.is_done(Step.GCS):
        gcs.ensure_buckets(cfg, dry_run=args.dry_run)
        state.mark_done(Step.GCS)

    from installer.gcp import secret_manager
    if not state.is_done(Step.SECRETS):
        secret_manager.ensure_secrets(cfg, install_path=install_path,
                                      dry_run=args.dry_run)
        state.mark_done(Step.SECRETS)

    from installer.gcp import data_store
    if not state.is_done(Step.DATA_STORE):
        data_store.ensure_data_store(cfg, dry_run=args.dry_run)
        state.mark_done(Step.DATA_STORE)

    from installer.gcp import engine
    if not state.is_done(Step.ENGINE):
        engine.ensure_engine(cfg, dry_run=args.dry_run)
        state.mark_done(Step.ENGINE)

    from installer.connectors import configure_selected
    if not state.is_done(Step.CONNECTORS):
        configure_selected(cfg, install_path=install_path, dry_run=args.dry_run,
                           non_interactive=args.non_interactive)
        state.mark_done(Step.CONNECTORS)

    from installer.gcp import report as _report
    if not state.is_done(Step.REPORT):
        _report.emit(cfg, install_path=install_path)
        state.mark_done(Step.REPORT)

    # Auto-trigger initial Drive sync if enabled
    from installer.utils import shell, ui
    gdrive = cfg.connector("gdrive")
    if gdrive and gdrive.enabled and not args.dry_run:
        job_name = f"{cfg.business.display_name}-gdrive-sync"[:63]
        ui.note(f"\n🔄 Triggering initial Drive sync: {job_name}")
        res = shell.run(
            ["gcloud", "run", "jobs", "execute", job_name,
             f"--region={cfg.gcp.region}",
             f"--project={cfg.gcp.project_id}"],
            check=False, timeout=30
        )
        if res.ok:
            ui.success("Initial sync started! Documents will appear in ~2-5 minutes.")
        else:
            ui.warn(f"Sync trigger failed: {res.stderr.strip()[:200]}")
            ui.note(f"Run manually: gcloud run jobs execute {job_name} --region {cfg.gcp.region}")

    print_completion(cfg, install_path)
    log.info("Phase 3 bootstrap complete.")

    # Auto-launch web UI
    if not args.dry_run:
        # FIX: Use .parent instead of .parent.parent
        # install_path = D:\LAB\DELETE3\Phase3_Bootstrap
        # install_path.parent = D:\LAB\DELETE3
        # web_script = D:\LAB\DELETE3\scripts\simple_web.py
        web_script = install_path.parent / "scripts" / "simple_web.py"
        if web_script.exists():
            ui.note(f"\n🚀 Launching web UI at http://localhost:5000")
            ui.note("Press Ctrl+C in the web UI window to stop it.\n")
            
            # Open browser after 2 seconds
            Timer(2.0, lambda: webbrowser.open("http://localhost:5000")).start()
            
            # Launch web server (this will block until Ctrl+C)
            try:
                subprocess.run([sys.executable, str(web_script)], check=False)
            except KeyboardInterrupt:
                ui.note("\nWeb UI stopped.")
        else:
            ui.warn(f"Web UI not found at {web_script}")

    return 0


def cli(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nInterrupted. State saved — re-run with --resume.")
        return 130
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        log = get_logger(__name__)
        log.exception("Fatal error during bootstrap: %s", e)
        print(f"\n[fatal] {type(e).__name__}: {e}")
        print("See the log in <install-path>/logs/ for details.")
        print("Re-run with --resume once the cause is fixed.")
        if os.environ.get("PHASE3_DEBUG"):
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(cli())

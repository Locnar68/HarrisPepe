"""`python scripts/deploy.py` — deploy the sync pipeline to Cloud Run + Cloud Scheduler.

Steps:
  1. Deploy the Cloud Run service (builds container from source)
  2. Get the service URL
  3. Create or update the Cloud Scheduler job at the configured interval
  4. Print verification commands

The polling interval is read from config.yaml → cloud_run.poll_interval_minutes.

Usage:
    python scripts/deploy.py                # full deploy + schedule
    python scripts/deploy.py --schedule-only  # just update the cron schedule
    python scripts/deploy.py --trigger       # manually trigger one run now
    python scripts/deploy.py --logs          # tail Cloud Run logs
"""
from __future__ import annotations

import _path  # noqa: F401
import json
import subprocess
import sys

import click
from rich.console import Console

from core import load_config

console = Console()


def _gcloud(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["gcloud", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and result.returncode != 0:
        console.print(f"[red]gcloud failed:[/red] {result.stderr.strip()}")
    return result


def _cron_from_minutes(minutes: int) -> str:
    """Convert a polling interval in minutes to a cron expression."""
    if minutes <= 0:
        raise ValueError("poll_interval_minutes must be > 0")
    if minutes < 60:
        return f"*/{minutes} * * * *"       # every N minutes
    hours = minutes // 60
    if hours < 24:
        return f"0 */{hours} * * *"         # every N hours
    days = hours // 24
    return f"0 0 */{days} * *"              # every N days


@click.command()
@click.option("--schedule-only", is_flag=True, help="Only create/update the Scheduler job.")
@click.option("--trigger", is_flag=True, help="Manually trigger one sync run now.")
@click.option("--logs", is_flag=True, help="Tail Cloud Run logs and exit.")
@click.option("--teardown", is_flag=True, help="Delete the Cloud Run service + Scheduler job.")
def main(schedule_only: bool, trigger: bool, logs: bool, teardown: bool) -> None:
    cfg = load_config()
    cr = cfg.raw.get("cloud_run", {}) or {}

    service   = cr.get("service_name", "smb-sync")
    region    = cr.get("region", "us-central1")
    memory    = cr.get("memory", "1Gi")
    cpu       = str(cr.get("cpu", 2))
    timeout   = str(cr.get("timeout", 1800))
    max_inst  = str(cr.get("max_instances", 1))
    interval  = int(cr.get("poll_interval_minutes", 60))
    sched_job = cr.get("scheduler_job_name", f"{service}-cron")
    sa_email  = cfg.sa_email or f"sync-sa@{cfg.project_id}.iam.gserviceaccount.com"

    cron_expr = _cron_from_minutes(interval)

    # ---- logs mode ----
    if logs:
        console.print(f"[cyan]tailing logs for {service} in {region}...[/cyan]")
        subprocess.run([
            "gcloud", "run", "services", "logs", "tail", service,
            f"--region={region}", f"--project={cfg.project_id}",
        ])
        return

    # ---- teardown mode ----
    if teardown:
        if not click.confirm(f"Delete Cloud Run service '{service}' and Scheduler job '{sched_job}'?"):
            return
        console.print("[yellow]deleting scheduler job...[/yellow]")
        _gcloud(["scheduler", "jobs", "delete", sched_job,
                 f"--location={region}", f"--project={cfg.project_id}", "--quiet"], check=False)
        console.print("[yellow]deleting cloud run service...[/yellow]")
        _gcloud(["run", "services", "delete", service,
                 f"--region={region}", f"--project={cfg.project_id}", "--quiet"], check=False)
        console.print("[green]done[/green]")
        return

    # ---- trigger mode ----
    if trigger:
        # Check if scheduler job exists first.
        res = _gcloud(["scheduler", "jobs", "describe", sched_job,
                       f"--location={region}", f"--project={cfg.project_id}",
                       "--format=value(name)"], check=False)
        if res.returncode == 0:
            console.print(f"[cyan]triggering {sched_job}...[/cyan]")
            _gcloud(["scheduler", "jobs", "run", sched_job,
                     f"--location={region}", f"--project={cfg.project_id}"])
            console.print("[green]triggered[/green] — watch with: python scripts/deploy.py --logs")
        else:
            # No scheduler job; call the service URL directly.
            res = _gcloud(["run", "services", "describe", service,
                           f"--region={region}", f"--project={cfg.project_id}",
                           "--format=value(status.url)"])
            if res.returncode != 0:
                console.print("[red]service not deployed yet[/red]")
                return
            url = res.stdout.strip()
            console.print(f"[cyan]POST {url}/run ...[/cyan]")
            import urllib.request
            req = urllib.request.Request(f"{url}/run", method="POST")
            # This won't have auth — suggest using curl with an identity token instead.
            console.print(
                "[yellow]direct POST requires auth. Use:[/yellow]\n"
                f'  curl -X POST -H "Authorization: Bearer $(gcloud auth print-identity-token)" {url}/run'
            )
        return

    # ---- deploy ----
    if not schedule_only:
        console.rule(f"[bold]Deploying {service} to Cloud Run ({region})[/bold]")
        console.print(f"  SA:       {sa_email}")
        console.print(f"  memory:   {memory}   cpu: {cpu}   timeout: {timeout}s")
        console.print(f"  interval: every {interval} min (cron: {cron_expr})")
        console.print("")

        from core.config import REPO_ROOT
        console.print("[cyan]building + deploying (this takes 2-5 min)...[/cyan]")
        res = _gcloud([
            "run", "deploy", service,
            "--source", str(REPO_ROOT),
            f"--region={region}",
            "--no-allow-unauthenticated",
            f"--service-account={sa_email}",
            f"--set-env-vars=GOOGLE_CLOUD_PROJECT={cfg.project_id}",
            f"--timeout={timeout}",
            f"--memory={memory}",
            f"--cpu={cpu}",
            f"--max-instances={max_inst}",
            "--concurrency=1",
            f"--project={cfg.project_id}",
        ])
        if res.returncode != 0:
            sys.exit(1)
        console.print("[green]deploy complete[/green]")

    # ---- scheduler ----
    console.rule(f"[bold]Configuring Cloud Scheduler ({cron_expr})[/bold]")

    # Get service URL.
    res = _gcloud(["run", "services", "describe", service,
                   f"--region={region}", f"--project={cfg.project_id}",
                   "--format=value(status.url)"])
    if res.returncode != 0:
        console.print("[red]couldn't get service URL — is the service deployed?[/red]")
        sys.exit(1)
    run_url = res.stdout.strip()
    console.print(f"  service URL: [cyan]{run_url}[/cyan]")

    # Check if job exists.
    exists = _gcloud(["scheduler", "jobs", "describe", sched_job,
                      f"--location={region}", f"--project={cfg.project_id}",
                      "--format=value(name)"], check=False)

    if exists.returncode == 0:
        console.print(f"  [skip] scheduler job {sched_job} exists — updating schedule")
        _gcloud([
            "scheduler", "jobs", "update", "http", sched_job,
            f"--location={region}",
            f"--project={cfg.project_id}",
            f"--schedule={cron_expr}",
            f"--uri={run_url}/run",
            "--http-method=POST",
            f"--oidc-service-account-email={sa_email}",
            f"--attempt-deadline={timeout}s",
        ])
    else:
        console.print(f"  [...] creating scheduler job {sched_job}")
        _gcloud([
            "scheduler", "jobs", "create", "http", sched_job,
            f"--location={region}",
            f"--project={cfg.project_id}",
            f"--schedule={cron_expr}",
            f"--uri={run_url}/run",
            "--http-method=POST",
            f"--oidc-service-account-email={sa_email}",
            f"--attempt-deadline={timeout}s",
        ])

    console.rule("[green]deployed[/green]")
    console.print(
        f"\n  Service:   {run_url}"
        f"\n  Schedule:  every {interval} min (cron: {cron_expr})"
        f"\n  Job name:  {sched_job}"
        f"\n"
        f"\n  [cyan]python scripts/deploy.py --trigger[/cyan]   — run once now"
        f"\n  [cyan]python scripts/deploy.py --logs[/cyan]      — watch output"
        f"\n  [cyan]python scripts/deploy.py --teardown[/cyan]  — delete everything"
        f"\n"
    )


if __name__ == "__main__":
    main()

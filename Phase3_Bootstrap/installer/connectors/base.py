"""
Base helpers shared by all connector configurators.

Every connector lands as:

    * A Cloud Run *Job* (not a service — jobs are the right fit for
      cron-triggered sync workers).
    * A Cloud Scheduler entry that invokes the job on the configured cron.

We don't actually build and push the container image from this installer —
that's a one-time CI concern. Instead we reference a published image that
the Harris team controls. For Phase 3 we configure the job with a *placeholder*
image (``gcr.io/cloudrun/hello``) and print instructions telling the operator
to swap in the real image once CI is set up.
"""

from __future__ import annotations

import logging

from installer.config.schema import ConnectorConfig, Phase3Config
from installer.utils import shell, ui

log = logging.getLogger(__name__)

# A harmless placeholder — operator replaces after first CI build
PLACEHOLDER_IMAGE = "gcr.io/cloudrun/hello"


def deploy_cloud_run_job(
    cfg: Phase3Config,
    conn: ConnectorConfig,
    *,
    job_name: str,
    env_vars: dict[str, str],
    dry_run: bool,
) -> None:
    """Create (or update) a Cloud Run job for this connector."""
    env_args = []
    for k, v in env_vars.items():
        env_args += ["--set-env-vars", f"{k}={v}"]

    # Idempotent: describe first; update if exists, create otherwise.
    exists_res = shell.run(
        ["gcloud", "run", "jobs", "describe", job_name,
         f"--region={cfg.gcp.region}",
         f"--project={cfg.gcp.project_id}"],
        check=False, timeout=30, dry_run=dry_run,
    )
    action = "update" if (not dry_run and exists_res.ok) else "create"

    args = ["gcloud", "run", "jobs", action, job_name,
            f"--image={PLACEHOLDER_IMAGE}",
            f"--region={cfg.gcp.region}",
            f"--project={cfg.gcp.project_id}",
            f"--service-account={cfg.service_account.email}",
            "--max-retries=3",
            "--task-timeout=3600",
            *env_args]

    res = shell.run(args, check=False, timeout=180, dry_run=dry_run)
    if dry_run:
        ui.note(f"[dry-run] would {action} Cloud Run job '{job_name}'")
        return
    if not res.ok:
        ui.warn(f"{action} Cloud Run job '{job_name}' failed: "
                f"{res.stderr.strip()[:200]}")
        return
    ui.success(f"Cloud Run job {action}d: {job_name}")
    ui.note(f"Image is the placeholder '{PLACEHOLDER_IMAGE}'. "
            f"Replace with your real image once CI is ready:")
    ui.note(f"  gcloud run jobs update {job_name} --image=<your-image> "
            f"--region={cfg.gcp.region} --project={cfg.gcp.project_id}")


def deploy_scheduler(
    cfg: Phase3Config,
    conn: ConnectorConfig,
    *,
    scheduler_name: str,
    job_name: str,
    dry_run: bool,
) -> None:
    """Create (or update) a Cloud Scheduler entry that invokes the Cloud Run job."""
    pn = cfg.gcp.project_number or cfg.gcp.project_id
    uri = (
        f"https://{cfg.gcp.region}-run.googleapis.com/apis/run.googleapis.com"
        f"/v1/namespaces/{pn}/jobs/{job_name}:run"
    )

    describe = shell.run(
        ["gcloud", "scheduler", "jobs", "describe", scheduler_name,
         f"--location={cfg.gcp.region}",
         f"--project={cfg.gcp.project_id}"],
        check=False, timeout=30, dry_run=dry_run,
    )
    action = "update" if (not dry_run and describe.ok) else "create"

    args = ["gcloud", "scheduler", "jobs", f"{action}", "http", scheduler_name,
            f"--location={cfg.gcp.region}",
            f"--project={cfg.gcp.project_id}",
            f"--schedule={conn.schedule_cron}",
            f"--uri={uri}",
            "--http-method=POST",
            f"--oauth-service-account-email={cfg.service_account.email}",
            "--oauth-token-scope=https://www.googleapis.com/auth/cloud-platform"]

    res = shell.run(args, check=False, timeout=120, dry_run=dry_run)
    if dry_run:
        ui.note(f"[dry-run] would {action} scheduler '{scheduler_name}' "
                f"with cron '{conn.schedule_cron}'")
        return
    if not res.ok:
        ui.warn(f"scheduler {action} '{scheduler_name}' failed: "
                f"{res.stderr.strip()[:200]}")
        return
    ui.success(f"Scheduler {action}d: {scheduler_name} ({conn.schedule_cron})")

"""
Google Drive connector — configure Cloud Run job + Scheduler.

For Phase 3 we ship the service-account mode (Workspace + personal Gmail
compatible). OAuth-delegated mode shares the job and env layout but needs
the extra OAuth dance which lives in oauth_helper.py (Phase 3.1).
"""

from __future__ import annotations

import logging
from pathlib import Path

from installer.config.schema import ConnectorConfig, Phase3Config
from installer.connectors.base import deploy_cloud_run_job, deploy_scheduler
from installer.utils import ui

log = logging.getLogger(__name__)


def configure(
    cfg: Phase3Config,
    conn: ConnectorConfig,
    *,
    install_path: Path,
    dry_run: bool = False,
) -> None:
    ui.note(f"Configuring Google Drive connector (mode: {conn.options.get('mode')}, "
            f"schedule: {conn.schedule_cron})")

    job = f"{cfg.business.display_name}-gdrive-sync"[:63]
    sched = f"{cfg.business.display_name}-gdrive-sched"[:128]

    env_vars = {
        "GCP_PROJECT_ID": cfg.gcp.project_id,
        "COMPANY_NAME": cfg.business.display_name,
        "GCS_BUCKET_RAW": cfg.storage.raw_bucket,
        "GCS_BUCKET_PROCESSED": cfg.storage.processed_bucket,
        "VERTEX_DATA_STORE_ID": cfg.vertex.data_store_id,
        "GDRIVE_MODE": conn.options.get("mode", "service_account"),
        "GDRIVE_DRIVE_TYPE": conn.options.get("drive_type", "my_drive"),
        "GDRIVE_FOLDER_IDS": ",".join(conn.options.get("folder_ids", [])),
        "GDRIVE_MIME_ALLOWLIST": ",".join(conn.options.get("mime_allowlist", [])),
    }

    deploy_cloud_run_job(cfg, conn, job_name=job, env_vars=env_vars, dry_run=dry_run)
    deploy_scheduler(cfg, conn, scheduler_name=sched, job_name=job, dry_run=dry_run)

    folder_ids = conn.options.get("folder_ids", [])
    if folder_ids:
        ui.warn("IMPORTANT: you must share each target Drive folder with "
                f"{cfg.service_account.email} (Viewer role) or the sync will "
                "see zero files.")
        for fid in folder_ids:
            ui.note(f"  https://drive.google.com/drive/folders/{fid}")

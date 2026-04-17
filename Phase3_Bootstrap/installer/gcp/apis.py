"""
Enable all required Google APIs on the project.

Billed enablement can take 30-120 seconds per API; we batch to one gcloud
call which is atomic and faster.
"""

from __future__ import annotations

import logging

from installer.config.schema import Phase3Config
from installer.utils import shell, ui

log = logging.getLogger(__name__)

# All APIs the Phase 3 pipeline touches
REQUIRED_APIS = [
    "discoveryengine.googleapis.com",     # Vertex AI Search
    "aiplatform.googleapis.com",          # Vertex AI (Gemini)
    "storage.googleapis.com",             # GCS
    "secretmanager.googleapis.com",       # Secret Manager
    "cloudbuild.googleapis.com",          # Cloud Build (for Cloud Run jobs)
    "run.googleapis.com",                 # Cloud Run
    "cloudscheduler.googleapis.com",      # Cloud Scheduler (incremental sync)
    "iam.googleapis.com",                 # IAM
    "iamcredentials.googleapis.com",      # SA key creation / impersonation
    "cloudresourcemanager.googleapis.com",# Project management
    "serviceusage.googleapis.com",        # Enable-APIs API (chicken-and-egg sometimes)
    "logging.googleapis.com",             # Cloud Logging
    "gmail.googleapis.com",               # Gmail connector
    "drive.googleapis.com",               # Drive connector
]


def enable_apis(cfg: Phase3Config, *, dry_run: bool = False) -> None:
    ui.section("Step 6 — Enable APIs",
               f"Enabling {len(REQUIRED_APIS)} APIs on {cfg.gcp.project_id}. "
               "This can take up to 2 minutes.")

    cmd = ["gcloud", "services", "enable", *REQUIRED_APIS,
           f"--project={cfg.gcp.project_id}"]

    res = shell.run(cmd, check=False, timeout=300, dry_run=dry_run)
    if dry_run:
        for a in REQUIRED_APIS:
            ui.note(f"[dry-run] would enable {a}")
        return
    if not res.ok:
        raise RuntimeError(f"Failed to enable APIs:\n{res.stderr}")

    for a in REQUIRED_APIS:
        ui.success(f"enabled: {a}")

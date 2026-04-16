"""Enable the GCP APIs the pipeline depends on."""
from __future__ import annotations

from core import service_usage_client
from core.config import Config

REQUIRED_APIS = [
    "discoveryengine.googleapis.com",
    "storage.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "iam.googleapis.com",
    "drive.googleapis.com",
    "gmail.googleapis.com",
    "serviceusage.googleapis.com",
]


def enable_apis(cfg: Config, log=print) -> list[str]:
    """Enable any APIs not already enabled. Returns the list it actually enabled."""
    client = service_usage_client()
    parent = f"projects/{cfg.project_id}"
    newly_enabled = []
    for api in REQUIRED_APIS:
        name = f"{parent}/services/{api}"
        try:
            state = client.get_service(request={"name": name}).state.name
        except Exception:
            state = "STATE_UNSPECIFIED"
        if state == "ENABLED":
            log(f"  [skip] {api} (already enabled)")
            continue
        log(f"  [...] enabling {api}")
        op = client.enable_service(request={"name": name})
        op.result(timeout=300)
        newly_enabled.append(api)
        log(f"  [ok]   {api}")
    return newly_enabled

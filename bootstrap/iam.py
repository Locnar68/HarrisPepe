"""Service account management — create, grant roles, download key."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from core.config import Config

DEFAULT_SA_ROLES = [
    "roles/discoveryengine.editor",
    "roles/storage.objectAdmin",
]


def _gcloud(args: list[str]) -> subprocess.CompletedProcess:
    """Run gcloud, returning CompletedProcess. Uses text mode + utf-8."""
    return subprocess.run(
        ["gcloud", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def ensure_service_account(cfg: Config, sa_id: str, log=print) -> str:
    """Create the SA if missing. Returns the SA email."""
    email = f"{sa_id}@{cfg.project_id}.iam.gserviceaccount.com"
    res = _gcloud([
        "iam", "service-accounts", "describe", email,
        f"--project={cfg.project_id}",
        "--format=value(email)",
    ])
    if res.returncode == 0 and res.stdout.strip():
        log(f"  [skip] service account {email} (already exists)")
        return email

    log(f"  [...] creating service account {sa_id}")
    res = _gcloud([
        "iam", "service-accounts", "create", sa_id,
        f"--project={cfg.project_id}",
        f"--display-name=SMB Bootstrapper Sync",
    ])
    if res.returncode != 0:
        raise RuntimeError(f"failed to create SA: {res.stderr}")
    log(f"  [ok]   {email}")
    return email


def grant_project_roles(cfg: Config, sa_email: str, roles=DEFAULT_SA_ROLES, log=print) -> None:
    member = f"serviceAccount:{sa_email}"
    for role in roles:
        log(f"  [...] binding {role} to {sa_email}")
        res = _gcloud([
            "projects", "add-iam-policy-binding", cfg.project_id,
            f"--member={member}",
            f"--role={role}",
            "--condition=None",
        ])
        if res.returncode != 0:
            raise RuntimeError(f"failed to bind {role}: {res.stderr}")
        log(f"  [ok]   {role}")


def create_key_if_missing(sa_email: str, key_path: Path, log=print) -> Path:
    key_path = Path(key_path)
    if key_path.exists():
        # Validate it's actually for this SA.
        try:
            with key_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("client_email") == sa_email:
                log(f"  [skip] key {key_path} (exists and matches {sa_email})")
                return key_path
            log(f"  [warn] {key_path} is for {data.get('client_email')!r}, not {sa_email}")
        except Exception as e:
            log(f"  [warn] couldn't read {key_path}: {e}")

    key_path.parent.mkdir(parents=True, exist_ok=True)
    log(f"  [...] downloading new key to {key_path}")
    res = _gcloud([
        "iam", "service-accounts", "keys", "create", str(key_path),
        f"--iam-account={sa_email}",
    ])
    if res.returncode != 0:
        raise RuntimeError(f"failed to create key: {res.stderr}")
    log(f"  [ok]   {key_path}")
    return key_path

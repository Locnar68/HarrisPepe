"""GCS bucket — ensure it exists, create if missing."""
from __future__ import annotations

from core import storage_client
from core.config import Config


def ensure_bucket(cfg: Config, location: str = "US", log=print) -> None:
    gcs = storage_client(cfg)
    bucket = gcs.bucket(cfg.bucket)
    if bucket.exists():
        log(f"  [skip] gs://{cfg.bucket} (already exists)")
        return
    log(f"  [...] creating gs://{cfg.bucket}")
    new = gcs.create_bucket(cfg.bucket, location=location)
    new.iam_configuration.uniform_bucket_level_access_enabled = True
    new.patch()
    log(f"  [ok]   gs://{cfg.bucket}")

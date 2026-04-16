"""Local filesystem connector — mirror a local directory tree into GCS.

Real implementation (not a stub — simple enough to ship).
Config:
  connectors.local_files.enabled: true
  connectors.local_files.path: "D:\\Madison Files"
  connectors.local_files.mirror_as: "Properties"
"""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from core import storage_client
from connectors.base import Connector, SyncStats
from connectors.drive import INDEXABLE  # same allowlist


def _md5(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        while True:
            data = fh.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


class LocalFilesConnector(Connector):
    name = "local_files"

    def sync(self, dry_run: bool = False, force: bool = False, log=print) -> SyncStats:
        stats = SyncStats()
        root = self.c.get("path")
        if not root:
            raise RuntimeError("local_files connector requires 'path'")
        root_path = Path(root)
        if not root_path.exists():
            raise RuntimeError(f"local path not found: {root_path}")

        mirror_as = self.c.get("mirror_as", "Properties").strip("/")
        gcs_base = self.gcs_base(mirror_as)

        gcs = storage_client(self.cfg)
        bucket = gcs.bucket(self.cfg.bucket)

        existing: dict[str, str] = {}
        for blob in bucket.list_blobs(prefix=gcs_base + "/"):
            meta = blob.metadata or {}
            existing[blob.name] = meta.get("source_mtime", "")

        log(f"  local root: {root_path}")
        log(f"  gcs target: gs://{self.cfg.bucket}/{gcs_base}")

        for f in root_path.rglob("*"):
            if not f.is_file():
                continue
            stats.walked += 1
            ext = f.suffix.lower()
            if ext not in INDEXABLE:
                stats.skipped_ext += 1
                continue

            rel = PurePosixPath(*f.relative_to(root_path).parts)
            gcs_name = f"{gcs_base}/{rel}"
            mtime = str(int(f.stat().st_mtime))

            if not force and existing.get(gcs_name) == mtime:
                stats.skipped_same += 1
                continue

            if dry_run:
                log(f"  [dry] {rel}")
                stats.uploaded += 1
                continue

            try:
                data = f.read_bytes()
            except Exception as e:
                stats.errors += 1
                log(f"  [err] {rel}: {e}")
                continue

            blob = bucket.blob(gcs_name)
            blob.metadata = {
                "source": "local_files",
                "source_id": _md5(f),
                "source_mtime": mtime,
            }
            blob.upload_from_string(data)
            stats.uploaded += 1
            stats.bytes += len(data)
            log(f"  [up]  {rel} ({len(data):,} B)")

        return stats

"""Connector abstract base — the contract every data source implements."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from core.config import Config


@dataclass
class SyncStats:
    walked: int = 0
    uploaded: int = 0
    skipped_same: int = 0
    skipped_ext: int = 0
    errors: int = 0
    bytes: int = 0
    notes: list[str] = field(default_factory=list)

    def merge(self, other: "SyncStats") -> None:
        self.walked += other.walked
        self.uploaded += other.uploaded
        self.skipped_same += other.skipped_same
        self.skipped_ext += other.skipped_ext
        self.errors += other.errors
        self.bytes += other.bytes
        self.notes.extend(other.notes)

    def as_dict(self) -> dict:
        return {
            "walked": self.walked,
            "uploaded": self.uploaded,
            "skipped_same": self.skipped_same,
            "skipped_ext": self.skipped_ext,
            "errors": self.errors,
            "bytes": self.bytes,
            "notes": self.notes,
        }


class Connector(ABC):
    """A data source that pulls content and uploads it to GCS.

    Contract:
      - `name` is the key under `connectors:` in config.yaml
      - `sync()` is called by scripts/sync.py
      - Output goes to gs://<bucket>/<mirror_prefix>/<connector-chosen-subpath>/
      - Each uploaded object's GCS metadata should include a stable source id
        and a last-modified timestamp so we can skip unchanged files.
    """

    name: str = ""          # override in subclass

    def __init__(self, cfg: Config, connector_cfg: dict):
        self.cfg = cfg
        self.c = connector_cfg

    @abstractmethod
    def sync(self, dry_run: bool = False, force: bool = False, log=print) -> SyncStats:
        ...

    # Most connectors will want this one-liner for GCS target root.
    def gcs_base(self, subpath: str) -> str:
        return f"{self.cfg.mirror_prefix}/{subpath.strip('/')}"

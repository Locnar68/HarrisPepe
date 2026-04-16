"""Connector plugin registry.

Each data source (Drive, Gmail, OneDrive, local files, CSV) is a Connector.
Add a new one by subclassing Connector and registering in REGISTRY.
"""
from .base import Connector, SyncStats
from .drive import DriveConnector
from .gmail import GmailConnector
from .onedrive import OneDriveConnector
from .local_files import LocalFilesConnector
from .csv_import import CSVConnector

REGISTRY: dict[str, type[Connector]] = {
    "drive":       DriveConnector,
    "gmail":       GmailConnector,
    "onedrive":    OneDriveConnector,
    "local_files": LocalFilesConnector,
    "csv":         CSVConnector,
}


def build(name: str, cfg, connector_cfg: dict) -> Connector:
    cls = REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"unknown connector {name!r} — known: {sorted(REGISTRY)}"
        )
    return cls(cfg, connector_cfg)


__all__ = ["Connector", "SyncStats", "REGISTRY", "build"]

"""Google Drive connector — recursively mirrors a Drive folder to GCS."""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterator

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from core import drive_service, storage_client
from connectors.base import Connector, SyncStats

EXPORT_MAP: dict[str, tuple[str, str]] = {
    "application/vnd.google-apps.document":     ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet":  ("application/pdf", ".pdf"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.drawing":      ("application/pdf", ".pdf"),
}

INDEXABLE = {
    ".pdf", ".txt", ".html", ".htm", ".md",
    ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp",
    ".csv", ".json",
}


@dataclass
class _DFile:
    id: str
    name: str
    mime_type: str
    modified_time: str
    path: PurePosixPath


class DriveConnector(Connector):
    name = "drive"

    def _walk(self, svc, folder_id: str, base: PurePosixPath = PurePosixPath("")) -> Iterator[_DFile]:
        page_token = None
        while True:
            resp = svc.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields=(
                    "nextPageToken, "
                    "files(id, name, mimeType, modifiedTime, shortcutDetails)"
                ),
                pageSize=200,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            for f in resp.get("files", []):
                mime = f["mimeType"]
                if mime == "application/vnd.google-apps.shortcut":
                    continue
                if mime == "application/vnd.google-apps.folder":
                    yield from self._walk(svc, f["id"], base / f["name"])
                    continue
                yield _DFile(
                    id=f["id"],
                    name=f["name"],
                    mime_type=mime,
                    modified_time=f["modifiedTime"],
                    path=base / f["name"],
                )
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    def _target(self, df: _DFile) -> tuple[str, str]:
        if df.mime_type in EXPORT_MAP:
            mime, ext = EXPORT_MAP[df.mime_type]
            stem = df.path.stem or df.path.name
            return str(df.path.parent / (stem + ext)), mime
        return str(df.path), df.mime_type

    def _download(self, svc, df: _DFile) -> bytes:
        if df.mime_type in EXPORT_MAP:
            export_mime, _ = EXPORT_MAP[df.mime_type]
            req = svc.files().export_media(fileId=df.id, mimeType=export_mime)
        else:
            req = svc.files().get_media(fileId=df.id, supportsAllDrives=True)
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, req, chunksize=4 * 1024 * 1024)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue()

    def sync(self, dry_run: bool = False, force: bool = False, log=print) -> SyncStats:
        stats = SyncStats()
        folder_id = self.c.get("root_folder_id")
        if not folder_id:
            raise RuntimeError("drive connector requires root_folder_id")

        mirror_as = self.c.get("mirror_as", "Properties").strip("/")
        gcs_base = self.gcs_base(mirror_as)

        try:
            svc = drive_service()
        except Exception as e:
            raise RuntimeError(f"drive auth failed: {e}") from e

        gcs = storage_client(self.cfg)
        bucket = gcs.bucket(self.cfg.bucket)

        existing: dict[str, str] = {}
        for blob in bucket.list_blobs(prefix=gcs_base + "/"):
            meta = blob.metadata or {}
            existing[blob.name] = meta.get("source_mtime", "")

        log(f"  drive folder: {folder_id}")
        log(f"  gcs target:   gs://{self.cfg.bucket}/{gcs_base}")

        for df in self._walk(svc, folder_id):
            stats.walked += 1
            rel, mime = self._target(df)
            gcs_name = f"{gcs_base}/{rel}"
            ext = PurePosixPath(rel).suffix.lower()

            if ext not in INDEXABLE:
                stats.skipped_ext += 1
                continue

            if not force and existing.get(gcs_name) == df.modified_time:
                stats.skipped_same += 1
                continue

            if dry_run:
                log(f"  [dry] {df.path}")
                stats.uploaded += 1
                continue

            try:
                data = self._download(svc, df)
            except HttpError as e:
                stats.errors += 1
                log(f"  [err] {df.path}: {e}")
                continue

            blob = bucket.blob(gcs_name)
            blob.metadata = {
                "source": "drive",
                "source_id": df.id,
                "source_mtime": df.modified_time,
            }
            blob.upload_from_string(data, content_type=mime)
            stats.uploaded += 1
            stats.bytes += len(data)
            log(f"  [up]  {df.path} ({len(data):,} B)")

        return stats

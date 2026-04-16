"""Gmail connector — search messages, download bodies + attachments, upload to GCS.

Auth: per-user OAuth via client_secret.json (InstalledAppFlow).
Service accounts can't access personal Gmail without Workspace domain-wide
delegation, so we use a Desktop OAuth client instead.

First run pops a browser for consent. The refresh token is saved to
gmail_token.json (gitignored) for subsequent runs.

Setup:
  1. Cloud Console → APIs & Services → Credentials
  2. Create OAuth 2.0 Client ID → Desktop app
  3. Download the JSON → save as client_secret.json in repo root
  4. Enable Gmail API: gcloud services enable gmail.googleapis.com
  5. In config.yaml, set connectors.gmail.enabled: true

GCS layout:
  <mirror_prefix>/Properties/<default_property>/09-Email/<YYYY-MM>/<slug>_<id>/body.txt
  <mirror_prefix>/Properties/<default_property>/09-Email/<YYYY-MM>/<slug>_<id>/attachment.pdf

The strict metadata classifier picks these up via category_folders mapping:
  "09-Email": email
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Iterator

from core import storage_client
from core.config import Config, REPO_ROOT
from connectors.base import Connector, SyncStats
from connectors.drive import INDEXABLE  # reuse the extension allowlist

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_FILE = "gmail_token.json"


@dataclass
class _Message:
    id: str
    subject: str
    sender: str
    date_iso: str         # ISO 8601
    date_folder: str      # "2023-07"
    body: str
    attachments: list = field(default_factory=list)  # [{filename, data, mime}]


def _slugify(text: str, max_len: int = 40) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()[:max_len]


class GmailConnector(Connector):
    name = "gmail"

    # ---- auth ----

    def _build_service(self):
        """Build Gmail v1 client using per-user OAuth (Desktop app flow)."""
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        secret_path = Path(self.c.get("client_secret_path", "client_secret.json"))
        if not secret_path.is_absolute():
            secret_path = REPO_ROOT / secret_path
        token_path = REPO_ROOT / TOKEN_FILE

        creds = None
        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not secret_path.exists():
                    raise RuntimeError(
                        f"OAuth client secret not found: {secret_path}\n"
                        "Create one at Cloud Console → APIs & Services → Credentials → "
                        "OAuth 2.0 Client IDs (Desktop app) → Download JSON.\n"
                        "Save as client_secret.json in the repo root."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(secret_path), GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)
            # Persist for next run.
            with token_path.open("w", encoding="utf-8") as fh:
                fh.write(creds.to_json())

        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    # ---- search ----

    def _search(self, svc, query: str, after: str | None) -> Iterator[dict]:
        q = query
        if after:
            q = f"{q} after:{after}"
        page_token = None
        while True:
            resp = svc.users().messages().list(
                userId="me", q=q, pageToken=page_token, maxResults=100,
            ).execute()
            for msg in resp.get("messages", []):
                yield msg
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    # ---- fetch ----

    def _get_message(self, svc, msg_id: str) -> _Message:
        raw = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()

        headers = {h["name"].lower(): h["value"] for h in raw["payload"].get("headers", [])}
        subject = headers.get("subject", "(no subject)")
        sender = headers.get("from", "")
        date_str = headers.get("date", "")

        try:
            dt = parsedate_to_datetime(date_str)
            date_iso = dt.isoformat()
            date_folder = dt.strftime("%Y-%m")
        except Exception:
            date_iso = ""
            date_folder = "unknown"

        body_text = ""
        attachments: list[dict] = []

        def walk(parts: list):
            nonlocal body_text
            for part in parts:
                if "parts" in part:
                    walk(part["parts"])
                    continue
                mime = part.get("mimeType", "")
                filename = part.get("filename", "")
                payload_body = part.get("body", {})

                if filename and payload_body.get("attachmentId"):
                    att = svc.users().messages().attachments().get(
                        userId="me", messageId=msg_id, id=payload_body["attachmentId"],
                    ).execute()
                    data = base64.urlsafe_b64decode(att["data"])
                    attachments.append({"filename": filename, "data": data, "mime": mime})
                elif mime == "text/plain" and payload_body.get("data"):
                    body_text += base64.urlsafe_b64decode(
                        payload_body["data"]
                    ).decode("utf-8", errors="replace")

        payload = raw["payload"]
        if "parts" in payload:
            walk(payload["parts"])
        elif payload.get("body", {}).get("data"):
            body_text = base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode("utf-8", errors="replace")

        return _Message(
            id=msg_id,
            subject=subject,
            sender=sender,
            date_iso=date_iso,
            date_folder=date_folder,
            body=body_text,
            attachments=attachments,
        )

    # ---- sync ----

    def sync(self, dry_run: bool = False, force: bool = False, log=print) -> SyncStats:
        stats = SyncStats()

        query = self.c.get("query", "")
        after = self.c.get("after")
        default_property = self.c.get("default_property", "_inbox")
        index_body = self.c.get("index_body", True)
        index_attachments = self.c.get("index_attachments", True)

        # GCS layout: <prefix>/Properties/<property>/09-Email/<date>/<slug>/...
        gcs_base = self.gcs_base(f"Properties/{default_property}/09-Email")

        try:
            svc = self._build_service()
        except Exception as e:
            raise RuntimeError(f"Gmail auth failed: {e}") from e

        gcs = storage_client(self.cfg)
        bucket = gcs.bucket(self.cfg.bucket)

        # Existing objects for incremental skip.
        existing: dict[str, str] = {}
        try:
            for blob in bucket.list_blobs(prefix=gcs_base + "/"):
                meta = blob.metadata or {}
                existing[blob.name] = meta.get("source_mtime", "")
        except Exception:
            pass  # bucket might not exist yet

        log(f"  gmail query:    {query or '(all)'} (after: {after or 'all time'})")
        log(f"  gcs target:     gs://{self.cfg.bucket}/{gcs_base}")
        log(f"  default prop:   {default_property}")

        for msg_meta in self._search(svc, query, after):
            msg_id = msg_meta["id"]
            stats.walked += 1

            try:
                msg = self._get_message(svc, msg_id)
            except Exception as e:
                stats.errors += 1
                log(f"  [err] msg {msg_id}: {e}")
                continue

            slug = _slugify(msg.subject) or msg_id[:12]
            folder = f"{msg.date_folder}/{slug}_{msg_id[:8]}"
            base_meta = {
                "source": "gmail",
                "source_id": msg_id,
                "source_mtime": msg.date_iso,
                "gmail_subject": msg.subject[:200],
                "gmail_from": msg.sender[:200],
            }

            # -- body --
            if index_body and msg.body:
                gcs_name = f"{gcs_base}/{folder}/body.txt"
                if not force and existing.get(gcs_name) == msg.date_iso:
                    stats.skipped_same += 1
                elif dry_run:
                    log(f"  [dry] {folder}/body.txt")
                    stats.uploaded += 1
                else:
                    data = msg.body.encode("utf-8")
                    blob = bucket.blob(gcs_name)
                    blob.metadata = base_meta
                    blob.upload_from_string(data, content_type="text/plain")
                    stats.uploaded += 1
                    stats.bytes += len(data)
                    log(f"  [up]  {folder}/body.txt ({len(data):,} B)")

            # -- attachments --
            if index_attachments:
                for att in msg.attachments:
                    filename = att["filename"]
                    ext = PurePosixPath(filename).suffix.lower()
                    if ext not in INDEXABLE:
                        stats.skipped_ext += 1
                        continue
                    gcs_name = f"{gcs_base}/{folder}/{filename}"
                    if not force and existing.get(gcs_name) == msg.date_iso:
                        stats.skipped_same += 1
                        continue
                    if dry_run:
                        log(f"  [dry] {folder}/{filename}")
                        stats.uploaded += 1
                        continue
                    blob = bucket.blob(gcs_name)
                    blob.metadata = {**base_meta, "source_id": f"{msg_id}_{filename}"}
                    blob.upload_from_string(att["data"], content_type=att["mime"])
                    stats.uploaded += 1
                    stats.bytes += len(att["data"])
                    log(f"  [up]  {folder}/{filename} ({len(att['data']):,} B)")

        return stats

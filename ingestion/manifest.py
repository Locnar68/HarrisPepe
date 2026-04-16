"""Build a JSONL manifest for ImportDocuments."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from core import storage_client
from core.config import Config
from metadata.extractor import classify


@dataclass
class Record:
    id: str
    structData: dict
    content: dict


def build_manifest(cfg: Config, log=print) -> list[Record]:
    gcs = storage_client(cfg)
    bucket = gcs.bucket(cfg.bucket)
    prefix = f"{cfg.mirror_prefix}/"

    records: list[Record] = []
    skipped = 0

    for blob in bucket.list_blobs(prefix=prefix):
        if blob.name.endswith("/"):
            continue
        tags = classify(cfg, blob.name)
        if tags is None:
            skipped += 1
            continue

        uri = f"gs://{cfg.bucket}/{blob.name}"
        doc_id = hashlib.sha1(uri.encode("utf-8")).hexdigest()
        mtime = (blob.updated or datetime.now(timezone.utc)).isoformat()
        mime = blob.content_type or "application/octet-stream"

        # Store the GCS URI in structData so it survives the API round-trip.
        # Search results return structData but not always content.uri.
        struct = {**tags, "updated": mtime, "source_uri": uri}

        records.append(Record(
            id=doc_id,
            structData=struct,
            content={"mimeType": mime, "uri": uri},
        ))

    log(f"  built manifest: {len(records)} records, {skipped} skipped (unclassified)")
    return records


def write_manifest(records: list[Record], local_path: Path) -> Path:
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(asdict(r), separators=(",", ":")))
            fh.write("\n")
    return local_path


def upload_manifest(cfg: Config, records: list[Record], log=print) -> str:
    buf = StringIO()
    for r in records:
        buf.write(json.dumps(asdict(r), separators=(",", ":")))
        buf.write("\n")
    body = buf.getvalue().encode("utf-8")
    gcs = storage_client(cfg)
    bucket = gcs.bucket(cfg.bucket)
    blob = bucket.blob(f"{cfg.manifest_prefix}/manifest.jsonl")
    blob.upload_from_string(body, content_type="application/jsonl")
    uri = cfg.gcs_manifest_uri()
    log(f"  uploaded manifest: {uri}")
    return uri

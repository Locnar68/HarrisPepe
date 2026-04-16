"""Cloud Run entrypoint — hourly sync + index job.

POST /run triggers the full pipeline:
  1. Run every enabled connector (connectors/*.sync())
  2. Build + upload the JSONL manifest
  3. ImportDocuments (INCREMENTAL)
"""
from __future__ import annotations

import logging
import os
import sys
import time
import traceback
from pathlib import Path

# Same trick as scripts/_path.py — repo root on sys.path.
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, jsonify

from core import load_config
from connectors import build as build_connector
from connectors.base import SyncStats
from ingestion.manifest import build_manifest, upload_manifest
from ingestion.inject import import_documents

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
log = logging.getLogger("smb-sync")

app = Flask(__name__)


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"ok": True}), 200


@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "service": "smb-sync",
        "endpoints": ["/run (POST)", "/healthz (GET)"],
    }), 200


@app.route("/run", methods=["POST"])
def run():
    cfg = load_config()
    summary: dict = {"project": cfg.project_id, "data_store": cfg.data_store_id}
    t0 = time.time()
    try:
        log.info("stage 1: connectors")
        overall = SyncStats()
        per_connector: dict[str, dict] = {}
        for name in cfg.enabled_connectors():
            log.info("  » %s", name)
            conn = build_connector(name, cfg, cfg.connector_cfg(name))
            stats = conn.sync(dry_run=False, force=False, log=log.info)
            per_connector[name] = stats.as_dict()
            overall.merge(stats)
        summary["connectors"] = per_connector
        summary["uploaded_total"] = overall.uploaded

        log.info("stage 2: manifest")
        records = build_manifest(cfg, log=log.info)
        summary["manifest_records"] = len(records)
        if not records:
            summary["skipped_import"] = True
            summary["total_seconds"] = round(time.time() - t0, 1)
            return jsonify(summary), 200
        upload_manifest(cfg, records, log=log.info)

        log.info("stage 3: import")
        summary["import"] = import_documents(cfg, wait=True, log=log.info)
        summary["total_seconds"] = round(time.time() - t0, 1)
        return jsonify(summary), 200
    except Exception as e:
        log.exception("pipeline failed")
        summary["error"] = str(e)
        summary["traceback"] = traceback.format_exc(limit=8)
        summary["total_seconds"] = round(time.time() - t0, 1)
        return jsonify(summary), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)

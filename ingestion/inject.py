"""ImportDocuments into the Data Store."""
from __future__ import annotations

import time
from typing import Callable

from core import document_client
from core.config import Config


def import_documents(
    cfg: Config,
    manifest_uri: str | None = None,
    full: bool = False,
    wait: bool = True,
    log: Callable = print,
    on_poll: Callable[[dict], None] | None = None,
    poll_interval_sec: float = 3.0,
    timeout_sec: float = 1800.0,
) -> dict:
    """Import documents from a GCS JSONL manifest.

    If wait=True, polls the operation every `poll_interval_sec` seconds.
    Calls on_poll({elapsed, success, failure, done}) on each tick so the caller
    can render a live heartbeat (scripts/index.py uses rich.console.status).
    """
    from google.cloud import discoveryengine_v1 as de

    manifest_uri = manifest_uri or cfg.gcs_manifest_uri()
    mode = (
        de.ImportDocumentsRequest.ReconciliationMode.FULL
        if full
        else de.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL
    )

    client = document_client(cfg)
    req = de.ImportDocumentsRequest(
        parent=cfg.branch_name,
        gcs_source=de.GcsSource(input_uris=[manifest_uri], data_schema="document"),
        reconciliation_mode=mode,
    )
    log(f"  importing from {manifest_uri} (mode={'FULL' if full else 'INCREMENTAL'})")
    op = client.import_documents(request=req)
    op_name = op.operation.name
    log(f"  op: {op_name}")

    if not wait:
        return {"op": op_name, "waited": False}

    # Poll heartbeat — the underlying Operation's metadata is refreshed each call.
    start = time.time()
    deadline = start + timeout_sec
    while not op.done():
        time.sleep(poll_interval_sec)
        elapsed = time.time() - start
        if time.time() > deadline:
            raise TimeoutError(
                f"ImportDocuments did not finish in {timeout_sec}s (op still running "
                f"server-side): {op_name}"
            )
        if on_poll is not None:
            try:
                md = op.metadata
                on_poll({
                    "elapsed": elapsed,
                    "success": getattr(md, "success_count", None),
                    "failure": getattr(md, "failure_count", None),
                    "done": False,
                })
            except Exception:
                pass

    # Finalize (raises if the op failed server-side).
    op.result()
    md = op.metadata
    elapsed = time.time() - start
    result = {
        "op": op_name,
        "waited": True,
        "elapsed_sec": round(elapsed, 1),
        "success": getattr(md, "success_count", None),
        "failure": getattr(md, "failure_count", None),
    }
    if on_poll is not None:
        on_poll({**result, "done": True})
    log(f"  done in {elapsed:.1f}s: success={result['success']} failure={result['failure']}")
    return result

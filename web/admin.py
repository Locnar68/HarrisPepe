"""Admin dashboard — GCP cost tracking, local query counter, accurate doc counts."""
from __future__ import annotations

import json
import datetime
from pathlib import Path
from dataclasses import dataclass
from core.config import Config, REPO_ROOT

USAGE_FILE = REPO_ROOT / "output" / ".usage.json"

# Vertex AI Search Enterprise pricing (2025)
PRICING = {
    "search_query_per_1k": 4.00,
    "answer_query_per_1k": 4.00,
    "doc_hosting_per_1k_month": 2.50,
    "gcs_storage_per_gb_month": 0.026,
}


def _load_usage() -> dict:
    if USAGE_FILE.exists():
        try: return json.loads(USAGE_FILE.read_text())
        except: pass
    return {"queries": [], "total_queries": 0}


def _save_usage(data: dict):
    USAGE_FILE.parent.mkdir(exist_ok=True)
    USAGE_FILE.write_text(json.dumps(data), encoding="utf-8")


def track_query():
    """Call this every time a query is made. Tracks daily counts."""
    data = _load_usage()
    today = datetime.date.today().isoformat()
    data["total_queries"] = data.get("total_queries", 0) + 1

    # Daily breakdown (keep last 90 days).
    days = data.get("daily", {})
    days[today] = days.get(today, 0) + 1
    # Prune old days.
    cutoff = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    days = {k: v for k, v in days.items() if k >= cutoff}
    data["daily"] = days
    _save_usage(data)


def get_usage_stats(cfg: Config) -> dict:
    """Gather accurate usage statistics."""
    errors = []

    # ── Document count (list actual docs in the data store) ──
    doc_count = 0
    try:
        from google.cloud import discoveryengine_v1 as de
        client = de.DocumentServiceClient()
        parent = f"{cfg.data_store_name}/branches/default_branch"
        page = client.list_documents(request=de.ListDocumentsRequest(parent=parent, page_size=100))
        for _ in page:
            doc_count += 1
    except Exception as e:
        errors.append(f"Document count: {e}")

    # ── GCS bucket stats ──
    bucket_objects = 0
    bucket_size_bytes = 0
    try:
        from core import storage_client
        gcs = storage_client(cfg)
        for blob in gcs.bucket(cfg.bucket).list_blobs(prefix=cfg.mirror_prefix + "/"):
            bucket_size_bytes += blob.size or 0
            bucket_objects += 1
    except Exception as e:
        errors.append(f"GCS stats: {e}")

    bucket_size_mb = bucket_size_bytes / (1024 * 1024)
    bucket_size_gb = bucket_size_bytes / (1024 * 1024 * 1024)

    # ── Local query tracking ──
    usage = _load_usage()
    today = datetime.date.today().isoformat()
    daily = usage.get("daily", {})
    queries_today = daily.get(today, 0)
    total_queries = usage.get("total_queries", 0)

    # This month's queries.
    month_prefix = today[:7]  # "2026-04"
    queries_month = sum(v for k, v in daily.items() if k.startswith(month_prefix))

    # ── Cost estimates ──
    est_doc_hosting = (doc_count / 1000) * PRICING["doc_hosting_per_1k_month"]
    est_storage = bucket_size_gb * PRICING["gcs_storage_per_gb_month"]
    # Use answer query rate (higher) since most queries use the answer endpoint.
    est_queries = (queries_month / 1000) * PRICING["answer_query_per_1k"]
    est_total = est_doc_hosting + est_storage + est_queries

    return {
        "data_store": {"id": cfg.data_store_id, "engine": cfg.engine_id, "documents": doc_count},
        "storage": {"bucket": cfg.bucket, "objects": bucket_objects, "size_mb": round(bucket_size_mb, 2)},
        "api_usage": {
            "today": queries_today,
            "this_month": queries_month,
            "all_time": total_queries,
            "daily": daily,
        },
        "cost_estimates": {
            "doc_hosting": round(est_doc_hosting, 2),
            "gcs_storage": round(est_storage, 4),
            "api_queries": round(est_queries, 2),
            "total_monthly": round(est_total, 2),
        },
        "pricing": PRICING,
        "errors": errors,
    }

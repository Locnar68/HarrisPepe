"""Admin dashboard — GCP cost tracking and usage metrics."""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from core.config import Config


@dataclass
class UsageStats:
    # Data Store
    doc_count: int = 0
    data_store_id: str = ""
    engine_id: str = ""

    # GCS
    bucket_name: str = ""
    bucket_objects: int = 0
    bucket_size_mb: float = 0.0

    # Cost estimates (monthly)
    est_storage_cost: float = 0.0
    est_doc_hosting_cost: float = 0.0
    est_query_cost: float = 0.0
    est_total_monthly: float = 0.0

    # API usage
    query_count_today: int = 0
    query_count_month: int = 0

    # Pricing reference
    pricing: dict = None

    errors: list[str] = None


# Vertex AI Search Enterprise pricing (as of 2025)
PRICING = {
    "search_query_per_1k": 4.00,
    "answer_query_per_1k": 4.00,
    "doc_hosting_per_1k_month": 2.50,
    "gcs_storage_per_gb_month": 0.026,
    "gcs_class_a_per_10k": 0.05,   # uploads
    "gcs_class_b_per_10k": 0.004,  # downloads
    "data_store_enterprise_month": 0.0,  # included in query pricing
}


def get_usage_stats(cfg: Config) -> UsageStats:
    """Gather usage statistics from GCP APIs."""
    stats = UsageStats(
        data_store_id=cfg.data_store_id,
        engine_id=cfg.engine_id,
        bucket_name=cfg.bucket,
        pricing=PRICING,
        errors=[],
    )

    # ── Data Store document count ──
    try:
        from google.cloud import discoveryengine_v1 as de
        from core import search_client

        client = search_client(cfg)
        # Do a minimal search to check if the engine is alive.
        req = de.SearchRequest(
            serving_config=cfg.search_serving_config,
            query="test",
            page_size=1,
        )
        resp = client.search(request=req)
        stats.doc_count = resp.total_size if hasattr(resp, 'total_size') else 0
    except Exception as e:
        stats.errors.append(f"Data store query failed: {e}")

    # Try to get doc count from the data store directly.
    try:
        from google.cloud import discoveryengine_v1 as de
        client = de.DocumentServiceClient()
        parent = f"{cfg.data_store_name}/branches/default_branch"
        docs = list(client.list_documents(request=de.ListDocumentsRequest(parent=parent, page_size=1)))
        # The API returns a pager; total_size might be available.
    except Exception:
        pass  # Non-critical

    # ── GCS bucket stats ──
    try:
        from core import storage_client
        gcs = storage_client(cfg)
        bucket = gcs.bucket(cfg.bucket)
        total_size = 0
        total_objects = 0
        for blob in bucket.list_blobs(prefix=cfg.mirror_prefix + "/"):
            total_size += blob.size or 0
            total_objects += 1
        stats.bucket_size_mb = total_size / (1024 * 1024)
        stats.bucket_objects = total_objects
    except Exception as e:
        stats.errors.append(f"GCS stats failed: {e}")

    # ── Cost estimates ──
    # Document hosting: $2.50 per 1000 docs/month
    doc_count = stats.doc_count or stats.bucket_objects
    stats.est_doc_hosting_cost = (doc_count / 1000) * PRICING["doc_hosting_per_1k_month"]

    # Storage: $0.026 per GB/month
    stats.est_storage_cost = (stats.bucket_size_mb / 1024) * PRICING["gcs_storage_per_gb_month"]

    # Query costs: estimate based on typical usage
    # We can't easily get exact query counts without Cloud Monitoring setup,
    # so we'll show the per-query rate and let the admin track usage.
    stats.est_query_cost = 0.0  # Will be calculated from monitoring if available

    # Total
    stats.est_total_monthly = (
        stats.est_doc_hosting_cost +
        stats.est_storage_cost +
        stats.est_query_cost
    )

    # ── Try Cloud Monitoring for API call counts ──
    try:
        from google.cloud import monitoring_v3
        from google.protobuf import timestamp_pb2

        mon_client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{cfg.project_id}"

        now = datetime.datetime.utcnow()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Query for Discovery Engine API calls this month.
        interval = monitoring_v3.TimeInterval({
            "start_time": {"seconds": int(start_of_month.timestamp())},
            "end_time": {"seconds": int(now.timestamp())},
        })

        # Try to get API request count.
        try:
            results = mon_client.list_time_series(
                request={
                    "name": project_name,
                    "filter": 'metric.type = "serviceruntime.googleapis.com/api/request_count" AND resource.labels.service = "discoveryengine.googleapis.com"',
                    "interval": interval,
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                }
            )
            monthly_calls = 0
            for ts in results:
                for point in ts.points:
                    monthly_calls += point.value.int64_value
            stats.query_count_month = monthly_calls
            # Estimate query cost: assume half are answer queries, half are search.
            avg_rate = (PRICING["search_query_per_1k"] + PRICING["answer_query_per_1k"]) / 2
            stats.est_query_cost = (monthly_calls / 1000) * avg_rate
            stats.est_total_monthly = stats.est_doc_hosting_cost + stats.est_storage_cost + stats.est_query_cost
        except Exception:
            pass  # Monitoring API might not be enabled.

        # Today's calls.
        try:
            interval_today = monitoring_v3.TimeInterval({
                "start_time": {"seconds": int(start_of_day.timestamp())},
                "end_time": {"seconds": int(now.timestamp())},
            })
            results = mon_client.list_time_series(
                request={
                    "name": project_name,
                    "filter": 'metric.type = "serviceruntime.googleapis.com/api/request_count" AND resource.labels.service = "discoveryengine.googleapis.com"',
                    "interval": interval_today,
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                }
            )
            daily_calls = 0
            for ts in results:
                for point in ts.points:
                    daily_calls += point.value.int64_value
            stats.query_count_today = daily_calls
        except Exception:
            pass

    except ImportError:
        stats.errors.append("google-cloud-monitoring not installed. Run: pip install google-cloud-monitoring")
    except Exception as e:
        stats.errors.append(f"Monitoring API: {e}")

    return stats

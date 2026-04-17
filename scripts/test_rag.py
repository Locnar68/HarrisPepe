"""
Test real RAG end-to-end: search + Gemini summarization with citations.

This bypasses the web UI and exercises the exact same API path. If this works
but the web UI doesn't, the problem is in the web UI, not the backend.

Usage (from repo root):
    python scripts/test_rag.py
    python scripts/test_rag.py "your custom query here"
"""
import json
import os
import sys
from pathlib import Path

import google.auth.transport.requests
import requests
from dotenv import load_dotenv
from google.cloud import discoveryengine_v1
from google.oauth2 import service_account


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / "Phase3_Bootstrap" / "secrets" / ".env"
    sa_key = repo_root / "Phase3_Bootstrap" / "secrets" / "service-account.json"

    load_dotenv(env_path)
    project_id = os.getenv("GCP_PROJECT_ID")
    data_store_id = os.getenv("VERTEX_DATA_STORE_ID")
    engine_id = os.getenv("VERTEX_ENGINE_ID")

    custom_query = sys.argv[1] if len(sys.argv) > 1 else None

    creds = service_account.Credentials.from_service_account_file(
        str(sa_key), scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    # --- 1. Confirm document processing config ---
    print("=" * 70)
    print("1. Data store parsing configuration")
    print("=" * 70)
    token_creds = service_account.Credentials.from_service_account_file(
        str(sa_key), scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    token_creds.refresh(google.auth.transport.requests.Request())
    url = (
        f"https://discoveryengine.googleapis.com/v1alpha"
        f"/projects/{project_id}/locations/global"
        f"/collections/default_collection/dataStores/{data_store_id}"
        f"/documentProcessingConfig"
    )
    r = requests.get(url, headers={
        "Authorization": f"Bearer {token_creds.token}",
        "X-Goog-User-Project": project_id,
    })
    if r.status_code == 200:
        config = r.json()
        parsing = config.get("defaultParsingConfig", {})
        if "layoutParsingConfig" in parsing:
            print("  ✓ Layout Parser enabled (PDF content will be extracted)")
        elif "ocrParsingConfig" in parsing:
            print("  ✓ OCR Parser enabled")
        elif "digitalParsingConfig" in parsing:
            print("  ⚠ Digital-only parser (text PDFs only, no OCR)")
        else:
            print(f"  ⚠ Unknown parser: {parsing}")
    else:
        print(f"  ✗ Config fetch failed: {r.status_code} {r.text[:200]}")

    # --- 2. Run queries with full RAG spec ---
    print()
    print("=" * 70)
    print("2. RAG queries (search + Gemini summary with citations)")
    print("=" * 70)
    search_client = discoveryengine_v1.SearchServiceClient(credentials=creds)
    serving_config = (
        f"projects/{project_id}/locations/global"
        f"/collections/default_collection/engines/{engine_id}/servingConfigs/default_search"
    )

    queries = [custom_query] if custom_query else [
        "summarize what documents are available",
        "list all properties",
    ]

    for q in queries:
        print(f"\n📝 Query: '{q}'")
        req = discoveryengine_v1.SearchRequest(
            serving_config=serving_config,
            query=q,
            page_size=10,
            content_search_spec=discoveryengine_v1.SearchRequest.ContentSearchSpec(
                snippet_spec=discoveryengine_v1.SearchRequest.ContentSearchSpec.SnippetSpec(
                    return_snippet=True,
                ),
                summary_spec=discoveryengine_v1.SearchRequest.ContentSearchSpec.SummarySpec(
                    summary_result_count=10,
                    include_citations=True,
                    ignore_adversarial_query=True,
                    ignore_non_summary_seeking_query=False,
                    model_spec=discoveryengine_v1.SearchRequest.ContentSearchSpec.SummarySpec.ModelSpec(
                        version="stable",
                    ),
                ),
                extractive_content_spec=discoveryengine_v1.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                    max_extractive_answer_count=1,
                    max_extractive_segment_count=1,
                ),
            ),
        )
        try:
            resp = search_client.search(req)
            results = list(resp)
            summary_text = ""
            if hasattr(resp, "summary") and resp.summary:
                summary_text = resp.summary.summary_text
            print(f"   Results: {len(results)}")
            print(f"   🤖 Gemini: {summary_text or '(no summary generated)'}")
        except Exception as e:
            print(f"   ✗ {e}")

    print()
    print("✅ If Gemini produced a summary above, RAG is working end-to-end.")
    print("   If the web UI still says OFFLINE, the bug is in the UI — not the backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

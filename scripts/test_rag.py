"""
End-to-end RAG test: search + Gemini summarization with citations.

Exercises the exact API path the web UI uses, so if this works but the web
UI doesn't, the bug is in the UI — not the backend.

Usage:
    python scripts/test_rag.py
    python scripts/test_rag.py "your custom query here"

Env discovery: $VERTEX_ENV_FILE > <cwd>/Phase3_Bootstrap/secrets/.env >
               <cwd>/.env > <repo>/Phase3_Bootstrap/secrets/.env
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import load_or_die  # noqa: E402

import google.auth.transport.requests  # noqa: E402
import requests  # noqa: E402
from google.cloud import discoveryengine_v1  # noqa: E402
from google.oauth2 import service_account  # noqa: E402


def main() -> int:
    env_path, sa_key = load_or_die()

    project_id = os.getenv("GCP_PROJECT_ID")
    data_store_id = os.getenv("VERTEX_DATA_STORE_ID")
    engine_id = os.getenv("VERTEX_ENGINE_ID")

    if not (project_id and data_store_id and engine_id):
        print("✗ .env is missing one of: GCP_PROJECT_ID, VERTEX_DATA_STORE_ID, VERTEX_ENGINE_ID")
        print(f"  loaded from: {env_path}")
        return 1

    custom_query = sys.argv[1] if len(sys.argv) > 1 else None

    creds = service_account.Credentials.from_service_account_file(
        str(sa_key), scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    # --- 1. Confirm document processing config (Layout Parser?) ---
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
    try:
        r = requests.get(url, headers={
            "Authorization": f"Bearer {token_creds.token}",
            "X-Goog-User-Project": project_id,
        }, timeout=30)
    except Exception as e:
        print(f"  ✗ Config fetch network error: {e}")
        r = None

    if r is not None and r.status_code == 200:
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
    elif r is not None:
        print(f"  ✗ Config fetch failed: {r.status_code} {r.text[:200]}")

    # --- 2. Run queries with full RAG content spec ---
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

    got_any_summary = False
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
            # Materialize the pager BEFORE accessing resp.summary — known SDK
            # gotcha where summary is lazy-loaded.
            results = list(resp)
            summary_text = ""
            if hasattr(resp, "summary") and resp.summary:
                summary_text = resp.summary.summary_text or ""
            print(f"   Results: {len(results)}")
            print(f"   🤖 Gemini: {summary_text or '(no summary generated)'}")
            if summary_text:
                got_any_summary = True
        except Exception as e:
            print(f"   ✗ {e}")

    print()
    if got_any_summary:
        print("✅ RAG is working end-to-end (Gemini produced a summary).")
        print("   If the web UI shows something different, the bug is in the UI.")
    else:
        print("⚠ No summary was generated for any query.")
        print("   Likely causes:")
        print("     - Indexing still in progress (wait 5–15 min after sync)")
        print("     - Layout Parser not enabled on the data store")
        print("     - Data store tier is Standard (summarization requires Enterprise)")
        print("     - Query doesn't match anything in the indexed documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())

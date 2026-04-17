"""
Check indexing status: what documents are in the data store, and are they
searchable by the engine?

Usage:
    python scripts/check_index.py

Env discovery: $VERTEX_ENV_FILE > <cwd>/Phase3_Bootstrap/secrets/.env >
               <cwd>/.env > <repo>/Phase3_Bootstrap/secrets/.env
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make sibling imports work no matter where this is run from.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import load_or_die  # noqa: E402

from google.cloud import discoveryengine_v1  # noqa: E402
from google.oauth2 import service_account  # noqa: E402


def _safe_struct_get(struct, key: str, default: str = "") -> str:
    """Safely read a key from a proto-plus Struct. Returns default on anything weird."""
    if struct is None:
        return default
    try:
        if hasattr(struct, "get") and callable(struct.get):
            val = struct.get(key, default)
            return str(val) if val is not None else default
        # Fall-through for classic dict or Struct-with-__contains__
        if key in struct:
            val = struct[key]
            return str(val) if val is not None else default
    except Exception:
        pass
    return default


def main() -> int:
    env_path, sa_key = load_or_die()

    project_id = os.getenv("GCP_PROJECT_ID")
    data_store_id = os.getenv("VERTEX_DATA_STORE_ID")
    engine_id = os.getenv("VERTEX_ENGINE_ID")

    if not (project_id and data_store_id):
        print(f"✗ .env is missing GCP_PROJECT_ID or VERTEX_DATA_STORE_ID")
        print(f"  loaded from: {env_path}")
        return 1

    creds = service_account.Credentials.from_service_account_file(
        str(sa_key), scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    print(f"Project:    {project_id}")
    print(f"Data Store: {data_store_id}")
    print(f"Engine:     {engine_id or '(not set)'}")
    print()

    # --- 1. List documents in the data store ---
    print("📚 Documents in data store")
    print("-" * 70)
    doc_client = discoveryengine_v1.DocumentServiceClient(credentials=creds)
    parent = (
        f"projects/{project_id}/locations/global"
        f"/collections/default_collection/dataStores/{data_store_id}/branches/default_branch"
    )
    try:
        docs = list(doc_client.list_documents(parent=parent))
    except Exception as e:
        print(f"  ✗ list_documents failed: {e}")
        return 1

    print(f"Total: {len(docs)}")
    for d in docs:
        title = _safe_struct_get(d.struct_data, "title", "(untitled)")
        uri = d.content.uri if d.content else "(no content)"
        print(f"  - {title}")
        print(f"    id:  {d.id}")
        print(f"    uri: {uri}")

    # --- 2. Engine-side sanity check (no summarization) ---
    print()
    print("🔍 Search sanity check (no summarization)")
    print("-" * 70)
    if not engine_id:
        print("  ℹ No VERTEX_ENGINE_ID set — skipping engine search test")
        return 0

    search_client = discoveryengine_v1.SearchServiceClient(credentials=creds)
    serving_config = (
        f"projects/{project_id}/locations/global"
        f"/collections/default_collection/engines/{engine_id}/servingConfigs/default_search"
    )
    # An empty query returns everything the engine can currently see.
    req = discoveryengine_v1.SearchRequest(
        serving_config=serving_config, query="", page_size=10
    )
    try:
        resp = search_client.search(req)
        results = list(resp)
        print(f"  Engine returns {len(results)} documents")
        for r in results[:5]:
            print(f"    - {r.document.id}")
        if len(results) < len(docs):
            print(f"  ⚠ Engine returns fewer docs than the datastore has "
                  f"({len(results)} < {len(docs)})")
            print(f"     → Indexing is probably still in progress. "
                  f"Wait 5–15 min and retry.")
    except Exception as e:
        print(f"  ✗ Search failed: {e}")

    print()
    print("💡 For a real RAG test with Gemini summarization: python scripts/test_rag.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

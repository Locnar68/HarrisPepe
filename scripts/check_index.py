"""
Check indexing status: what documents are in the data store, and are they searchable?

Usage (from repo root):
    python scripts/check_index.py
"""
import os
import sys
from pathlib import Path

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

    creds = service_account.Credentials.from_service_account_file(
        str(sa_key), scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    print(f"Project:    {project_id}")
    print(f"Data Store: {data_store_id}")
    print(f"Engine:     {engine_id}\n")

    # 1. List documents
    print("📚 Documents in data store")
    print("-" * 70)
    doc_client = discoveryengine_v1.DocumentServiceClient(credentials=creds)
    parent = (
        f"projects/{project_id}/locations/global"
        f"/collections/default_collection/dataStores/{data_store_id}/branches/default_branch"
    )
    docs = list(doc_client.list_documents(parent=parent))
    print(f"Total: {len(docs)}")
    for d in docs:
        title = "unknown"
        try:
            if d.struct_data and "title" in d.struct_data:
                title = d.struct_data["title"]
        except Exception:
            pass
        uri = d.content.uri if d.content else "(no content)"
        print(f"  - {title}")
        print(f"    id:  {d.id}")
        print(f"    uri: {uri}")

    # 2. Quick search test (without summarization — just checks the index)
    print()
    print("🔍 Search sanity check (no summarization)")
    print("-" * 70)
    if not engine_id:
        print("  ℹ No VERTEX_ENGINE_ID set — skipping search test")
        return 0

    search_client = discoveryengine_v1.SearchServiceClient(credentials=creds)
    serving_config = (
        f"projects/{project_id}/locations/global"
        f"/collections/default_collection/engines/{engine_id}/servingConfigs/default_search"
    )
    # Empty query returns all docs the engine can see
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
            print(f"  ⚠ Engine returns fewer docs than datastore has ({len(results)} < {len(docs)})")
            print(f"     → Indexing may still be in progress. Wait 5–15 min and retry.")
    except Exception as e:
        print(f"  ✗ Search failed: {e}")

    print()
    print("💡 For a real RAG test with Gemini summarization: python scripts/test_rag.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

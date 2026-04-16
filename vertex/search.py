"""Classical ranked-results search against the Vertex AI Search engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core import search_client
from core.config import Config


@dataclass
class Hit:
    rank: int
    property: str
    doc_type: str
    filename: str
    uri: str
    struct: dict[str, Any]


def build_filter(property_=None, doc_type=None, category=None) -> str:
    clauses = []
    if property_:
        clauses.append(f'property: ANY("{property_}")')
    if doc_type:
        clauses.append(f'doc_type: ANY("{doc_type}")')
    if category:
        clauses.append(f'category: ANY("{category}")')
    return " AND ".join(clauses)


def _extract_uri(doc) -> str:
    """Try every possible location the GCS URI might be stored."""
    # 1. content.uri (set during import via JSONL content field)
    if doc.content:
        uri = getattr(doc.content, 'uri', '') or ''
        if uri:
            return uri

    # 2. derived_struct_data.link (Vertex puts source URI here for unstructured docs)
    if doc.derived_struct_data:
        dsd = dict(doc.derived_struct_data)
        link = dsd.get('link', '') or dsd.get('uri', '') or dsd.get('source_uri', '')
        if link:
            return link

    # 3. struct_data.source_uri (our custom field, added in manifest.py)
    if doc.struct_data:
        sd = dict(doc.struct_data)
        su = sd.get('source_uri', '')
        if su:
            return su

    # 4. derived_struct_data.source_uri
    if doc.derived_struct_data:
        dsd = dict(doc.derived_struct_data)
        su = dsd.get('source_uri', '')
        if su:
            return su

    return ''


def search(cfg: Config, query: str, property_=None, doc_type=None,
           category=None, page_size: int = 10) -> list[Hit]:
    from google.cloud import discoveryengine_v1 as de

    client = search_client(cfg)
    filter_expr = build_filter(property_, doc_type, category)

    req = de.SearchRequest(
        serving_config=cfg.search_serving_config,
        query=query,
        filter=filter_expr,
        page_size=page_size,
    )
    resp = client.search(request=req)

    hits = []
    for i, r in enumerate(resp.results, 1):
        doc = r.document

        # Get metadata — prefer struct_data, fall back to derived_struct_data
        sd = {}
        if doc.struct_data:
            sd = dict(doc.struct_data)
        elif doc.derived_struct_data:
            sd = dict(doc.derived_struct_data)

        uri = _extract_uri(doc)

        hits.append(Hit(
            rank=i,
            property=str(sd.get("property", "")),
            doc_type=str(sd.get("doc_type", "")),
            filename=str(sd.get("filename", "")),
            uri=uri,
            struct=sd,
        ))
    return hits

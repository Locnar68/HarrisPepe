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


def build_filter(property_: str | None = None,
                 doc_type: str | None = None,
                 category: str | None = None) -> str:
    clauses: list[str] = []
    if property_:
        clauses.append(f'property: ANY("{property_}")')
    if doc_type:
        clauses.append(f'doc_type: ANY("{doc_type}")')
    if category:
        clauses.append(f'category: ANY("{category}")')
    return " AND ".join(clauses)


def search(cfg: Config,
           query: str,
           property_: str | None = None,
           doc_type: str | None = None,
           category: str | None = None,
           page_size: int = 10) -> list[Hit]:
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

    hits: list[Hit] = []
    for i, r in enumerate(resp.results, 1):
        doc = r.document
        sd = dict(doc.struct_data) if doc.struct_data else {}
        uri = doc.content.uri if doc.content and doc.content.uri else ""
        hits.append(Hit(
            rank=i,
            property=str(sd.get("property", "")),
            doc_type=str(sd.get("doc_type", "")),
            filename=str(sd.get("filename", "")),
            uri=uri,
            struct=sd,
        ))
    return hits

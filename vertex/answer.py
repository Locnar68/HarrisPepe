"""Gemini-grounded answer over the Vertex AI Search engine.

Supports stateless (one-shot) and session-based (multi-turn) conversations.
Pass a session name from a previous response to enable follow-ups like
"which document was that from?" or "tell me more about the second one."
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core import conversational_client
from core.config import Config
from vertex.search import build_filter


@dataclass
class Answer:
    text: str
    citations: list[dict]
    sources: list[dict]
    session: str | None = None       # session resource name for follow-ups


def answer(cfg: Config,
           query: str,
           property_: str | None = None,
           doc_type: str | None = None,
           category: str | None = None,
           session: str | None = None,
           model_version: str = "gemini-2.0-flash-001/answer_gen/v1") -> Answer:
    from google.cloud import discoveryengine_v1 as de

    client = conversational_client(cfg)
    filter_expr = build_filter(property_, doc_type, category)

    req = de.AnswerQueryRequest(
        serving_config=cfg.search_serving_config,
        query=de.Query(text=query),
        session=session or None,
        search_spec=de.AnswerQueryRequest.SearchSpec(
            search_params=de.AnswerQueryRequest.SearchSpec.SearchParams(
                max_return_results=10,
                filter=filter_expr,
            ),
        ),
        answer_generation_spec=de.AnswerQueryRequest.AnswerGenerationSpec(
            ignore_adversarial_query=True,
            include_citations=True,
            model_spec=de.AnswerQueryRequest.AnswerGenerationSpec.ModelSpec(
                model_version=model_version,
            ),
        ),
    )

    resp = client.answer_query(request=req)
    a = resp.answer
    text = a.answer_text or ""

    # Extract session name for multi-turn follow-ups.
    session_name = None
    if resp.session:
        session_name = resp.session.name

    citations = []
    for c in a.citations:
        snippet = text[c.start_index:c.end_index]
        citations.append({
            "snippet": snippet,
            "reference_ids": [s.reference_id for s in c.sources],
        })

    sources = []
    for ref in a.references:
        di = ref.unstructured_document_info
        if di:
            sd = dict(di.struct_data) if di.struct_data else {}
            sources.append({
                "reference_id": ref.reference_id,
                "title": di.title or sd.get("filename", ""),
                "property": sd.get("property", ""),
                "category": sd.get("category", ""),
                "uri": di.uri if hasattr(di, "uri") else "",
            })

    return Answer(
        text=text,
        citations=citations,
        sources=sources,
        session=session_name,
    )

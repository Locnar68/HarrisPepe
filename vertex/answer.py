"""Gemini-grounded answer with session support + URI extraction."""
from __future__ import annotations

from dataclasses import dataclass

from core import conversational_client
from core.config import Config
from vertex.search import build_filter


@dataclass
class Answer:
    text: str
    citations: list[dict]
    sources: list[dict]
    session: str | None = None


def answer(cfg: Config, query: str, property_=None, doc_type=None,
           category=None, session=None,
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
                max_return_results=10, filter=filter_expr,
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
    session_name = resp.session.name if resp.session else None

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
            # Try multiple URI sources.
            uri = getattr(di, 'uri', '') or ''
            if not uri:
                uri = sd.get('source_uri', '') or sd.get('link', '')
            sources.append({
                "reference_id": ref.reference_id,
                "title": di.title or sd.get("filename", ""),
                "property": sd.get("property", ""),
                "category": sd.get("category", ""),
                "doc_type": sd.get("doc_type", ""),
                "uri": uri,
            })

    return Answer(text=text, citations=citations, sources=sources, session=session_name)

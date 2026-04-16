"""Drafting engine — fill templates with RAG answers from Vertex AI Search.

Two modes:
  SMART  — {{What is the EIN number}} → uses placeholder text as the query
  MAPPED — {{ein}} → looks up queries.yaml for custom query + doc_type filter

Includes rate-limit throttling and retry with exponential backoff to stay
within Vertex AI Search's LLM query quota (~10 req/min on Enterprise).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from core.config import Config


@dataclass
class FillResult:
    placeholder: str
    query: str
    answer: str
    sources: list[str] = field(default_factory=list)
    success: bool = True


class DraftingEngine:
    def __init__(self, cfg: Config, property_: str | None = None,
                 doc_type: str | None = None, delay: float = 4.0,
                 max_retries: int = 3, log=print):
        self.cfg = cfg
        self.property = property_
        self.doc_type = doc_type
        self.delay = delay              # seconds between queries
        self.max_retries = max_retries
        self.log = log
        self._cache: dict[str, FillResult] = {}
        self._call_count = 0

    def _throttle(self):
        """Wait between API calls to avoid rate limits."""
        if self._call_count > 0 and self.delay > 0:
            time.sleep(self.delay)
        self._call_count += 1

    def _resolve(self, placeholder: str, query_spec: dict | None = None) -> FillResult:
        """Run a RAG query for one placeholder with retry logic."""
        if query_spec:
            query_text = query_spec.get("query", placeholder)
            dt = query_spec.get("doc_type") or self.doc_type
            prop = query_spec.get("property") or self.property
        else:
            query_text = placeholder.replace("_", " ")
            dt = self.doc_type
            prop = self.property

        cache_key = f"{query_text}|{prop}|{dt}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        from vertex.answer import answer

        last_err = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                a = answer(self.cfg, query_text, property_=prop, doc_type=dt)
                text = a.text or ""
                if not text or "could not be generated" in text.lower():
                    result = FillResult(
                        placeholder=placeholder, query=query_text,
                        answer=f"[UNANSWERED: {placeholder}]", success=False)
                else:
                    src_names = [s.get("title", "") for s in a.sources if s.get("title")]
                    result = FillResult(
                        placeholder=placeholder, query=query_text,
                        answer=text.strip(), sources=src_names, success=True)
                self._cache[cache_key] = result
                return result

            except Exception as e:
                last_err = e
                err_str = str(e)
                if "429" in err_str or "quota" in err_str.lower():
                    # Rate limited — back off exponentially.
                    wait = self.delay * (2 ** attempt) + 2
                    self.log(f"    ⏳ rate limited on '{placeholder}', retrying in {wait:.0f}s...")
                    time.sleep(wait)
                elif "503" in err_str:
                    wait = self.delay * (attempt + 1)
                    self.log(f"    ⏳ 503 on '{placeholder}', retrying in {wait:.0f}s...")
                    time.sleep(wait)
                else:
                    # Non-retryable error.
                    break

        result = FillResult(
            placeholder=placeholder, query=query_text,
            answer=f"[ERROR: {last_err}]", success=False)
        self._cache[cache_key] = result
        return result

    def fill(self, template_text: str, query_map: dict | None = None) -> tuple[str, list[FillResult]]:
        """Replace all {{placeholders}} with RAG answers."""
        query_map = query_map or {}
        results: list[FillResult] = []
        seen: set[str] = set()

        def replacer(match):
            name = match.group(1).strip()
            if name in seen:
                cached = next((r for r in results if r.placeholder == name), None)
                return cached.answer if cached else match.group(0)
            seen.add(name)
            spec = query_map.get(name)
            self.log(f"  [{len(seen)}/{total}] {name}...")
            result = self._resolve(name, spec)
            status = "✓" if result.success else "✗"
            self.log(f"         {status} {result.answer[:60]}")
            results.append(result)
            return result.answer

        # Count total unique placeholders first.
        total = len(set(re.findall(r"\{\{(.+?)\}\}", template_text)))

        filled = re.sub(r"\{\{(.+?)\}\}", replacer, template_text)
        return filled, results


def load_query_map(queries_path: Path) -> dict:
    """Load the optional queries.yaml file."""
    if not queries_path.exists():
        return {}
    with queries_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("placeholders", data)

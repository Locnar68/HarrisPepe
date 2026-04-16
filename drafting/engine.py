"""Drafting engine — fill templates with RAG answers from Vertex AI Search.

Uses a strict extraction preamble to force Vertex to return ONLY the value,
not full document text. Includes post-processing to clean up any noise.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from core.config import Config
from vertex.answer import EXTRACT_PREAMBLE


@dataclass
class FillResult:
    placeholder: str
    query: str
    answer: str
    sources: list[str] = field(default_factory=list)
    success: bool = True


def _clean_answer(text: str, placeholder: str) -> tuple[str, bool]:
    """Post-process a RAG answer to remove noise and validate.

    Returns (cleaned_text, is_valid).
    """
    if not text:
        return "Not Available", False

    t = text.strip()

    # Mark as failed if Vertex said it can't answer.
    fail_phrases = [
        "could not be generated",
        "cannot be answered",
        "not found in the provided",
        "does not contain",
        "no information available",
        "not explicitly stated",
        "not mentioned in",
        "cannot determine",
        "NOT FOUND",
    ]
    t_lower = t.lower()
    for phrase in fail_phrases:
        if phrase.lower() in t_lower:
            return "Not Available", False

    # Block TEST values.
    if "TEST" in t and len(t) < 20:
        return "Not Available", False

    # If the answer is way too long (>300 chars), it's probably dumping doc text.
    # Truncate to first sentence.
    if len(t) > 300:
        # Try to get just the first meaningful sentence.
        sentences = re.split(r'(?<=[.!?])\s+', t)
        if sentences:
            # Find the first sentence that contains actual data (not preamble).
            for s in sentences[:3]:
                s = s.strip()
                if len(s) > 10 and not s.lower().startswith(("the provided", "according to", "based on")):
                    t = s
                    break
            else:
                t = sentences[0]

    # Remove common AI preamble phrases.
    preamble_patterns = [
        r"^(?:Based on|According to|The|From) (?:the |my |)(?:provided |available |)(?:documents?|sources?|information|data)[,.]?\s*",
        r"^(?:The |)(?:answer|response|value|result) (?:is|to this is)[:\s]+",
    ]
    for pat in preamble_patterns:
        t = re.sub(pat, "", t, flags=re.IGNORECASE).strip()

    # Remove trailing periods from short values.
    if len(t) < 50 and t.endswith("."):
        t = t[:-1].strip()

    if not t:
        return "Not Available", False

    return t, True


class DraftingEngine:
    def __init__(self, cfg: Config, property_: str | None = None,
                 doc_type: str | None = None, delay: float = 4.0,
                 max_retries: int = 3, log=print):
        self.cfg = cfg
        self.property = property_
        self.doc_type = doc_type
        self.delay = delay
        self.max_retries = max_retries
        self.log = log
        self._cache: dict[str, FillResult] = {}
        self._call_count = 0

    def _throttle(self):
        if self._call_count > 0 and self.delay > 0:
            time.sleep(self.delay)
        self._call_count += 1

    def _resolve(self, placeholder: str, query_spec: dict | None = None) -> FillResult:
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
                a = answer(self.cfg, query_text, property_=prop, doc_type=dt,
                           preamble=EXTRACT_PREAMBLE)
                raw = a.text or ""

                # Post-process the answer.
                cleaned, valid = _clean_answer(raw, placeholder)

                src_names = [s.get("title", "") for s in a.sources if s.get("title")]
                result = FillResult(
                    placeholder=placeholder, query=query_text,
                    answer=cleaned, sources=src_names, success=valid,
                )
                self._cache[cache_key] = result
                return result

            except Exception as e:
                last_err = e
                err_str = str(e)
                if "429" in err_str or "quota" in err_str.lower():
                    wait = self.delay * (2 ** attempt) + 2
                    self.log(f"    rate limited on '{placeholder}', retrying in {wait:.0f}s...")
                    time.sleep(wait)
                elif "503" in err_str:
                    wait = self.delay * (attempt + 1)
                    self.log(f"    503 on '{placeholder}', retrying in {wait:.0f}s...")
                    time.sleep(wait)
                else:
                    break

        result = FillResult(
            placeholder=placeholder, query=query_text,
            answer="Not Available", success=False,
        )
        self._cache[cache_key] = result
        return result

    def fill(self, template_text: str, query_map: dict | None = None) -> tuple[str, list[FillResult]]:
        query_map = query_map or {}
        results: list[FillResult] = []
        seen: set[str] = set()
        total = len(set(re.findall(r"\{\{(.+?)\}\}", template_text)))

        def replacer(match):
            name = match.group(1).strip()
            if name in seen:
                cached = next((r for r in results if r.placeholder == name), None)
                return cached.answer if cached else match.group(0)
            seen.add(name)
            spec = query_map.get(name)
            self.log(f"  [{len(seen)}/{total}] {name}...")
            result = self._resolve(name, spec)
            status = "Y" if result.success else "X"
            self.log(f"         {status} {result.answer[:60]}")
            results.append(result)
            return result.answer

        filled = re.sub(r"\{\{(.+?)\}\}", replacer, template_text)
        return filled, results


def load_query_map(queries_path: Path) -> dict:
    if not queries_path.exists():
        return {}
    with queries_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("placeholders", data)

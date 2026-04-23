"""
Phase 4B: Job Intelligence Engine
===================================
Two-stage pipeline:
  1. Vertex AI Search  →  retrieve relevant document excerpts
  2. Gemini 1.5 Pro    →  synthesize a direct, sourced answer

Key features:
  - Multi-turn conversation: Bob can ask follow-ups without re-stating the job
  - Job context tracking: detects which job/address is "in focus"
  - Confidence scoring: tells Bob when sources are thin
  - Structured response format: answer + sources + gaps + suggested follow-ups

INSTALL:
    pip install google-generativeai google-cloud-discoveryengine
"""

import os
import re
import uuid
import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import google.generativeai as genai
from google.cloud import discoveryengine_v1 as discoveryengine
from google.oauth2 import service_account
from google.api_core.client_options import ClientOptions

# ── Config — all values read from environment / .env ─────────────────────────
# The bootstrap writes these into Phase3_Bootstrap/secrets/.env automatically.
import os as _os
from pathlib import Path as _Path

PROJECT_ID   = _os.getenv("GCP_PROJECT_ID",       "commanding-way-380716")
ENGINE_ID    = _os.getenv("VERTEX_ENGINE_ID",      "madison-ave-search-app")
LOCATION     = _os.getenv("GCP_LOCATION",          "global")
GEMINI_MODEL = _os.getenv("GEMINI_MODEL",          "gemini-1.5-flash")
MAX_RESULTS  = 12
MAX_SEGMENTS = 20
MAX_HISTORY  = 8
SESSION_TTL  = 3600

def _resolve_sa_key() -> str:
    explicit = _os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if explicit and _Path(explicit).exists():
        return explicit
    bootstrap_key = _Path(__file__).resolve().parent.parent / "Phase3_Bootstrap" / "secrets" / "service-account.json"
    if bootstrap_key.exists():
        return str(bootstrap_key)
    local_key = _Path(__file__).parent / "service-account.json"
    if local_key.exists():
        return str(local_key)
    return "service-account.json"

SA_KEY = _resolve_sa_key()


# ── System prompt  ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the Madison Ave Construction Intelligence Assistant.
Your job is to help Bob — the company owner — get direct, accurate answers about 
his restoration and renovation jobs, insurance claims, invoices, permits, and clients.

RULES:
1. Answer using ONLY the document excerpts provided. Never invent addresses, dollar 
   amounts, dates, permit numbers, or insurer names.
2. For financial figures: state the number, which document it came from, and note if 
   the source could be partial (e.g., one invoice ≠ total job cost).
3. For status questions: structure your answer as:
   • Current Stage → Key Dates → Open Items → Money Summary
4. If the documents don't clearly answer the question, say exactly what you DID find
   and what is missing. Bob can then pull the right document.
5. Use conversation history to understand "that job," "the Brooklyn property," or 
   "that claim" without Bob having to repeat himself.
6. Be direct. Bob is an owner, not a first-time user. No preambles like "Great question!"
7. If you detect conflicting data across documents, flag it: "Note: Doc A says X, Doc B says Y."
8. Keep answers under 300 words unless a detailed breakdown is requested.

DOMAIN CONTEXT:
Madison Ave Construction does 24/7 emergency restoration (water, fire, storm, mold) 
on Long Island and NYC. Key document types: permits, insurance claim letters, 
Xactimate estimates, invoices, P&L statements, inspection reports, property inventories, 
appraisals, contractor notices, and closing docs. Job folders follow: 00-Intake, 
01-Photos, 02-Mitigation, 03-Estimate, 04-Insurance, 05-Permits, 06-Invoices, 
07-Customer-Comms, 08-Completion."""


# ── Data classes ──────────────────────────────────────────────────────────────
@dataclass
class ChatMessage:
    role: str     # "user" or "model"
    text: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ChatSession:
    session_id:   str
    history:      list[ChatMessage] = field(default_factory=list)
    job_context:  Optional[str] = None   # current job address / ID in focus
    created_at:   float = field(default_factory=time.time)
    last_active:  float = field(default_factory=time.time)


@dataclass
class IntelligenceResponse:
    answer:          str
    sources:         list[str]
    search_results:  int
    confidence:      str          # "high" | "medium" | "low" | "none"
    job_context:     Optional[str]
    suggested_followups: list[str]
    media_links:     list[dict] = field(default_factory=list)
    # media_links entries:
    #   photo pointer: {type:"photos", property:str, count:int, url:str}
    #   large pdf:     {type:"document", title:str, size_mb:float, url:str}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _load_creds():
    key_path = Path(__file__).parent / SA_KEY
    if not key_path.exists():
        key_path = Path(SA_KEY)
    return service_account.Credentials.from_service_account_file(
        str(key_path),
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )


def _extract_job_context(text: str) -> Optional[str]:
    """
    Try to detect a job address or ID from a user message.
    Returns a normalized string like "332 Parkville Ave" if found.
    """
    # Look for street-address patterns
    addr = re.search(
        r"\d{1,5}\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}"
        r"(?:\s+(?:Ave|Blvd|St|Rd|Dr|Ln|Way|Ct|Pl|Terr|Ter|Circle|Cir)\.?)?",
        text
    )
    if addr:
        return addr.group(0).strip()

    # Look for job IDs like JOB-2024-001
    job_id = re.search(r"\bJOB[-_]\d{4}[-_]\d{2,4}\b", text, re.IGNORECASE)
    if job_id:
        return job_id.group(0).upper()

    return None


def _score_confidence(excerpt_count: int, has_direct_hit: bool) -> str:
    """Rate how confident we are based on retrieval quality."""
    if excerpt_count == 0:
        return "none"
    if excerpt_count >= 5 and has_direct_hit:
        return "high"
    if excerpt_count >= 2:
        return "medium"
    return "low"


def _suggest_followups(query: str, job_context: Optional[str]) -> list[str]:
    """Generate contextual follow-up suggestions."""
    q = query.lower()
    suggestions = []

    if any(w in q for w in ["invoice", "payment", "owe", "paid", "balance"]):
        suggestions += ["Are there any other open invoices?", "What's the total project cost?"]
    elif any(w in q for w in ["permit", "inspection"]):
        suggestions += ["When does the permit expire?", "Are there any failed inspections?"]
    elif any(w in q for w in ["status", "progress", "stage"]):
        suggestions += ["What's still open on this job?", "Any insurance issues?"]
    elif any(w in q for w in ["claim", "insurance", "adjuster"]):
        suggestions += ["Has the adjuster responded?", "What's the approved scope amount?"]
    elif any(w in q for w in ["estimate", "scope", "xactimate"]):
        suggestions += ["Has the insurer approved the scope?", "Any change orders?"]

    if job_context and "job" not in q:
        suggestions.append(f"What documents do we have for {job_context}?")

    return suggestions[:3]


# ── Core engine ───────────────────────────────────────────────────────────────
class JobIntelligence:
    """
    Two-stage RAG: Vertex AI Search (retrieval) → Gemini Pro (synthesis).
    Maintains per-session conversation history and job context.
    """

    def __init__(self):
        # Gemini setup
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
        else:
            # Fall back to service account for Vertex-hosted Gemini
            creds = _load_creds()
            genai.configure(credentials=creds)

        self._gemini = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT,
        )

        # Vertex AI Search client
        self._search_client = discoveryengine.SearchServiceClient(
            credentials=_load_creds(),
            client_options=ClientOptions(
                api_endpoint=f"{LOCATION}-discoveryengine.googleapis.com"
                if LOCATION != "global"
                else "discoveryengine.googleapis.com"
            )
        )
        self._serving_config = (
            f"projects/{PROJECT_ID}/locations/{LOCATION}/"
            f"collections/default_collection/engines/{ENGINE_ID}/"
            f"servingConfigs/default_search"
        )

        # Session store
        self._sessions: dict[str, ChatSession] = {}

    # ── Session management ─────────────────────────────────────────────────
    def new_session(self) -> str:
        sid = str(uuid.uuid4())
        self._sessions[sid] = ChatSession(session_id=sid)
        self._cleanup_old_sessions()
        return sid

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        sess = self._sessions.get(session_id)
        if sess:
            # Expire old sessions
            if time.time() - sess.last_active > SESSION_TTL:
                del self._sessions[session_id]
                return None
        return sess

    def _cleanup_old_sessions(self):
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.last_active > SESSION_TTL
        ]
        for sid in expired:
            del self._sessions[sid]

    # ── Vertex retrieval ───────────────────────────────────────────────────
    def retrieve(self, query: str, job_context: Optional[str] = None) -> list[dict]:
        """
        Query Vertex AI Search and return a list of excerpt dicts:
        {"source": str, "content": str}
        """
        # If we have a job context, prepend it to sharpen retrieval
        search_query = query
        if job_context:
            search_query = f"{job_context} {query}"

        request = discoveryengine.SearchRequest(
            serving_config=self._serving_config,
            query=search_query,
            page_size=MAX_RESULTS,
            content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                extractive_content_spec=(
                    discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                        max_extractive_answer_count=3,
                        max_extractive_segment_count=MAX_SEGMENTS,
                    )
                )
                # NOTE: skip snippet_spec — proto marshaling bug with 'list' WhichOneof
            ),
        )

        try:
            response = self._search_client.search(request)
        except Exception as e:
            print(f"[Vertex] Search error: {e}")
            return []

        excerpts     = []
        media_links  = []

        for result in response.results:
            doc = result.document

            # Read struct_data safely
            struct = {}
            try:
                if doc.struct_data:
                    struct = dict(doc.struct_data)
            except Exception:
                pass

            source_uri   = struct.get("source_uri", "")
            doc_type     = struct.get("document_type", "")
            onedrive_url = struct.get("onedrive_url", "")

            # ── Pointer docs: extract media links, skip content extraction ──
            if doc_type == "photo_index":
                prop_name   = struct.get("property", struct.get("title", "Property"))
                photo_count = struct.get("photo_count", 0)
                if onedrive_url:
                    media_links.append({
                        "type":     "photos",
                        "property": prop_name,
                        "count":    photo_count,
                        "url":      onedrive_url,
                    })
                # Also inject a brief content note so Gemini knows about photos
                excerpts.append({
                    "source":  f"{prop_name} (photo index)",
                    "content": f"{photo_count} photos available for {prop_name} in OneDrive.",
                })
                continue

            if doc_type == "large_pdf_pointer":
                title   = struct.get("title", "Document")
                size_mb = struct.get("size_mb", 0)
                gcs_uri = struct.get("gcs_uri", "")
                media_links.append({
                    "type":    "document",
                    "title":   title,
                    "size_mb": size_mb,
                    "url":     gcs_uri,
                })
                excerpts.append({
                    "source":  title,
                    "content": struct.get("summary", f"Large PDF: {title} ({size_mb:.1f} MB)"),
                })
                continue

            # ── Regular docs: extract content ──────────────────────────────
            content = ""
            try:
                if doc.derived_struct_data:
                    dsd = dict(doc.derived_struct_data)
                    answers = dsd.get("extractive_answers", [])
                    if isinstance(answers, list):
                        for ans in answers:
                            if isinstance(ans, dict):
                                content += ans.get("content", "") + "\n"
                    if not content:
                        segs = dsd.get("extractive_segments", [])
                        if isinstance(segs, list):
                            for seg in segs:
                                if isinstance(seg, dict):
                                    content += seg.get("content", "") + "\n"
            except Exception:
                pass

            if content.strip():
                source_label = (
                    Path(source_uri).name if source_uri
                    else (doc.id or "Unknown source")
                )
                excerpts.append({
                    "source":  source_label,
                    "content": content.strip(),
                })

        # Deduplicate media links by URL
        seen_urls = set()
        unique_media = []
        for m in media_links:
            if m.get("url") and m["url"] not in seen_urls:
                seen_urls.add(m["url"])
                unique_media.append(m)

        return excerpts, unique_media

    # ── Gemini synthesis ───────────────────────────────────────────────────
    def synthesize(
        self,
        query:      str,
        excerpts:   list[dict],
        session:    Optional[ChatSession] = None,
    ) -> str:
        """
        Build a prompt from excerpts + conversation history and call Gemini.
        Returns the raw answer text.
        """
        # Format document excerpts
        if excerpts:
            ctx_parts = []
            for i, exc in enumerate(excerpts, 1):
                ctx_parts.append(
                    f"[SOURCE {i} — {exc['source']}]\n{exc['content']}"
                )
            context_block = "\n\n─────\n\n".join(ctx_parts)
        else:
            context_block = "(No relevant documents retrieved for this query.)"

        # Build conversation history for Gemini
        history = []
        if session and session.history:
            # Keep last N turns, converting to Gemini format
            recent = session.history[-(MAX_HISTORY * 2):]
            for msg in recent:
                history.append({
                    "role":  msg.role,
                    "parts": [msg.text]
                })

        # Build the user turn
        job_hint = (
            f"\n[Current job in focus: {session.job_context}]"
            if session and session.job_context
            else ""
        )
        prompt = (
            f"DOCUMENT EXCERPTS:\n{context_block}\n\n"
            f"{'─' * 40}{job_hint}\n\n"
            f"Bob's question: {query}"
        )

        try:
            chat = self._gemini.start_chat(history=history)
            response = chat.send_message(prompt)
            return response.text
        except Exception as e:
            print(f"[Gemini] Synthesis error: {e}")
            return (
                "I hit an error generating your answer. "
                f"Vertex retrieved {len(excerpts)} document excerpt(s) — "
                "please try rephrasing or check the logs."
            )

    # ── Main entry point ───────────────────────────────────────────────────
    def chat(self, query: str, session_id: Optional[str] = None) -> IntelligenceResponse:
        """
        Full pipeline: retrieve → synthesize → return structured response.
        Creates a new session if session_id is None or invalid.
        """
        # Resolve session
        session = None
        if session_id:
            session = self.get_session(session_id)
        if session is None:
            sid = self.new_session()
            session = self._sessions[sid]

        # Update job context if a new address/ID is mentioned
        detected = _extract_job_context(query)
        if detected:
            session.job_context = detected

        # Stage 1: Vertex retrieval
        excerpts, media_links = self.retrieve(query, job_context=session.job_context)

        # Stage 2: Gemini synthesis
        answer = self.synthesize(query, excerpts, session)

        # Update session history
        session.history.append(ChatMessage(role="user",  text=query))
        session.history.append(ChatMessage(role="model", text=answer))
        session.last_active = time.time()

        # Score confidence
        has_direct = any(
            any(word in exc["content"].lower() for word in query.lower().split()[:4])
            for exc in excerpts
        )
        confidence = _score_confidence(len(excerpts), has_direct)
        followups  = _suggest_followups(query, session.job_context)
        sources    = list({exc["source"] for exc in excerpts})

        return IntelligenceResponse(
            answer=answer,
            sources=sources,
            search_results=len(excerpts),
            confidence=confidence,
            job_context=session.job_context,
            suggested_followups=followups,
            media_links=media_links,
        )

    def clear_session(self, session_id: str):
        """Reset conversation history while keeping the session alive."""
        session = self.get_session(session_id)
        if session:
            session.history.clear()
            session.job_context = None


# ── Singleton for Flask app ───────────────────────────────────────────────────
_intelligence: Optional[JobIntelligence] = None


def get_intelligence() -> JobIntelligence:
    """Return the app-level singleton, initializing on first call."""
    global _intelligence
    if _intelligence is None:
        _intelligence = JobIntelligence()
    return _intelligence
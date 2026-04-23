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
from google.protobuf.json_format import MessageToDict

# ── Config — all values read from environment / .env ─────────────────────────
# The bootstrap writes these into Phase3_Bootstrap/secrets/.env automatically.
import os as _os
from pathlib import Path as _Path

PROJECT_ID   = _os.getenv("GCP_PROJECT_ID",       "commanding-way-380716")
ENGINE_ID    = _os.getenv("VERTEX_ENGINE_ID",      "madison-ave-search-app")
LOCATION     = _os.getenv("GCP_LOCATION",          "global")
GEMINI_MODEL = _os.getenv("GEMINI_MODEL",          "gemini-1.5-flash")
MAX_RESULTS  = 20
MAX_SEGMENTS = 10
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
SYSTEM_PROMPT = """You are a real estate investment intelligence assistant.
Your job is to help the portfolio owner get direct, accurate answers about
their properties, deals, financials, legal documents, and investment performance.

RULES:
1. Answer using ONLY the document excerpts provided. Never invent addresses,
   dollar amounts, dates, entity names, or lender details.
2. For financial figures: state the number, cite the source document, and note
   if the figure may be partial (e.g., one invoice does not equal total project cost).
3. For property questions, structure answers as:
   • Property → Appraisal / Purchase Price → Key Dates → Financial Summary → Open Items
4. If documents don't clearly answer the question, say exactly what you DID find
   and what is missing. The owner can then pull the right document.
5. Use conversation history to track which property is "in focus" so the owner
   does not have to repeat the address on every follow-up.
6. Be direct and concise. No preambles like "Great question!" or "Certainly!"
7. If you detect conflicting figures across documents, flag it explicitly:
   "Note: Doc A shows X, Doc B shows Y — verify which is current."
8. When a photo pointer doc appears in results, mention the OneDrive link naturally:
   e.g. "157 photos are available for this property — see the link below."
9. Keep answers under 300 words unless a detailed breakdown is explicitly requested.
10. For portfolio-wide questions, summarize what the indexed documents show and
    note that totals may be incomplete if not all docs are indexed.

DOMAIN CONTEXT:
This is a real estate investment portfolio operating on Long Island, NY.
Properties are acquired, renovated, and sold or held for income.
Key document types indexed:
  - Appraisals (market value, comparables, appraiser name)
  - Closing packages (purchase/sale contracts, HUD statements, deed, title)
  - Title reports (liens, encumbrances, ownership chain)
  - P&L statements and monthly financial summaries
  - Scope of work (SOW) documents
  - Permits and certificates of occupancy
  - Inspection reports (building, electrical, mold, asbestos)
  - Flood and property disclosures
  - Loan approval letters and lender correspondence
  - Invoices from contractors and vendors
  - Insurance policies and flood zone documents
  - Entity formation docs (LLC operating agreements, EIN letters)
Property folders follow: /files/ (documents) and /photos/ (field photos in OneDrive).
LLC entities include: Bobbomatic LLC, Flip It LLC, Shearwater Way LLC, Lama Drive LLC."""


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
    media_links:     list[dict] = field(default_factory=list)  # photo pointers + large PDFs
    source_uris:     dict       = field(default_factory=dict)   # {filename: gs://uri} for download


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
    def retrieve(self, query: str, job_context: Optional[str] = None) -> tuple:
        """
        Query Vertex AI Search.
        Returns: (excerpts, media_links)
          excerpts    — list of {"source": str, "source_uri": str, "content": str}
          media_links — list of {"type": "photo"|"large_pdf", "title": str,
                                  "url": str, "count": int}
        """
        search_query = query
        if job_context:
            search_query = f"{job_context} {query}"

        request = discoveryengine.SearchRequest(
            serving_config=self._serving_config,
            query=search_query,
            page_size=MAX_RESULTS,
            content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                    return_snippet=True,
                ),
                summary_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                    summary_result_count=10,
                    include_citations=True,
                    ignore_adversarial_query=True,
                    ignore_non_summary_seeking_query=False,
                ),
            ),
        )

        try:
            response = self._search_client.search(request)
            results  = list(response)
        except Exception as e:
            print("[Vertex] Search error:", e)
            return [], []

        excerpts    = []
        media_links = []

        for result in results:
            doc = result.document

            # Read all struct_data fields safely
            struct = {}
            try:
                if doc.struct_data:
                    struct = dict(doc.struct_data)
            except Exception:
                pass

            source_uri   = struct.get("source_uri", "")
            doc_type     = struct.get("document_type", "")
            onedrive_url = struct.get("onedrive_url", "")
            photo_count  = struct.get("photo_count", 0)
            title        = struct.get("title", doc.id or "Unknown")

            # Photo pointer docs → media_links, skip from excerpts
            if doc_type == "photo_index" and onedrive_url:
                media_links.append({
                    "type":  "photo",
                    "title": title,
                    "url":   onedrive_url,
                    "count": int(photo_count) if photo_count else 0,
                })
                continue

            # Large PDF pointers → media_links
            if doc_type == "large_pdf_pointer":
                gcs_uri = struct.get("gcs_uri", source_uri)
                media_links.append({
                    "type":  "large_pdf",
                    "title": title,
                    "url":   gcs_uri,
                    "count": 0,
                })
                continue

            # Regular docs -- collect source label for citation
            # Content comes from response.summary.summary_text (read after loop)
            source_label = Path(source_uri).name if source_uri else title
            if source_label and source_label not in ("Unknown", ""):
                excerpts.append({
                    "source":     source_label,
                    "source_uri": source_uri,
                    "content":    "",   # filled in below from Vertex summary
                })

        # Read Vertex summary AFTER pager is materialized (critical ordering)
        # Distribute summary text into the first excerpt so Gemini has context
        try:
            summary_text = ""
            if hasattr(response, "summary") and response.summary:
                summary_text = response.summary.summary_text or ""
            if summary_text and excerpts:
                excerpts[0]["content"] = summary_text
            elif summary_text:
                excerpts.append({
                    "source":     "Vertex Summary",
                    "source_uri": "",
                    "content":    summary_text,
                })
        except Exception as e:
            print("[Vertex] Summary read error:", e)

        # Drop any excerpts that ended up with no content
        excerpts = [e for e in excerpts if e["content"].strip()]

        return excerpts, media_links


    # ── Photo pointer lookup ───────────────────────────────────────────────
    def _photo_lookup(self, address: str) -> list[dict]:
        """
        Dedicated search for photo_index pointer docs.
        Detects photo pointers two ways:
          1. struct_data.document_type == "photo_index"  (after permanent sync fix)
          2. doc.id starts with "photo_pointer"          (jsonData-only imports)
        For case 2, parses the OneDrive URL from snippet text via regex.
        """
        import re as _re
        if not address:
            return []

        queries = [
            f"{address} photos OneDrive images",
            f"photo pointer {address} photos",
        ]
        media_links = []
        seen_urls:  set = set()
        seen_ids:   set = set()

        for q in queries:
            try:
                req = discoveryengine.SearchRequest(
                    serving_config=self._serving_config,
                    query=q,
                    page_size=30,
                    content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                        snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                            return_snippet=True),
                        summary_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                            summary_result_count=10,
                            include_citations=False,
                            ignore_adversarial_query=True,
                            ignore_non_summary_seeking_query=False,
                        ),
                    ),
                )
                resp    = self._search_client.search(req)
                results = list(resp)

                for r in results:
                    doc = r.document
                    if doc.id in seen_ids:
                        continue
                    seen_ids.add(doc.id)

                    # Path 1: struct_data populated (after sync fix)
                    struct = {}
                    try:
                        if doc.struct_data:
                            struct = dict(doc.struct_data)
                    except Exception:
                        pass

                    doc_type     = struct.get("document_type", "")
                    onedrive_url = struct.get("onedrive_url", "")
                    title        = struct.get("title", "")
                    photo_count  = struct.get("photo_count", 0)

                    if doc_type == "photo_index" and onedrive_url:
                        if onedrive_url not in seen_urls:
                            seen_urls.add(onedrive_url)
                            media_links.append({
                                "type":  "photo",
                                "title": title,
                                "url":   onedrive_url,
                                "count": int(photo_count) if photo_count else 0,
                            })
                        continue

                    # Path 2: jsonData-only doc — detect by doc.id prefix
                    if not doc.id.startswith("photo_pointer"):
                        continue

                    # Extract OneDrive URL from snippet or summary text
                    snippet_text = ""
                    try:
                        from google.protobuf.json_format import MessageToDict as _M2D
                        dsd = _M2D(doc.derived_struct_data)
                        for s in dsd.get("snippets", []):
                            snippet_text += s.get("snippet", "") + " "
                    except Exception:
                        pass

                    # Also try reading from the Vertex per-result extractive content
                    url_match   = _re.search(r"https://\S+sharepoint\S+", snippet_text)
                    count_match = _re.search(r"(\d+)\s+photos?", snippet_text, _re.IGNORECASE)
                    title_match = _re.search(r'"title":\s*"([^"]+)"', snippet_text)

                    if url_match:
                        od_url = url_match.group(0).rstrip(".,;")
                        if od_url not in seen_urls:
                            seen_urls.add(od_url)
                            t = title_match.group(1) if title_match else f"{address} — Photos"
                            c = int(count_match.group(1)) if count_match else 0
                            media_links.append({
                                "type":  "photo",
                                "title": t,
                                "url":   od_url,
                                "count": c,
                            })
                    else:
                        # URL not in snippet — record placeholder so user knows photos exist
                        if doc.id not in seen_ids:
                            t = title_match.group(1) if title_match else f"{address} — Photos"
                            c = int(count_match.group(1)) if count_match else 0
                            media_links.append({
                                "type":  "photo",
                                "title": t + " (open OneDrive to view)",
                                "url":   "#",
                                "count": c,
                            })

            except Exception as e:
                print(f"[Vertex] Photo lookup error: {e}")

        return media_links

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

        # Supplement with dedicated photo lookup if query is photo-related
        _photo_words = ("photo", "photos", "picture", "pictures", "image", "images", "show me")
        if any(w in query.lower() for w in _photo_words):
            extra = self._photo_lookup(session.job_context or query)
            seen  = {m["url"] for m in media_links}
            media_links += [m for m in extra if m["url"] not in seen]

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
        sources     = list({exc["source"] for exc in excerpts})
        source_uris = {exc["source"]: exc.get("source_uri", "") for exc in excerpts}

        return IntelligenceResponse(
            answer=answer,
            sources=sources,
            search_results=len(excerpts),
            confidence=confidence,
            job_context=session.job_context,
            suggested_followups=followups,
            media_links=media_links,
            source_uris=source_uris,
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

"""
Phase 4 Job Intelligence — uses identical search pattern to simple_web.py.
Gemini rewrites the Vertex summary conversationally when available.
"""
import os, re, uuid, time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from google.cloud import discoveryengine_v1 as discoveryengine
from google.oauth2 import service_account
import google.auth
import google.generativeai as genai

SERVING_CONFIG = os.getenv("VERTEX_SERVING_CONFIG", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
SESSION_TTL    = 3600
MAX_HISTORY    = 6

SYSTEM_PROMPT = """You are MAC, the Madison Ave Construction assistant.
Bob (the owner) is asking about his jobs, permits, loans, appraisals, and claims.
You will receive a Vertex AI summary of his documents plus conversation history.
Rewrite the summary in a direct, conversational way for Bob — no fluff.
If the summary already answers the question clearly, keep it concise.
Highlight any key numbers, dates, or names. Under 250 words."""

def _load_creds():
    for key in [
        Path(__file__).resolve().parent.parent / "service-account.json",
        Path(__file__).resolve().parent / "service-account.json",
    ]:
        if key.exists():
            return service_account.Credentials.from_service_account_file(
                str(key), scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return creds

def _safe_struct_get(struct, key, default=""):
    if struct is None: return default
    try:
        if hasattr(struct,"get"): val = struct.get(key, default)
        else: val = struct[key] if key in struct else default
        return str(val or default)
    except: return default

NO_RESULT = ("no results could be found","try rephrasing","i could not find","summary could not be generated")

def _is_empty(text):
    if not text: return True
    return any(m in text.lower() for m in NO_RESULT)

@dataclass
class ChatMessage:
    role: str; text: str
    timestamp: float = field(default_factory=time.time)

@dataclass
class ChatSession:
    session_id: str
    history: list = field(default_factory=list)
    job_context: Optional[str] = None
    last_active: float = field(default_factory=time.time)

@dataclass
class IntelligenceResponse:
    answer: str; sources: list; search_results: int
    confidence: str; job_context: Optional[str]; suggested_followups: list

def _extract_job_context(text):
    m = re.search(r"\d{1,5}\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}(?:\s+(?:Ave|Blvd|St|Rd|Dr|Ln|Way|Ct|Pl)\.?)?", text)
    return m.group(0).strip() if m else None

def _score(n):
    if n == 0: return "none"
    if n >= 5: return "high"
    if n >= 2: return "medium"
    return "low"

def _followups(query, ctx):
    q = query.lower(); s = []
    if any(w in q for w in ["loan","draw","balance","payment"]): s += ["Any other draws?","Current loan balance?"]
    elif any(w in q for w in ["permit","inspection","certificate"]): s += ["When does it expire?","Any failed inspections?"]
    elif any(w in q for w in ["apprais","value","comparable"]): s += ["Comparable sales used?","Site value?"]
    elif any(w in q for w in ["claim","insurance","adjuster"]): s += ["Who is the insurer?","Approved scope amount?"]
    elif any(w in q for w in ["owner","lender","contact"]): s += ["Permits for this owner?","Who is the lender?"]
    else: s += ["Any permits on file?","What documents exist for this job?"]
    if ctx: s.append(f"More on {ctx}?")
    return s[:3]

class JobIntelligence:
    def __init__(self):
        self._creds = _load_creds()
        self._sessions = {}
        self._use_gemini = False
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self._gemini = genai.GenerativeModel(model_name=GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)
                self._use_gemini = True
                print(f"[Phase4] Gemini synthesis ON ({GEMINI_MODEL})")
            except Exception as e:
                print(f"[Phase4] Gemini init failed, using Vertex summary only: {e}")
        else:
            print("[Phase4] No GEMINI_API_KEY — using Vertex summary only")

    def new_session(self):
        sid = str(uuid.uuid4())
        self._sessions[sid] = ChatSession(session_id=sid)
        return sid

    def get_session(self, sid):
        s = self._sessions.get(sid)
        if s and time.time() - s.last_active > SESSION_TTL:
            del self._sessions[sid]; return None
        return s

    def _vertex_search(self, query):
        """Exact same pattern as simple_web.py — proven working."""
        client = discoveryengine.SearchServiceClient(credentials=self._creds)
        content_spec = discoveryengine.SearchRequest.ContentSearchSpec(
            snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                return_snippet=True),
            summary_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                summary_result_count=10,
                include_citations=True,
                ignore_adversarial_query=True,
                ignore_non_summary_seeking_query=False,
                model_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec.ModelSpec(
                    version="stable")))
        req = discoveryengine.SearchRequest(
            serving_config=SERVING_CONFIG, query=query,
            page_size=10, content_search_spec=content_spec)

        response = client.search(req)
        results  = list(response)   # materialize FIRST — required for summary

        summary = ""
        if hasattr(response,"summary") and response.summary:
            summary = response.summary.summary_text or ""

        sources = []
        seen = set()
        for r in results:
            doc = r.document
            title = _safe_struct_get(doc.struct_data, "title", "")
            uri   = _safe_struct_get(doc.struct_data, "uri",   "")
            if not title:
                title = _safe_struct_get(doc.derived_struct_data, "title", "")
            label = title or (Path(uri).name if uri else doc.id or "Document")
            if label and label not in seen:
                seen.add(label)
                sources.append({"title": label, "uri": uri})

        return summary, sources[:5]

    def chat(self, query, session_id=None):
        session = self.get_session(session_id) if session_id else None
        if not session:
            sid = self.new_session(); session = self._sessions[sid]

        detected = _extract_job_context(query)
        if detected: session.job_context = detected

        full_query = f"{session.job_context} {query}" if session.job_context else query

        try:
            summary, sources = self._vertex_search(full_query)
        except Exception as e:
            print(f"[Vertex] {e}")
            summary, sources = "", []

        if _is_empty(summary) or not sources:
            hint = f" (focused on: {session.job_context})" if session.job_context else ""
            answer = (f"Nothing found{hint}. Try a specific address, "
                      f"permit number, loan number, dollar amount, or name.")
            sources = []
        elif self._use_gemini and summary:
            # Gemini rewrites Vertex summary conversationally with history context
            history = [{"role": m.role, "parts": [m.text]} for m in session.history[-(MAX_HISTORY*2):]]
            hint = f"\n[Job in focus: {session.job_context}]" if session.job_context else ""
            src_list = ", ".join(s["title"] for s in sources)
            prompt = (f"Sources: {src_list}{hint}\n\n"
                      f"Vertex summary:\n{summary}\n\n"
                      f"Bob's question: {query}")
            try:
                answer = self._gemini.start_chat(history=history).send_message(prompt).text
            except Exception as e:
                print(f"[Gemini] {e} — using Vertex summary as-is")
                answer = summary
        else:
            answer = summary

        session.history.append(ChatMessage(role="user", text=query))
        session.history.append(ChatMessage(role="model", text=answer))
        session.last_active = time.time()

        return IntelligenceResponse(
            answer=answer, sources=sources,
            search_results=len(sources), confidence=_score(len(sources)),
            job_context=session.job_context,
            suggested_followups=_followups(query, session.job_context))

    def clear_session(self, sid):
        s = self.get_session(sid)
        if s: s.history.clear(); s.job_context = None

_intel = None
def get_intelligence():
    global _intel
    if _intel is None: _intel = JobIntelligence()
    return _intel

"""Simple Flask web UI for Vertex AI Search.

Env file discovery (first match wins):
  1. $VERTEX_ENV_FILE (explicit override)
  2. <cwd>/Phase3_Bootstrap/secrets/.env         (typical workspace)
  3. <cwd>/.env                                   (user-provided at cwd root)
  4. <repo>/Phase3_Bootstrap/secrets/.env         (repo-local, for dev setups)
"""
import os
import sys
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request as flask_request
from dotenv import load_dotenv


def discover_env_file() -> Path | None:
    """Find the .env to use. Returns None if none found."""
    candidates = []

    override = os.environ.get("VERTEX_ENV_FILE")
    if override:
        candidates.append(Path(override))

    cwd = Path.cwd()
    candidates.append(cwd / "Phase3_Bootstrap" / "secrets" / ".env")
    candidates.append(cwd / ".env")

    repo_root = Path(__file__).resolve().parent.parent
    candidates.append(repo_root / "Phase3_Bootstrap" / "secrets" / ".env")

    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:
            continue
    return None


BOOTSTRAP_ENV = discover_env_file()
if BOOTSTRAP_ENV:
    print(f"✓ Loading env from: {BOOTSTRAP_ENV}")
    load_dotenv(BOOTSTRAP_ENV)
    SA_KEY_PATH = BOOTSTRAP_ENV.parent / "service-account.json"
else:
    print("⚠ No .env file found. Searched:")
    print("    $VERTEX_ENV_FILE (not set)" if not os.environ.get("VERTEX_ENV_FILE") else f"    $VERTEX_ENV_FILE = {os.environ.get('VERTEX_ENV_FILE')}")
    print(f"    {Path.cwd() / 'Phase3_Bootstrap' / 'secrets' / '.env'}")
    print(f"    {Path.cwd() / '.env'}")
    print(f"    {Path(__file__).resolve().parent.parent / 'Phase3_Bootstrap' / 'secrets' / '.env'}")
    print("")
    print("Fix: either cd into your workspace before running,")
    print("     or set VERTEX_ENV_FILE to the full path of your .env.")
    SA_KEY_PATH = Path(__file__).resolve().parent.parent / "Phase3_Bootstrap" / "secrets" / "service-account.json"

app = Flask(__name__)
app.secret_key = os.urandom(24)

COMPANY_NAME = os.getenv("COMPANY_NAME", "Document Search")
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
DATA_STORE_ID = os.getenv("VERTEX_DATA_STORE_ID")
ENGINE_ID = os.getenv("VERTEX_ENGINE_ID")
SERVING_CONFIG = os.getenv("VERTEX_SERVING_CONFIG")
GCS_RAW_BUCKET = os.getenv("GCS_BUCKET_RAW")
GCP_REGION = os.getenv("GCP_REGION", "us-east1")

print(f"\nConfiguration:")
print(f"  Company:    {COMPANY_NAME}")
print(f"  Project:    {PROJECT_ID or '(missing)'}")
print(f"  Region:     {GCP_REGION}")
print(f"  Data Store: {DATA_STORE_ID or '(missing)'}")
print(f"  Engine:     {ENGINE_ID or '(missing)'}")
print(f"  SA Key:     {SA_KEY_PATH} ({'exists' if SA_KEY_PATH.exists() else 'MISSING'})")
print()


# ---- Credential helpers ----------------------------------------------------
_CREDS = None

def get_creds():
    global _CREDS
    if _CREDS is None:
        from google.oauth2 import service_account
        if SA_KEY_PATH.exists():
            _CREDS = service_account.Credentials.from_service_account_file(
                str(SA_KEY_PATH),
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        else:
            import google.auth
            _CREDS, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
    return _CREDS


# ---- Safe struct-data accessor --------------------------------------------
def _safe_struct_get(struct, key: str, default: str = "") -> str:
    """Read a key from a proto-plus Struct (or dict) defensively.

    Handles the various shapes google-cloud-discoveryengine returns across
    versions: MapComposite, dict, proto Struct, None.
    """
    if struct is None:
        return default
    try:
        if hasattr(struct, "get") and callable(struct.get):
            val = struct.get(key, default)
        else:
            val = struct[key] if key in struct else default
        if val is None:
            return default
        return str(val)
    except Exception:
        return default


# ---- Response phrasing helpers ---------------------------------------------
NO_RESULT_MARKERS = (
    "no results could be found",
    "try rephrasing the search query",
    "i could not find",
    "the summary could not be generated",
)

def is_empty_answer(text: str) -> bool:
    if not text:
        return True
    t = text.strip().lower()
    return any(m in t for m in NO_RESULT_MARKERS)


def friendly_empty_message(query: str) -> str:
    return (
        f"I couldn't find anything in your indexed documents that matches "
        f"\"{query}\". Try a query about something that's actually in your "
        f"files — for example, a specific address, price, name, date, or "
        f"status that appears in the source material."
    )


# ---- HTML ------------------------------------------------------------------
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ company }} - AI Search</title>
<link href="https://cdnjs.cloudflare.com/ajax/libs/tailwindcss/2.2.19/tailwind.min.css" rel="stylesheet">
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;height:100vh;overflow:hidden;margin:0;}
  .chat-area{overflow-y:auto;scroll-behavior:smooth;}
  .msg-enter{animation:slideUp .3s ease-out;}
  @keyframes slideUp{from{opacity:0;transform:translateY(12px);}to{opacity:1;transform:translateY(0);}}
  .dot{animation:pulse 1.4s infinite;}.dot:nth-child(2){animation-delay:.2s;}.dot:nth-child(3){animation-delay:.4s;}
  @keyframes pulse{0%,80%,100%{opacity:.3;}40%{opacity:1;}}
  .status-badge{font-size:10px;padding:2px 8px;border-radius:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;}
  .answer-text p{margin-bottom:.5rem;}
  .source-card{background:white;border:1px solid #e2e8f0;border-radius:8px;padding:12px;transition:all .15s;}
  .source-card:hover{border-color:#3b82f6;box-shadow:0 2px 8px rgba(59,130,246,0.1);}
  @keyframes spin{to{transform:rotate(360deg);}} .spinner{animation:spin 1s linear infinite;display:inline-block;}
</style>
</head>
<body class="bg-gray-50">
<div class="flex flex-col h-full">
  <header class="bg-white border-b border-gray-200 px-6 py-4 flex-shrink-0">
    <div class="max-w-5xl mx-auto flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl flex items-center justify-center shadow-sm">
          <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
          </svg>
        </div>
        <div>
          <h1 class="text-lg font-bold text-gray-800">{{ company }}</h1>
          <p class="text-xs text-gray-500">AI Document Search</p>
        </div>
      </div>
      <div id="status-indicator" class="flex items-center gap-2">
        <div class="status-badge bg-yellow-100 text-yellow-700" id="status-text">Checking...</div>
      </div>
    </div>
  </header>

  <div id="chat" class="chat-area flex-1 px-6 py-6">
    <div class="max-w-4xl mx-auto">
      <div id="welcome" class="flex flex-col items-center justify-center py-20 msg-enter">
        <div class="w-20 h-20 bg-gradient-to-br from-blue-100 to-blue-50 rounded-3xl flex items-center justify-center mb-4 shadow-sm">
          <svg class="w-10 h-10 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
        </div>
        <h2 class="text-2xl font-bold text-gray-800 mb-2">Ask anything about your documents</h2>
        <p class="text-gray-500 text-sm mb-6 text-center max-w-md">Search finds content <em>inside</em> your files. Ask about specific names, places, dates, prices, or statuses that appear in the documents.</p>
        <div class="flex flex-wrap justify-center gap-2 max-w-2xl">
          <button onclick="ask('summarize all available properties')" class="px-4 py-2 bg-white border-2 border-gray-200 rounded-xl text-sm text-gray-700 hover:border-blue-400 hover:bg-blue-50 transition-all">
            📋 Summarize all properties
          </button>
          <button onclick="ask('list properties in contract')" class="px-4 py-2 bg-white border-2 border-gray-200 rounded-xl text-sm text-gray-700 hover:border-blue-400 hover:bg-blue-50 transition-all">
            📝 Properties in contract
          </button>
          <button onclick="ask('show most expensive property')" class="px-4 py-2 bg-white border-2 border-gray-200 rounded-xl text-sm text-gray-700 hover:border-blue-400 hover:bg-blue-50 transition-all">
            💰 Most expensive property
          </button>
        </div>
        <div id="data-status-msg" class="mt-8 p-4 bg-blue-50 border border-blue-200 rounded-xl max-w-lg" style="display:none;">
        </div>
      </div>
    </div>
  </div>

  <div class="border-t border-gray-200 bg-white px-6 py-4 flex-shrink-0">
    <div class="max-w-4xl mx-auto flex gap-3">
      <input id="qi" type="text" placeholder="Ask a question about your documents..." class="flex-1 px-4 py-3 rounded-xl border-2 border-gray-200 text-sm focus:border-blue-500 focus:outline-none" onkeydown="if(event.key==='Enter')sendQ()">
      <button onclick="sendQ()" class="px-6 py-3 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700 transition-all shadow-sm">
        Ask →
      </button>
    </div>
  </div>
</div>

<script>
const COMPANY_NAME = "{{ company_name }}";
const REGION = "{{ region }}";

let checkCount = 0;

function esc(t){const d=document.createElement('div');d.textContent=t;return d.innerHTML;}

async function checkDataStatus(){
  checkCount++;
  const badge = document.getElementById('status-text');
  const msg = document.getElementById('data-status-msg');

  let resp;
  try{
    const controller = new AbortController();
    const to = setTimeout(() => controller.abort(), 10000);
    resp = await fetch('/api/status', {signal: controller.signal});
    clearTimeout(to);
  }catch(e){
    badge.textContent = 'Offline';
    badge.className = 'status-badge bg-red-100 text-red-700';
    return;
  }

  let data;
  try{ data = await resp.json(); }
  catch(e){
    badge.textContent = 'Offline';
    badge.className = 'status-badge bg-red-100 text-red-700';
    return;
  }

  if(data.error){
    badge.textContent = 'Config error';
    badge.className = 'status-badge bg-red-100 text-red-700';
    msg.style.display = 'block';
    const hint = data.hint ? '<br><br><strong>Fix:</strong> ' + esc(data.hint) : '';
    msg.innerHTML = '<p class="text-sm text-red-800"><strong>⚠️ Backend error:</strong> ' + esc(data.error) + hint + '</p>';
    return;
  }

  if(data.documents > 0){
    badge.textContent = '✓ ' + data.documents + ' doc' + (data.documents === 1 ? '' : 's');
    badge.className = 'status-badge bg-green-100 text-green-700';
    msg.style.display = 'none';
    return;
  }

  if(checkCount <= 10){
    badge.innerHTML = '<span class="spinner">⏳</span> Indexing...';
    badge.className = 'status-badge bg-blue-100 text-blue-700';
    msg.style.display = 'block';
    msg.innerHTML = '<p class="text-sm text-blue-800"><strong>⏳ Indexing in progress</strong><br>Drive sync is processing your files. This usually takes 2–5 minutes. Auto-refreshes every 30s.</p>';
  }else{
    badge.textContent = 'No documents';
    badge.className = 'status-badge bg-yellow-100 text-yellow-700';
    msg.style.display = 'block';
    msg.innerHTML = '<p class="text-sm text-yellow-800"><strong>⚠️ No documents indexed</strong><br>Run <code class="px-2 py-0.5 bg-yellow-200 rounded text-xs">python scripts/manual_sync.py</code> to sync from Drive, or <code class="px-2 py-0.5 bg-yellow-200 rounded text-xs">python scripts/diagnose.py</code> to check what\\'s wrong.</p>';
  }
}

function addMsg(role,html){
  const w=document.getElementById('welcome');
  if(w)w.remove();
  const el=document.createElement('div');
  el.className='max-w-4xl mx-auto mb-4 msg-enter';
  if(role==='user'){
    el.innerHTML='<div class="flex justify-end"><div class="bg-blue-600 text-white px-4 py-3 rounded-2xl rounded-br-md max-w-xl text-sm shadow-sm">'+esc(html)+'</div></div>';
  }else{
    el.innerHTML='<div class="flex justify-start">'+html+'</div>';
  }
  document.getElementById('chat').appendChild(el);
  document.getElementById('chat').scrollTop=document.getElementById('chat').scrollHeight;
  return el;
}

function showDots(){
  return addMsg('bot','<div class="bg-white border border-gray-200 px-5 py-4 rounded-2xl rounded-bl-md shadow-sm inline-block"><div class="flex gap-1.5"><div class="dot w-2.5 h-2.5 bg-gray-400 rounded-full"></div><div class="dot w-2.5 h-2.5 bg-gray-400 rounded-full"></div><div class="dot w-2.5 h-2.5 bg-gray-400 rounded-full"></div></div></div>');
}

function fmt(t){
  let h=esc(t);
  h=h.replace(/\\*\\*(.+?)\\*\\*/g,'<strong>$1</strong>');
  h=h.replace(/\\*(.+?)\\*/g,'<em>$1</em>');
  h=h.replace(/\\n\\n/g,'</p><p>');
  h=h.replace(/\\n/g,'<br>');
  return '<div class="answer-text"><p>'+h+'</p></div>';
}

function buildResp(answerText,sources,empty){
  const bubbleClass = empty
    ? 'bg-amber-50 border border-amber-200 px-5 py-4 rounded-2xl rounded-bl-md shadow-sm max-w-3xl'
    : 'bg-white border border-gray-200 px-5 py-4 rounded-2xl rounded-bl-md shadow-sm max-w-3xl';
  let sourcesHtml='';
  if(sources && sources.length){
    sourcesHtml='<div class="mt-4 pt-4 border-t border-gray-100"><p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">'+sources.length+' Source'+(sources.length>1?'s':'')+'</p><div class="grid grid-cols-1 md:grid-cols-2 gap-3">';
    for(const s of sources){
      sourcesHtml+='<div class="source-card"><p class="font-semibold text-gray-800 text-sm mb-1 truncate">'+esc(s.title||'Document')+'</p>';
      if(s.uri){
        sourcesHtml+='<a href="'+esc(s.uri)+'" target="_blank" class="text-xs text-blue-600 hover:text-blue-700 underline">View →</a>';
      }
      sourcesHtml+='</div>';
    }
    sourcesHtml+='</div></div>';
  }
  return '<div class="'+bubbleClass+'">'+fmt(answerText)+sourcesHtml+'</div>';
}

function ask(q){document.getElementById('qi').value=q;sendQ();}

async function sendQ(){
  const inp=document.getElementById('qi');
  const q=inp.value.trim();
  if(!q)return;
  inp.value='';

  addMsg('user',q);
  const dots=showDots();

  try{
    const r=await fetch('/api/query',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({query:q})
    });
    const data=await r.json();
    dots.remove();

    if(data.error){
      addMsg('bot','<div class="bg-red-50 border border-red-200 px-5 py-4 rounded-2xl text-sm text-red-700 max-w-3xl">'+esc(data.error)+'</div>');
      return;
    }

    addMsg('bot',buildResp(data.text||'No answer found.',data.sources,!!data.empty));
  }catch(err){
    dots.remove();
    addMsg('bot','<div class="bg-red-50 border border-red-200 px-5 py-4 rounded-2xl text-sm text-red-700 max-w-3xl">'+esc(err.message)+'</div>');
  }
}

checkDataStatus();
setInterval(checkDataStatus, 30000);
</script>
</body>
</html>
'''


@app.route("/")
def index():
    return render_template_string(
        HTML_TEMPLATE,
        company=COMPANY_NAME.replace("-", " ").title(),
        company_name=COMPANY_NAME,
        region=GCP_REGION,
    )


@app.route("/api/status")
def api_status():
    if not BOOTSTRAP_ENV:
        return jsonify({
            "error": "No .env file found",
            "hint": "cd into your workspace before running, "
                    "or set VERTEX_ENV_FILE to the full path.",
            "documents": 0,
        })
    if not (PROJECT_ID and DATA_STORE_ID):
        return jsonify({
            "error": f"Missing required variables in {BOOTSTRAP_ENV}",
            "hint": "Ensure GCP_PROJECT_ID and VERTEX_DATA_STORE_ID are set.",
            "documents": 0,
        })

    try:
        from google.cloud import discoveryengine_v1 as discoveryengine
        client = discoveryengine.DocumentServiceClient(credentials=get_creds())
        parent = (
            f"projects/{PROJECT_ID}/locations/global"
            f"/collections/default_collection/dataStores/{DATA_STORE_ID}/branches/default_branch"
        )
        req = discoveryengine.ListDocumentsRequest(parent=parent, page_size=100)
        # The pager itself is the flat iterator over Documents across all
        # pages. Don't try to drill through `.pages` — in current SDK versions
        # the per-page ListDocumentsResponse is NOT directly iterable.
        docs = list(client.list_documents(request=req))
        return jsonify({"documents": len(docs)})
    except Exception as e:
        return jsonify({"error": str(e), "documents": 0})


@app.route("/api/query", methods=["POST"])
def api_query():
    data = flask_request.get_json(force=True)
    query = (data or {}).get("query", "").strip()
    if not query:
        return jsonify({"error": "query required"}), 400
    if not SERVING_CONFIG:
        return jsonify({"error": "Configuration not loaded - check .env file"}), 500

    try:
        from google.cloud import discoveryengine_v1 as discoveryengine
        client = discoveryengine.SearchServiceClient(credentials=get_creds())

        content_spec = discoveryengine.SearchRequest.ContentSearchSpec(
            snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                return_snippet=True,
            ),
            summary_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                summary_result_count=10,
                include_citations=True,
                ignore_adversarial_query=True,
                ignore_non_summary_seeking_query=False,
                model_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec.ModelSpec(
                    version="stable",
                ),
            ),
            extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                max_extractive_answer_count=1,
                max_extractive_segment_count=1,
            ),
        )

        req = discoveryengine.SearchRequest(
            serving_config=SERVING_CONFIG,
            query=query,
            page_size=10,
            content_search_spec=content_spec,
        )

        response = client.search(req)
        # IMPORTANT: materialize the pager BEFORE accessing response.summary.
        # In the discoveryengine SDK, summary is lazily populated as a side
        # effect of consuming the first page; reading it directly off the
        # pager yields an empty message.
        results = list(response)

        answer_text = ""
        if hasattr(response, "summary") and response.summary:
            answer_text = response.summary.summary_text or ""

        sources = []
        for result in results:
            doc = result.document
            title = _safe_struct_get(doc.struct_data, "title", "Document")
            drive_uri = _safe_struct_get(doc.struct_data, "uri", "")
            if title == "Document":
                title = _safe_struct_get(doc.derived_struct_data, "title", "Document")
            sources.append({"title": title, "uri": drive_uri})

        seen = set()
        unique_sources = []
        for s in sources:
            key = s.get("title")
            if key and key not in seen:
                seen.add(key)
                unique_sources.append(s)

        empty = is_empty_answer(answer_text) or (not unique_sources and not answer_text)
        if empty:
            answer_text = friendly_empty_message(query)

        return jsonify({
            "text": answer_text or friendly_empty_message(query),
            "sources": unique_sources[:5],
            "empty": empty,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import webbrowser
    from threading import Timer

    port = int(os.environ.get("PORT", 5000))
    url = f"http://localhost:{port}"

    print(f"\n  🚀 Web UI: {url}\n")
    Timer(1.5, lambda: webbrowser.open(url)).start()

    app.run(host="0.0.0.0", port=port, debug=False)

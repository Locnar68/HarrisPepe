"""Simple Flask web UI for Vertex AI Search - reads from Phase3 .env"""
import os
import sys
from pathlib import Path
from datetime import timedelta
from flask import Flask, jsonify, render_template_string, request
from dotenv import load_dotenv

# Load env from Phase3_Bootstrap
REPO_ROOT = Path(__file__).parent.parent
BOOTSTRAP_ENV = REPO_ROOT / "Phase3_Bootstrap" / "secrets" / ".env"

print(f"Looking for .env at: {BOOTSTRAP_ENV}")
if BOOTSTRAP_ENV.exists():
    print(f"✓ Found .env file, loading...")
    load_dotenv(BOOTSTRAP_ENV)
else:
    print(f"⚠ .env not found at {BOOTSTRAP_ENV}")
    print(f"Trying alternative path...")
    # Try from current directory
    alt_env = Path.cwd() / ".." / "Phase3_Bootstrap" / "secrets" / ".env"
    if alt_env.exists():
        print(f"✓ Found .env at {alt_env}")
        load_dotenv(alt_env)
        BOOTSTRAP_ENV = alt_env

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Read config from environment
COMPANY_NAME = os.getenv("COMPANY_NAME", "Document Search")
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
DATA_STORE_ID = os.getenv("VERTEX_DATA_STORE_ID")
ENGINE_ID = os.getenv("VERTEX_ENGINE_ID")
SERVING_CONFIG = os.getenv("VERTEX_SERVING_CONFIG")
GCS_RAW_BUCKET = os.getenv("GCS_BUCKET_RAW")
GCP_REGION = os.getenv("GCP_REGION", "us-east1")

print(f"\nConfiguration loaded:")
print(f"  Company: {COMPANY_NAME}")
print(f"  Project: {PROJECT_ID}")
print(f"  Region: {GCP_REGION}")
print(f"  Data Store: {DATA_STORE_ID}")
print(f"  Engine: {ENGINE_ID}")
print()

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
        <p class="text-gray-500 text-sm mb-6 text-center max-w-md">Type a question below to search across all your files using AI</p>
        <div class="flex flex-wrap justify-center gap-2 max-w-2xl">
          <button onclick="ask('What documents do I have?')" class="px-4 py-2 bg-white border-2 border-gray-200 rounded-xl text-sm text-gray-700 hover:border-blue-400 hover:bg-blue-50 transition-all">
            📄 What documents do I have?
          </button>
          <button onclick="ask('Show me recent files')" class="px-4 py-2 bg-white border-2 border-gray-200 rounded-xl text-sm text-gray-700 hover:border-blue-400 hover:bg-blue-50 transition-all">
            🕒 Show me recent files
          </button>
          <button onclick="ask('Search for contracts')" class="px-4 py-2 bg-white border-2 border-gray-200 rounded-xl text-sm text-gray-700 hover:border-blue-400 hover:bg-blue-50 transition-all">
            🔍 Search for contracts
          </button>
        </div>
        <div id="data-status-msg" class="mt-8 p-4 bg-blue-50 border border-blue-200 rounded-xl max-w-lg" style="display:none;">
          <p class="text-sm text-blue-800"><strong>💡 Getting Started:</strong> Your search index is ready! Make sure you've run the initial sync to import your documents.</p>
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
const PROJECT_ID = "{{ project_id }}";
const DATA_STORE_ID = "{{ data_store_id }}";
const SERVING_CONFIG = "{{ serving_config }}";
const COMPANY_NAME = "{{ company_name }}";
const REGION = "{{ region }}";

let checkCount = 0;

function esc(t){const d=document.createElement('div');d.textContent=t;return d.innerHTML;}

async function checkDataStatus(){
  checkCount++;
  try{
    const resp = await fetch('/api/status');
    const data = await resp.json();
    const badge = document.getElementById('status-text');
    const msg = document.getElementById('data-status-msg');
    
    if(data.documents > 0){
      badge.textContent = `✓ ${data.documents} docs`;
      badge.className = 'status-badge bg-green-100 text-green-700';
      msg.style.display = 'none';
    }else{
      // Show indexing message for first 10 checks (5 minutes)
      if(checkCount <= 10){
        badge.innerHTML = '<span class="spinner">⏳</span> Indexing...';
        badge.className = 'status-badge bg-blue-100 text-blue-700';
        msg.style.display = 'block';
        msg.innerHTML = '<p class="text-sm text-blue-800"><strong>⏳ Documents are being indexed...</strong><br>Drive sync is processing your files. This usually takes 2-5 minutes.<br><br>This page auto-refreshes every 30 seconds. Check back soon!</p>';
      }else{
        badge.textContent = '⚠ No documents';
        badge.className = 'status-badge bg-yellow-100 text-yellow-700';
        msg.style.display = 'block';
        
        const syncJob = data.sync_job || (COMPANY_NAME + '-gdrive-sync').substring(0, 63);
        const region = data.region || REGION || 'us-east1';
        
        msg.innerHTML = '<p class="text-sm text-yellow-800"><strong>⚠️ Still No Documents</strong><br>The sync may have failed. Try running manually:<br><code class="px-2 py-0.5 bg-yellow-200 rounded text-xs">gcloud run jobs execute ' + syncJob + ' --region ' + region + '</code></p>';
      }
    }
  }catch(e){
    document.getElementById('status-text').textContent = 'Offline';
    document.getElementById('status-text').className = 'status-badge bg-red-100 text-red-700';
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

function buildResp(answerText,sources){
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
  return '<div class="bg-white border border-gray-200 px-5 py-4 rounded-2xl rounded-bl-md shadow-sm max-w-3xl">'+fmt(answerText)+sourcesHtml+'</div>';
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
    
    addMsg('bot',buildResp(data.text||'No answer found.',data.sources));
  }catch(err){
    dots.remove();
    addMsg('bot','<div class="bg-red-50 border border-red-200 px-5 py-4 rounded-2xl text-sm text-red-700 max-w-3xl">'+esc(err.message)+'</div>');
  }
}

// Init
checkDataStatus();
setInterval(checkDataStatus, 30000); // Check every 30s
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
        project_id=PROJECT_ID or "",
        data_store_id=DATA_STORE_ID or "",
        serving_config=SERVING_CONFIG or "",
        region=GCP_REGION
    )

@app.route("/api/status")
def api_status():
    """Check how many documents are in the data store"""
    
    # Get sync job name from company name
    sync_job = f"{COMPANY_NAME}-gdrive-sync"[:63] if COMPANY_NAME else "gdrive-sync"
    region = GCP_REGION or "us-east1"
    
    if not PROJECT_ID or not DATA_STORE_ID:
        return jsonify({
            "error": "Configuration not loaded - check .env file",
            "documents": 0,
            "sync_job": sync_job,
            "region": region
        })
    
    try:
        from google.cloud import discoveryengine_v1 as discoveryengine
        
        client = discoveryengine.DocumentServiceClient()
        parent = f"projects/{PROJECT_ID}/locations/global/collections/default_collection/dataStores/{DATA_STORE_ID}/branches/default_branch"
        
        # List documents to get count
        request = discoveryengine.ListDocumentsRequest(parent=parent, page_size=10)
        page_result = client.list_documents(request=request)
        
        # Count documents
        doc_count = sum(1 for _ in page_result)
        
        return jsonify({
            "documents": doc_count,
            "sync_job": sync_job,
            "region": region
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "documents": 0,
            "sync_job": sync_job,
            "region": region
        })

@app.route("/api/query", methods=["POST"])
def api_query():
    """Search and answer using Vertex AI Search"""
    data = request.get_json(force=True)
    query = data.get("query", "").strip()
    
    if not query:
        return jsonify({"error": "query required"}), 400
    
    if not SERVING_CONFIG:
        return jsonify({"error": "Configuration not loaded - check .env file"}), 500
    
    try:
        from google.cloud import discoveryengine_v1 as discoveryengine
        
        # Search
        client = discoveryengine.SearchServiceClient()
        request = discoveryengine.SearchRequest(
            serving_config=SERVING_CONFIG,
            query=query,
            page_size=5,
            content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                summary_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                    summary_result_count=5,
                    include_citations=True
                )
            )
        )
        
        response = client.search(request)
        
        # Extract answer
        answer_text = "No answer found."
        if hasattr(response, "summary") and response.summary:
            answer_text = response.summary.summary_text
        
        # Extract sources
        sources = []
        for result in response.results:
            doc = result.document
            doc_data = doc.derived_struct_data
            
            title = "Document"
            if hasattr(doc_data, "get") and callable(doc_data.get):
                title = doc_data.get("title", title)
            
            sources.append({
                "title": title,
                "uri": doc.name if hasattr(doc, "name") else ""
            })
        
        return jsonify({
            "text": answer_text,
            "sources": sources[:5]
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

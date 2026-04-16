"""Web UI — Flask app with Gmail compose links instead of mailto."""
from __future__ import annotations

import os
import sys
import urllib.parse
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, jsonify, render_template, request as req
from core import load_config, storage_client
from vertex.search import search as do_search
from vertex.answer import answer as do_answer

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
_cfg = None

def cfg():
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


@app.route("/")
def index():
    c = cfg()
    props = c.properties or []
    doc_types = sorted({v for v in c.category_folders.values()})
    doc_types += [t for t in ["email", "document"] if t not in doc_types]
    return render_template("index.html",
        company=c.raw.get("data_store", {}).get("display_name", "SMB Search"),
        properties=props, doc_types=doc_types)


@app.route("/api/query", methods=["POST"])
def api_query():
    data = req.get_json(force=True)
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "query required"}), 400

    prop = data.get("property") or None
    dtype = data.get("doc_type") or None
    mode = data.get("mode", "answer")
    session = data.get("session") or None
    c = cfg()

    try:
        if mode == "search":
            hits = do_search(c, query, property_=prop, doc_type=dtype, page_size=10)
            return jsonify({"mode": "search", "results": [
                {"rank": h.rank, "property": h.property, "doc_type": h.doc_type,
                 "filename": h.filename, "uri": h.uri} for h in hits
            ]})

        a = do_answer(c, query, property_=prop, doc_type=dtype, session=session)
        sources = [{"reference_id": s.get("reference_id",""), "title": s.get("title",""),
                     "property": s.get("property",""), "category": s.get("category",""),
                     "doc_type": s.get("doc_type",""), "uri": s.get("uri","")} for s in a.sources]

        no_answer = (not a.text or "could not be generated" in a.text.lower())
        if no_answer or not sources:
            hits = do_search(c, query, property_=prop, doc_type=dtype, page_size=10)
            search_sources = [{"reference_id": str(h.rank), "title": h.filename,
                               "property": h.property, "category": h.doc_type,
                               "uri": h.uri} for h in hits]
            if not sources:
                sources = search_sources
            elif search_sources:
                known = {s["title"] for s in sources}
                for ss in search_sources:
                    if ss["title"] not in known:
                        sources.append(ss)
            text = a.text if not no_answer else (
                "I found relevant documents but couldn't generate a summary. "
                "The matching files are listed below.")
        else:
            text = a.text

        return jsonify({"mode": "answer", "text": text, "sources": sources,
                        "citations": a.citations, "session": a.session})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download")
def api_download():
    uri = req.args.get("uri", "")
    if not uri.startswith("gs://"):
        return jsonify({"error": "invalid uri"}), 400
    c = cfg()
    parts = uri.replace("gs://", "").split("/", 1)
    if len(parts) != 2:
        return jsonify({"error": "malformed uri"}), 400
    try:
        gcs = storage_client(c)
        url = gcs.bucket(parts[0]).blob(parts[1]).generate_signed_url(
            version="v4", expiration=timedelta(hours=1), method="GET")
        return jsonify({"url": url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/email_docs", methods=["POST"])
def api_email_docs():
    """Generate download links for all docs and return a Gmail compose URL."""
    data = req.get_json(force=True)
    to = data.get("to", "").strip()
    uris = data.get("uris", [])       # list of {uri, title}

    if not to:
        return jsonify({"error": "email address required"}), 400
    if not uris:
        return jsonify({"error": "no documents to email"}), 400

    c = cfg()
    gcs = storage_client(c)
    lines = []

    for item in uris:
        uri = item.get("uri", "")
        title = item.get("title", "Document")
        if not uri.startswith("gs://"):
            continue
        parts = uri.replace("gs://", "").split("/", 1)
        if len(parts) != 2:
            continue
        try:
            url = gcs.bucket(parts[0]).blob(parts[1]).generate_signed_url(
                version="v4", expiration=timedelta(hours=24), method="GET")
            lines.append(f"{title}\n{url}")
        except Exception:
            lines.append(f"{title}\n(link generation failed)")

    if not lines:
        return jsonify({"error": "could not generate any download links"}), 500

    subject = f"{len(lines)} document{'s' if len(lines)>1 else ''} from AI Search"
    body = "Here are the documents from your search:\n\n" + "\n\n".join(lines) + "\n\nLinks expire in 24 hours.\n"

    # Gmail compose URL — opens a new compose window in the browser.
    gmail_url = (
        "https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={urllib.parse.quote(to)}"
        f"&su={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(body)}"
    )

    return jsonify({"gmail_url": gmail_url, "doc_count": len(lines)})


def create_app():
    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Web UI: http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=True)

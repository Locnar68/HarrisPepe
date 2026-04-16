"""Web UI — Flask app serving the chat interface + API endpoints."""
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
    return render_template(
        "index.html",
        company=c.raw.get("data_store", {}).get("display_name", "SMB Search"),
        properties=props,
        doc_types=doc_types,
    )


@app.route("/api/query", methods=["POST"])
def api_query():
    data = req.get_json(force=True)
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "query required"}), 400

    prop = data.get("property") or None
    dtype = data.get("doc_type") or None
    mode = data.get("mode", "answer")
    session = data.get("session") or None  # session name from prior turn
    c = cfg()

    try:
        if mode == "search":
            hits = do_search(c, query, property_=prop, doc_type=dtype, page_size=10)
            results = [{
                "rank": h.rank, "property": h.property, "doc_type": h.doc_type,
                "filename": h.filename, "uri": h.uri,
            } for h in hits]
            return jsonify({"mode": "search", "results": results})
        else:
            a = do_answer(c, query, property_=prop, doc_type=dtype, session=session)
            sources = [{
                "reference_id": s.get("reference_id", ""),
                "title": s.get("title", ""),
                "property": s.get("property", ""),
                "category": s.get("category", ""),
                "uri": s.get("uri", ""),
            } for s in a.sources]
            return jsonify({
                "mode": "answer",
                "text": a.text,
                "sources": sources,
                "citations": a.citations,
                "session": a.session,    # pass back to frontend for follow-ups
            })
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
        blob = gcs.bucket(parts[0]).blob(parts[1])
        url = blob.generate_signed_url(version="v4", expiration=timedelta(hours=1), method="GET")
        return jsonify({"url": url, "expires_in": "1 hour"})
    except Exception as e:
        return jsonify({"error": f"signed URL failed: {e}"}), 500


@app.route("/api/email_link")
def api_email_link():
    uri = req.args.get("uri", "")
    filename = req.args.get("filename", "document")
    prop = req.args.get("property", "")
    if not uri.startswith("gs://"):
        return jsonify({"error": "invalid uri"}), 400
    c = cfg()
    parts = uri.replace("gs://", "").split("/", 1)
    if len(parts) != 2:
        return jsonify({"error": "malformed uri"}), 400
    try:
        gcs = storage_client(c)
        blob = gcs.bucket(parts[0]).blob(parts[1])
        download_url = blob.generate_signed_url(version="v4", expiration=timedelta(hours=24), method="GET")
    except Exception as e:
        return jsonify({"error": f"signed URL failed: {e}"}), 500

    subject = urllib.parse.quote(f"Document: {filename} — {prop}")
    body = urllib.parse.quote(
        f"Here's the document you requested:\n\n"
        f"File: {filename}\nProperty: {prop}\n\n"
        f"Download (valid 24h):\n{download_url}\n"
    )
    return jsonify({"mailto": f"mailto:?subject={subject}&body={body}", "download_url": download_url})


def create_app():
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Web UI: http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=True)

"""Web UI — Flask app with search, email, and template drafting."""
from __future__ import annotations

import os
import re
import sys
import smtplib
import urllib.parse
import uuid
from datetime import timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, jsonify, render_template, request as req, send_file
from core import load_config, storage_client
from core.config import REPO_ROOT as ROOT
from vertex.search import search as do_search
from vertex.answer import answer as do_answer

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
_cfg = None
TEMPLATE_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def cfg():
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


def _signed_url(c, uri, hours=24):
    parts = uri.replace("gs://", "").split("/", 1)
    if len(parts) != 2:
        return None
    gcs = storage_client(c)
    return gcs.bucket(parts[0]).blob(parts[1]).generate_signed_url(
        version="v4", expiration=timedelta(hours=hours), method="GET")


def _send_smtp(c, to, subject, body, attachment_path=None):
    email_cfg = c.raw.get("email", {}) or {}
    sender = email_cfg.get("sender", "")
    password = email_cfg.get("app_password", "")
    host = email_cfg.get("smtp_host", "smtp.gmail.com")
    port = int(email_cfg.get("smtp_port", 587))
    if not sender or not password:
        return "Email not configured."

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if attachment_path and Path(attachment_path).exists():
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={Path(attachment_path).name}")
        msg.attach(part)

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        return None
    except Exception as e:
        return str(e)


# ── Pages ──

@app.route("/")
def index():
    c = cfg()
    props = c.properties or []
    doc_types = sorted({v for v in c.category_folders.values()})
    doc_types += [t for t in ["email", "document"] if t not in doc_types]
    email_cfg = c.raw.get("email", {}) or {}
    email_ok = bool(email_cfg.get("sender") and email_cfg.get("app_password"))
    return render_template("index.html",
        company=c.raw.get("data_store", {}).get("display_name", "SMB Search"),
        properties=props, doc_types=doc_types, email_enabled=email_ok)


# ── Search/Answer API ──

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
                 "filename": h.filename, "uri": h.uri} for h in hits]})

        a = do_answer(c, query, property_=prop, doc_type=dtype, session=session)
        sources = [{"reference_id": s.get("reference_id",""), "title": s.get("title",""),
                     "property": s.get("property",""), "category": s.get("category",""),
                     "doc_type": s.get("doc_type",""), "uri": s.get("uri","")} for s in a.sources]
        no_answer = (not a.text or "could not be generated" in a.text.lower())
        if no_answer or not sources:
            hits = do_search(c, query, property_=prop, doc_type=dtype, page_size=10)
            fallback = [{"reference_id": str(h.rank), "title": h.filename,
                         "property": h.property, "category": h.doc_type, "uri": h.uri} for h in hits]
            if not sources: sources = fallback
            text = a.text if not no_answer else "I found relevant documents but couldn't generate a summary."
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
    try:
        return jsonify({"url": _signed_url(cfg(), uri, hours=1)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/email", methods=["POST"])
def api_email():
    data = req.get_json(force=True)
    to = data.get("to", "").strip()
    docs = data.get("docs", [])
    if not to: return jsonify({"error": "Email required"}), 400
    if not docs: return jsonify({"error": "No documents"}), 400
    c = cfg()
    lines = []
    for d in docs:
        uri = d.get("uri", "")
        title = d.get("title", "Document")
        if not uri.startswith("gs://"): continue
        try:
            url = _signed_url(c, uri, hours=24)
            lines.append(f"• {title}\n  {url}")
        except: lines.append(f"• {title}\n  (failed)")
    if not lines: return jsonify({"error": "No links generated"}), 500
    subject = f"{len(lines)} document{'s' if len(lines)>1 else ''} from AI Search"
    body = "Documents:\n\n" + "\n\n".join(lines) + "\n\nLinks expire in 24h.\n"
    err = _send_smtp(c, to, subject, body)
    if err: return jsonify({"error": err}), 500
    return jsonify({"sent": True, "to": to, "doc_count": len(lines)})


# ── Templates API ──

@app.route("/api/templates")
def api_templates():
    """List available templates."""
    templates = []
    for f in sorted(TEMPLATE_DIR.glob("*.md")):
        if f.name == "queries.yaml":
            continue
        text = f.read_text(encoding="utf-8")
        phs = sorted(set(re.findall(r"\{\{(.+?)\}\}", text)))
        # Get first heading as display name.
        title = f.stem.replace("-", " ").title()
        for line in text.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break
        templates.append({"id": f.stem, "title": title, "fields": len(phs), "file": f.name})
    return jsonify({"templates": templates})


@app.route("/api/draft", methods=["POST"])
def api_draft():
    """Fill a template and generate a PDF. Returns a download path."""
    data = req.get_json(force=True)
    template_id = data.get("template", "").strip()
    prop = data.get("property") or None
    to_email = data.get("email", "").strip()

    if not template_id:
        return jsonify({"error": "template required"}), 400

    template_path = TEMPLATE_DIR / f"{template_id}.md"
    if not template_path.exists():
        return jsonify({"error": f"Template not found: {template_id}"}), 404

    c = cfg()
    if not prop:
        prop = c.default_property

    # Load engine.
    from drafting.engine import DraftingEngine, load_query_map
    from drafting.writer import write_pdf

    query_map = load_query_map(TEMPLATE_DIR / "queries.yaml")
    template_text = template_path.read_text(encoding="utf-8")
    total = len(set(re.findall(r"\{\{(.+?)\}\}", template_text)))

    engine = DraftingEngine(c, property_=prop, delay=4.0, log=lambda x: None)

    try:
        filled, results = engine.fill(template_text, query_map)
    except Exception as e:
        return jsonify({"error": f"Fill failed: {e}"}), 500

    # Generate PDF.
    file_id = uuid.uuid4().hex[:8]
    pdf_name = f"{template_id}-{file_id}.pdf"
    pdf_path = OUTPUT_DIR / pdf_name

    try:
        write_pdf(filled, pdf_path, title=template_id.replace("-", " ").title())
    except Exception as e:
        return jsonify({"error": f"PDF generation failed: {e}"}), 500

    # Build results summary.
    ok = sum(1 for r in results if r.success)
    summary = [{"field": r.placeholder, "ok": r.success, "answer": r.answer[:100]} for r in results]

    resp = {
        "pdf": pdf_name,
        "download_url": f"/api/draft/download/{pdf_name}",
        "resolved": ok,
        "total": len(results),
        "results": summary,
    }

    # Optionally email the PDF.
    if to_email:
        subject = f"{template_id.replace('-', ' ').title()} — {prop or 'Report'}"
        body = f"Attached: {template_id.replace('-', ' ').title()}\nProperty: {prop or 'N/A'}\nResolved: {ok}/{len(results)} fields\n"
        err = _send_smtp(c, to_email, subject, body, attachment_path=str(pdf_path))
        if err:
            resp["email_error"] = err
        else:
            resp["emailed_to"] = to_email

    return jsonify(resp)


@app.route("/api/draft/download/<filename>")
def api_draft_download(filename):
    """Serve a generated PDF for download."""
    path = OUTPUT_DIR / filename
    if not path.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(str(path), as_attachment=True, download_name=filename)


def create_app():
    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Web UI: http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=True)

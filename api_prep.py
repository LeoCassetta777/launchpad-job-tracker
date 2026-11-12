"""Phase 4 endpoints: documents, fit checks, interview prep, question bank, rejection log.

Documents
    GET    /api/documents                     list (text shortened)
    POST   /api/documents                     upload a PDF/DOCX (form) or paste text (JSON)
    GET/PATCH/DELETE /api/documents/<id>
    GET    /documents/<id>/file               download the original file
Sent materials (which versions went to which opportunity)
    POST   /api/opportunities/<id>/documents  {document_id, sent_on, note}
    DELETE /api/sent-documents/<id>
Fit check
    GET    /api/opportunities/<id>/fit        newest result + history
    POST   /api/opportunities/<id>/fit        {document_id, override_cap}   (costs money: Sonnet)
Interview prep and question bank
    GET    /api/opportunities/<id>/prep       everything for the prep page
    POST   /api/opportunities/<id>/questions/generate   {override_cap}     (costs money: Sonnet)
    GET    /api/questions?q=&tag=&kind=       the bank
    POST   /api/questions, PATCH/DELETE /api/questions/<id>
Rejection log
    GET    /api/rejections                    entries + patterns
    PATCH  /api/rejections/<id>               {lesson}
    POST   /api/opportunities/<id>/lesson     {lesson}  (right after closing a card)
Skills profile
    GET/POST /api/profile                     {text}
"""
import json
from collections import Counter

from flask import Blueprint, abort, jsonify, request, send_file

import ai
import ai_budget
import ai_tools
import config
import constants as C
import documents
import settings_store
import validation as V
from db import get_db, log_activity, rows_to_dicts

api_prep = Blueprint("api_prep", __name__)


@api_prep.before_request
def require_json_or_marked_upload():
    """Same cross-site protection as the other APIs. Uploads can't be JSON, so they must
    carry a custom header instead (other websites can't add custom headers either)."""
    if request.method in ("POST", "PATCH", "DELETE"):
        if not (request.is_json or request.headers.get("X-Launchpad") == "1"):
            abort(415, "Send JSON (Content-Type: application/json).")


@api_prep.errorhandler(ai_budget.BudgetError)
def handle_budget(e):
    return jsonify(error=str(e), cap_reached=True), 402


@api_prep.errorhandler(ValueError)        # validation problems and unreadable uploads
def handle_value_error(e):
    return jsonify(error=str(e)), 400


@api_prep.errorhandler(ai.AIError)
def handle_ai_error(e):
    return jsonify(error=str(e)), 400


@api_prep.errorhandler(400)
@api_prep.errorhandler(404)
@api_prep.errorhandler(413)
@api_prep.errorhandler(415)
def handle_http_error(e):
    return jsonify(error=e.description), e.code


def _one(table, row_id, what):
    row = get_db().execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        abort(404, f"{what} not found.")
    return row


def _opp_name(o):
    return f"{o['company']} · {o['title']}" if o["title"] else o["company"]


# ---------------------------------------------------------------- documents

def _doc_summary(d):
    d = dict(d)
    d["text_length"] = len(d["text"])
    d["preview"] = d["text"][:240]
    d["has_file"] = bool(d["stored_name"])
    del d["text"], d["stored_name"]
    return d


@api_prep.get("/api/documents")
def list_documents():
    conn = get_db()
    docs = [_doc_summary(d) for d in conn.execute("SELECT * FROM documents ORDER BY kind, updated_at DESC").fetchall()]
    used = {r["document_id"]: r["n"] for r in conn.execute(
        "SELECT document_id, COUNT(*) n FROM opportunity_documents GROUP BY document_id").fetchall()}
    companies = {r["id"]: r["company"] for r in conn.execute("SELECT id, company FROM opportunities").fetchall()}
    for d in docs:
        d["times_sent"] = used.get(d["id"], 0)
        d["tailored_for"] = companies.get(d["opportunity_id"]) if d["opportunity_id"] else None
        d["tailor_notes"] = json.loads(d["tailor_notes"]) if d["tailor_notes"] else None
    return jsonify(docs)


@api_prep.get("/api/documents/<int:doc_id>")
def get_document(doc_id):
    d = dict(_one("documents", doc_id, "Document"))
    d["has_file"] = bool(d.pop("stored_name"))
    d["sent_to"] = rows_to_dicts(get_db().execute(
        "SELECT sd.id, sd.sent_on, o.id AS opportunity_id, o.company, o.title FROM opportunity_documents sd "
        "JOIN opportunities o ON o.id = sd.opportunity_id WHERE sd.document_id = ? ORDER BY sd.sent_on DESC",
        (doc_id,)).fetchall())
    return jsonify(d)


@api_prep.post("/api/documents")
def create_document():
    """Either a multipart upload (file + label + kind) or JSON with pasted text."""
    conn = get_db()
    now = config.now_str()
    if request.files.get("file"):
        form = {k: request.form[k] for k in ("label", "kind", "notes") if request.form.get(k)}
        meta = V.clean(form, V.DOCUMENT_FIELDS)
        original, stored, size, text = documents.save_upload(request.files["file"])
        if not text.strip():
            meta_note = "No text could be read (a scanned image?). Paste the text into the document so fit checks can use it."
        else:
            meta_note = ""
        cur = conn.execute(
            "INSERT INTO documents (kind, label, filename, stored_name, size_bytes, text, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (meta.get("kind", "resume"), meta["label"], original, stored, size, text, meta.get("notes", ""), now, now))
    else:
        data = V.clean(request.get_json(silent=True) or {}, V.DOCUMENT_FIELDS)
        if not data.get("text", "").strip():
            abort(400, "Choose a file to upload, or paste the document's text.")
        meta_note = ""
        cur = conn.execute(
            "INSERT INTO documents (kind, label, text, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (data.get("kind", "resume"), data["label"], data["text"], data.get("notes", ""), now, now))
    conn.commit()
    doc = _doc_summary(_one("documents", cur.lastrowid, "Document"))
    return jsonify({**doc, "warning": meta_note}), 201


@api_prep.patch("/api/documents/<int:doc_id>")
def update_document(doc_id):
    _one("documents", doc_id, "Document")
    data = V.clean(request.get_json(silent=True) or {}, V.DOCUMENT_FIELDS, partial=True)
    if data:
        conn = get_db()
        sets = ", ".join(f"{k} = ?" for k in data)
        conn.execute(f"UPDATE documents SET {sets}, updated_at = ? WHERE id = ?", [*data.values(), config.now_str(), doc_id])
        conn.commit()
    return jsonify(_doc_summary(_one("documents", doc_id, "Document")))


@api_prep.delete("/api/documents/<int:doc_id>")
def delete_document(doc_id):
    d = _one("documents", doc_id, "Document")
    conn = get_db()
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    documents.delete_file(d["stored_name"])
    return jsonify(ok=True)


@api_prep.get("/documents/<int:doc_id>/file")
def download_document(doc_id):
    d = _one("documents", doc_id, "Document")
    path = documents.path_of(d["stored_name"])
    if not path:
        abort(404, "This document has no file (its text was pasted in).")
    return send_file(path, as_attachment=True, download_name=d["filename"] or path.name)


# ---------------------------------------------------------------- tailored resumes

@api_prep.post("/api/opportunities/<int:opp_id>/tailor")
def tailor(opp_id):
    """Make a tailored copy of a resume for this opportunity (Sonnet, about $0.03).
    It's saved as a NEW document; your original is never changed."""
    conn = get_db()
    o = _one("opportunities", opp_id, "Opportunity")
    data = request.get_json(silent=True) or {}
    doc_id = V.ref_id(data.get("document_id"))
    if not doc_id:
        abort(400, "Pick the resume to tailor.")
    resume = _one("documents", doc_id, "Document")
    fit = conn.execute("SELECT * FROM fit_checks WHERE opportunity_id = ? ORDER BY id DESC LIMIT 1", (opp_id,)).fetchone()
    profile = settings_store.get_all(conn)["skills_profile"]
    result, text, cost, notes = ai_tools.tailor_resume(o, resume, profile, fit, override_cap=data.get("override_cap") is True)
    now = config.now_str()
    label = V.text(150)(f"{resume['label']} → {o['company']}")
    meta = {"changes": result["changes"], "not_claimed": result["not_claimed"], "notes": notes,
            "cost_usd": cost, "from_label": resume["label"]}
    cur = conn.execute(
        "INSERT INTO documents (kind, label, text, notes, source_document_id, opportunity_id, tailor_notes, created_at, updated_at) "
        "VALUES ('resume', ?, ?, ?, ?, ?, ?, ?, ?)",
        (label, text, f"Tailored for {_opp_name(o)}", doc_id, opp_id, json.dumps(meta), now, now))
    log_activity(conn, "opportunity", opp_id, "resume_tailored", f"Tailored {resume['label']} for {_opp_name(o)}",
                 {"document_id": cur.lastrowid})
    conn.commit()
    return jsonify(id=cur.lastrowid, label=label, text=text, cost=cost, **meta), 201


@api_prep.get("/documents/<int:doc_id>/docx")
def download_docx(doc_id):
    """A Word file built from the document's current text (so your edits are included)."""
    import resume_docx
    d = _one("documents", doc_id, "Document")
    # "Resume – Data v2 (demo) → Brightloom" becomes "Resume - Data v2 demo - Brightloom"
    safe = " ".join("".join(ch if ch.isalnum() or ch == " " else " - " if ch in "–→-" else " " for ch in d["label"]).split())
    safe = safe.replace("- -", "-").strip(" -") or "resume"
    return send_file(resume_docx.build_docx(d["text"]), as_attachment=True, download_name=f"{safe}.docx",
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@api_prep.get("/api/opportunities/<int:opp_id>/tailored")
def tailored_for(opp_id):
    rows = get_db().execute("SELECT id, label, tailor_notes, created_at FROM documents WHERE opportunity_id = ? "
                            "ORDER BY id DESC", (opp_id,)).fetchall()
    return jsonify([{**dict(r), "tailor_notes": json.loads(r["tailor_notes"] or "{}")} for r in rows])


# ---------------------------------------------------------------- sent materials

def _sent_for(opp_id):
    return rows_to_dicts(get_db().execute(
        "SELECT sd.id, sd.sent_on, sd.note, d.id AS document_id, d.label, d.kind FROM opportunity_documents sd "
        "JOIN documents d ON d.id = sd.document_id WHERE sd.opportunity_id = ? ORDER BY sd.sent_on DESC", (opp_id,)).fetchall())


@api_prep.post("/api/opportunities/<int:opp_id>/documents")
def record_sent(opp_id):
    o = _one("opportunities", opp_id, "Opportunity")
    data = request.get_json(silent=True) or {}
    doc_id = V.ref_id(data.get("document_id"))
    if not doc_id:
        abort(400, "Pick a document.")
    d = _one("documents", doc_id, "Document")
    sent_on = V.iso_date(data.get("sent_on")) or config.today_str()
    conn = get_db()
    conn.execute("INSERT INTO opportunity_documents (opportunity_id, document_id, sent_on, note, created_at) "
                 "VALUES (?, ?, ?, ?, ?)", (opp_id, doc_id, sent_on, V.text(300)(data.get("note")), config.now_str()))
    log_activity(conn, "opportunity", opp_id, "document_sent", f"Sent {d['label']} to {_opp_name(o)}",
                 {"document_id": doc_id, "sent_on": sent_on})
    conn.commit()
    return jsonify(_sent_for(opp_id)), 201


@api_prep.delete("/api/sent-documents/<int:row_id>")
def delete_sent(row_id):
    _one("opportunity_documents", row_id, "Record")
    conn = get_db()
    conn.execute("DELETE FROM opportunity_documents WHERE id = ?", (row_id,))
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- fit check

def _fit_view(row):
    if row is None:
        return None
    f = dict(row)
    f["result"] = json.loads(f["result"])
    return f


@api_prep.get("/api/opportunities/<int:opp_id>/fit")
def get_fit(opp_id):
    _one("opportunities", opp_id, "Opportunity")
    rows = get_db().execute("SELECT * FROM fit_checks WHERE opportunity_id = ? ORDER BY id DESC", (opp_id,)).fetchall()
    return jsonify(latest=_fit_view(rows[0]) if rows else None,
                   history=[{"id": r["id"], "score": r["score"], "created_at": r["created_at"],
                             "document_label": r["document_label"]} for r in rows])


@api_prep.post("/api/opportunities/<int:opp_id>/fit")
def run_fit(opp_id):
    conn = get_db()
    o = _one("opportunities", opp_id, "Opportunity")
    data = request.get_json(silent=True) or {}
    doc_id = V.ref_id(data.get("document_id"))
    resume = _one("documents", doc_id, "Document") if doc_id else None
    profile = settings_store.get_all(conn)["skills_profile"]
    result, cost, notes = ai_tools.fit_check(o, resume, profile, override_cap=data.get("override_cap") is True)
    result["notes"] = notes
    cur = conn.execute(
        "INSERT INTO fit_checks (opportunity_id, document_id, document_label, score, score_reason, result, model, "
        "cost_usd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (opp_id, doc_id, resume["label"] if resume else "(skills profile only)", result["score"],
         result["score_reason"], json.dumps(result), config.SMART_MODEL, cost, config.now_str()))
    log_activity(conn, "opportunity", opp_id, "fit_check",
                 f"Fit check for {_opp_name(o)}: {result['score']}/5 ({result['score_reason']})",
                 {"score": result["score"], "document_id": doc_id})
    conn.commit()
    return jsonify(_fit_view(_one("fit_checks", cur.lastrowid, "Fit check")))


# ---------------------------------------------------------------- questions

def _norm(text):
    return " ".join("".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).split())


Q_SQL = ("SELECT q.*, o.company AS opp_company, o.title AS opp_title FROM questions q "
         "LEFT JOIN opportunities o ON o.id = q.opportunity_id")


@api_prep.get("/api/questions")
def list_questions():
    """The bank. ?q= searches question + answer; ?tag= and ?kind= filter."""
    where, params = [], []
    if request.args.get("q"):
        where.append("(q.text LIKE ? OR q.answer LIKE ?)")
        params += [f"%{request.args['q']}%"] * 2
    if request.args.get("tag"):
        where.append("(',' || q.tags || ',') LIKE ?")
        params.append(f"%,{request.args['tag']},%")
    if request.args.get("kind"):
        where.append("q.kind = ?")
        params.append(request.args["kind"])
    sql = Q_SQL + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY q.best DESC, q.updated_at DESC"
    return jsonify(rows_to_dicts(get_db().execute(sql, params).fetchall()))


def _unique_best(conn, qid, text):
    """Only one 'best answer' per question wording."""
    key = _norm(text)
    for other in conn.execute("SELECT id, text FROM questions WHERE best = 1 AND id != ?", (qid,)).fetchall():
        if _norm(other["text"]) == key:
            conn.execute("UPDATE questions SET best = 0 WHERE id = ?", (other["id"],))


@api_prep.post("/api/questions")
def create_question():
    conn = get_db()
    data = V.clean(request.get_json(silent=True) or {}, V.QUESTION_FIELDS)
    if data.get("opportunity_id"):
        _one("opportunities", data["opportunity_id"], "Opportunity")
    note = ""
    # Reuse: if you've already saved a best answer to this exact question, start from it.
    if data.get("kind", "asked") != "to_ask" and not data.get("answer"):
        key = _norm(data["text"])
        for row in conn.execute("SELECT text, answer FROM questions WHERE best = 1 AND answer != ''").fetchall():
            if _norm(row["text"]) == key:
                data["answer"] = row["answer"]
                note = "Filled in your saved best answer. Edit it for this interview."
                break
    data["created_at"] = data["updated_at"] = config.now_str()
    cols = ", ".join(data)
    cur = conn.execute(f"INSERT INTO questions ({cols}) VALUES ({', '.join('?' for _ in data)})", list(data.values()))
    if data.get("best"):
        _unique_best(conn, cur.lastrowid, data["text"])
    if data.get("opportunity_id") and data.get("kind", "asked") == "asked":
        log_activity(conn, "opportunity", data["opportunity_id"], "question_logged",
                     f"Logged interview question: {data['text'][:80]}")
    conn.commit()
    return jsonify({**dict(conn.execute(Q_SQL + " WHERE q.id = ?", (cur.lastrowid,)).fetchone()), "note": note}), 201


@api_prep.patch("/api/questions/<int:qid>")
def update_question(qid):
    old = _one("questions", qid, "Question")
    data = V.clean(request.get_json(silent=True) or {}, V.QUESTION_FIELDS, partial=True)
    conn = get_db()
    if data:
        sets = ", ".join(f"{k} = ?" for k in data)
        conn.execute(f"UPDATE questions SET {sets}, updated_at = ? WHERE id = ?", [*data.values(), config.now_str(), qid])
        if data.get("best"):
            _unique_best(conn, qid, data.get("text", old["text"]))
        conn.commit()
    return jsonify(dict(conn.execute(Q_SQL + " WHERE q.id = ?", (qid,)).fetchone()))


@api_prep.delete("/api/questions/<int:qid>")
def delete_question(qid):
    _one("questions", qid, "Question")
    conn = get_db()
    conn.execute("DELETE FROM questions WHERE id = ?", (qid,))
    conn.commit()
    return jsonify(ok=True)


@api_prep.get("/api/opportunities/<int:opp_id>/prep")
def prep(opp_id):
    conn = get_db()
    o = dict(_one("opportunities", opp_id, "Opportunity"))
    o.pop("posting_text")
    questions = rows_to_dicts(conn.execute(Q_SQL + " WHERE q.opportunity_id = ? ORDER BY q.created_at", (opp_id,)).fetchall())
    fit = conn.execute("SELECT * FROM fit_checks WHERE opportunity_id = ? ORDER BY id DESC LIMIT 1", (opp_id,)).fetchone()
    bank = [r["text"] for r in conn.execute(
        "SELECT text FROM questions WHERE kind != 'to_ask' GROUP BY text ORDER BY MAX(best) DESC, MAX(updated_at) DESC LIMIT 300")]
    return jsonify(opportunity=o, questions=questions, fit=_fit_view(fit), sent=_sent_for(opp_id), bank=bank)


@api_prep.post("/api/opportunities/<int:opp_id>/questions/generate")
def generate_questions(opp_id):
    conn = get_db()
    o = _one("opportunities", opp_id, "Opportunity")
    fit = conn.execute("SELECT * FROM fit_checks WHERE opportunity_id = ? ORDER BY id DESC LIMIT 1", (opp_id,)).fetchone()
    existing = [r["text"] for r in conn.execute("SELECT text FROM questions WHERE opportunity_id = ?", (opp_id,))]
    data = request.get_json(silent=True) or {}
    questions, cost = ai_tools.likely_questions(o, fit, existing, override_cap=data.get("override_cap") is True)
    now = config.now_str()
    added = 0
    seen = {_norm(t) for t in existing}
    for q in questions:
        text = V.text(1000)(q["question"])
        if not text or _norm(text) in seen:
            continue
        seen.add(_norm(text))
        conn.execute("INSERT INTO questions (opportunity_id, kind, text, tags, note, created_at, updated_at) "
                     "VALUES (?, 'likely', ?, ?, ?, ?, ?)",
                     (opp_id, text, V.tags(q["tag"]), V.text(1000)(f"Why: {q['why_likely']}\nTip: {q['answer_tip']}"), now, now))
        added += 1
    log_activity(conn, "opportunity", opp_id, "questions_generated", f"Generated {added} likely interview questions for {_opp_name(o)}")
    conn.commit()
    return jsonify(added=added, cost=cost)


# ---------------------------------------------------------------- rejection log

@api_prep.get("/api/rejections")
def list_rejections():
    """Entries plus simple counts for spotting patterns (no AI involved)."""
    conn = get_db()
    rows = rows_to_dicts(conn.execute("SELECT * FROM rejections ORDER BY created_at DESC").fetchall())
    stage_order = C.keys(C.STAGES)
    by_stage = Counter(r["stage_reached"] for r in rows)
    by_month = Counter(r["created_at"][:7] for r in rows)
    days = [r["days_open"] for r in rows if r["days_open"] is not None]
    stats = {
        "total": len(rows),
        "by_reason": Counter(r["reason"] for r in rows),
        "by_stage": [{"stage": s, "count": by_stage[s]} for s in stage_order if by_stage[s]],
        "by_type": Counter(r["type"] for r in rows),
        "by_source": Counter(r["source"] for r in rows),
        "by_month": [{"month": m, "count": by_month[m]} for m in sorted(by_month)],
        "avg_days_open": round(sum(days) / len(days)) if days else None,
        "with_lessons": sum(1 for r in rows if r["lesson"].strip()),
    }
    return jsonify(items=rows, stats=stats, patterns=_patterns(rows, stats))


def _patterns(rows, stats):
    """Plain-English observations from the counts. Only says something when there's enough data."""
    out = []
    n = stats["total"]
    if n < 3:
        return ["Patterns show up after 3 or more closed applications. Keep logging."] if n else []
    early = sum(1 for r in rows if r["stage_reached"] in ("interested", "preparing", "sent", "waiting"))
    if early / n >= 0.6:
        out.append(f"{early} of {n} ended before any conversation (Sent or Waiting). The first impression "
                   "(resume, cover letter, or outreach email) is the bottleneck, not interviews.")
    talking = sum(1 for r in rows if r["stage_reached"] in ("talking", "offer"))
    if talking / n >= 0.4:
        out.append(f"{talking} of {n} ended after you were already talking. Interview prep is where to focus.")
    ghosted = stats["by_reason"].get("ghosted", 0)
    if ghosted / n >= 0.4:
        out.append(f"{ghosted} of {n} were ghosted. Earlier, more specific follow-ups (or a named contact) could help.")
    top_source, top_count = Counter(r["source"] for r in rows).most_common(1)[0]
    if top_count / n >= 0.5 and top_source:
        out.append(f"{top_count} of {n} came through {C.label(C.SOURCES, top_source)}. Try mixing in referrals or direct outreach.")
    missing = n - stats["with_lessons"]
    if missing:
        out.append(f"{missing} entr{'y has' if missing == 1 else 'ies have'} no lesson yet. Even one line helps the weekly coach.")
    return out or ["No strong pattern yet. That's fine."]


@api_prep.patch("/api/rejections/<int:rid>")
def update_rejection(rid):
    _one("rejections", rid, "Entry")
    lesson = V.text(3000)((request.get_json(silent=True) or {}).get("lesson"))
    conn = get_db()
    conn.execute("UPDATE rejections SET lesson = ? WHERE id = ?", (lesson, rid))
    conn.commit()
    return jsonify(ok=True)


@api_prep.post("/api/opportunities/<int:opp_id>/lesson")
def save_lesson(opp_id):
    """Save 'what did you learn?' on the newest rejection entry for this card."""
    lesson = V.text(3000)((request.get_json(silent=True) or {}).get("lesson"))
    conn = get_db()
    row = conn.execute("SELECT id FROM rejections WHERE opportunity_id = ? ORDER BY id DESC LIMIT 1", (opp_id,)).fetchone()
    if row is None:
        abort(404, "No rejection entry for this card.")
    conn.execute("UPDATE rejections SET lesson = ? WHERE id = ?", (lesson, row["id"]))
    if lesson:
        log_activity(conn, "opportunity", opp_id, "lesson_logged", f"Lesson: {lesson[:120]}")
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- skills profile

@api_prep.get("/api/profile")
def get_profile():
    return jsonify(text=settings_store.get_all(get_db())["skills_profile"])


@api_prep.post("/api/profile")
def save_profile():
    text = V.text(20000)((request.get_json(silent=True) or {}).get("text"))
    settings_store.set_many(get_db(), {"skills_profile": text})
    return jsonify(ok=True)

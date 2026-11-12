"""The JSON API the pages talk to. Every URL here starts with /api.

Pattern for each kind of record:
    GET    /api/<things>        list
    POST   /api/<things>        create
    GET    /api/<things>/<id>   one record with its related data
    PATCH  /api/<things>/<id>   change some fields
    DELETE /api/<things>/<id>   delete

Every incoming value goes through validation.py first, and every change is
written to the activity log.
"""
import json
from datetime import date, timedelta

from flask import Blueprint, abort, jsonify, request

import config
import constants as C
import validation as V
from db import get_db, log_activity, rows_to_dicts

api = Blueprint("api", __name__, url_prefix="/api")


# ---------------------------------------------------------------- plumbing

@api.before_request
def require_json_for_changes():
    """Writes must be sent as JSON.

    Browsers won't let another website send a JSON request to this app without
    permission, so this one check blocks a malicious page from quietly
    changing your data (a "cross-site request forgery" attack).
    """
    if request.method in ("POST", "PATCH", "PUT", "DELETE") and not request.is_json:
        abort(415, "Send JSON (Content-Type: application/json).")


@api.errorhandler(ValueError)          # includes validation.ValidationError
def handle_validation_error(e):
    return jsonify(error=str(e)), 400


@api.errorhandler(400)
@api.errorhandler(404)
@api.errorhandler(415)
def handle_http_error(e):
    return jsonify(error=e.description), e.code


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Expected a JSON object.")
    return data


def fetch_one(sql, params, what="Record"):
    row = get_db().execute(sql, params).fetchone()
    if row is None:
        abort(404, f"{what} not found.")
    return dict(row)


def insert(conn, table, values):
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(values.values()))
    return cur.lastrowid


def update(conn, table, row_id, values):
    if not values:
        return
    sets = ", ".join(f"{col} = ?" for col in values)   # column names come from validation whitelists
    conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*values.values(), row_id])


def diff(old, new):
    """Fields whose value actually changed, as {field: [old, new]}."""
    return {k: [old.get(k), v] for k, v in new.items() if old.get(k) != v}


def check_exists(table, row_id, what):
    if row_id is not None:
        fetch_one(f"SELECT id FROM {table} WHERE id = ?", (row_id,), what)


def opp_name(o):
    return f"{o['company']} · {o['title']}" if o.get("title") else o["company"]


def recent_activity(entity_type, entity_id, limit=50):
    rows = get_db().execute(
        """SELECT * FROM activity_log WHERE entity_type = ? AND entity_id = ?
           ORDER BY id DESC LIMIT ?""", (entity_type, entity_id, limit)).fetchall()
    out = rows_to_dicts(rows)
    for a in out:
        a["details"] = json.loads(a["details"]) if a["details"] else None
    return out


def checklist_for(column, parent_id):
    rows = get_db().execute(
        f"SELECT * FROM checklist_items WHERE {column} = ? ORDER BY position, id", (parent_id,)).fetchall()
    return rows_to_dicts(rows)


# ---------------------------------------------------------------- opportunities

OPP_LIST_SQL = """
    SELECT o.*,
           (SELECT COUNT(*) FROM checklist_items c WHERE c.opportunity_id = o.id)                AS check_total,
           (SELECT COUNT(*) FROM checklist_items c WHERE c.opportunity_id = o.id AND c.done = 1) AS check_done,
           (SELECT COUNT(*) FROM tasks t WHERE t.opportunity_id = o.id AND t.status != 'done')   AS open_tasks
    FROM opportunities o
"""


def attach_contacts(opps):
    """Add a 'contacts' list ([{id, name}]) to each opportunity dict."""
    if not opps:
        return opps
    rows = get_db().execute(
        """SELECT oc.opportunity_id, c.id, c.name FROM opportunity_contacts oc
           JOIN contacts c ON c.id = oc.contact_id ORDER BY c.name""").fetchall()
    by_opp = {}
    for r in rows:
        by_opp.setdefault(r["opportunity_id"], []).append({"id": r["id"], "name": r["name"]})
    for o in opps:
        o["contacts"] = by_opp.get(o["id"], [])
    return opps


def get_opportunity(opp_id):
    o = fetch_one(OPP_LIST_SQL + " WHERE o.id = ?", (opp_id,), "Opportunity")
    return attach_contacts([o])[0]


@api.get("/opportunities")
def list_opportunities():
    rows = rows_to_dicts(get_db().execute(OPP_LIST_SQL + " ORDER BY o.position, o.id").fetchall())
    for o in rows:
        # The full posting can be 60,000 characters; the board doesn't need it (the drawer loads it).
        o["has_posting"] = bool(o.pop("posting_text"))
        o.pop("research_notes", None)
    return jsonify(attach_contacts(rows))


@api.post("/opportunities")
def create_opportunity():
    conn = get_db()
    data = V.clean(body(), V.OPPORTUNITY_FIELDS)
    data.setdefault("stage", "interested")
    if data["stage"] == "closed" and not data.get("close_reason"):
        raise V.ValidationError("Pick a reason for closing.")
    if data["stage"] != "closed":
        data["close_reason"] = None
    # New cards go to the bottom of their column.
    data["position"] = conn.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 FROM opportunities WHERE stage = ?", (data["stage"],)).fetchone()[0]
    data["created_at"] = data["updated_at"] = config.now_str()
    new_id = insert(conn, "opportunities", data)
    log_activity(conn, "opportunity", new_id, "created", f"Added {opp_name(data)}")
    conn.commit()
    return jsonify(get_opportunity(new_id)), 201


@api.get("/opportunities/<int:opp_id>")
def opportunity_detail(opp_id):
    conn = get_db()
    o = get_opportunity(opp_id)
    o["checklist"] = checklist_for("opportunity_id", opp_id)
    o["contacts"] = rows_to_dicts(conn.execute(
        """SELECT c.id, c.name, c.company, c.role FROM contacts c
           JOIN opportunity_contacts oc ON oc.contact_id = c.id
           WHERE oc.opportunity_id = ? ORDER BY c.name""", (opp_id,)).fetchall())
    o["tasks"] = [serialize_task(t) for t in conn.execute(
        TASK_SQL + " WHERE t.opportunity_id = ? ORDER BY t.status = 'done', COALESCE(t.planned_date, t.due_date)",
        (opp_id,)).fetchall()]
    o["interactions"] = rows_to_dicts(conn.execute(
        """SELECT i.*, c.name AS contact_name FROM interactions i JOIN contacts c ON c.id = i.contact_id
           WHERE i.opportunity_id = ? ORDER BY i.happened_on DESC, i.id DESC""", (opp_id,)).fetchall())
    o["activity"] = recent_activity("opportunity", opp_id)
    return jsonify(o)


@api.patch("/opportunities/<int:opp_id>")
def update_opportunity(opp_id):
    conn = get_db()
    old = fetch_one("SELECT * FROM opportunities WHERE id = ?", (opp_id,), "Opportunity")
    data = V.clean(body(), V.OPPORTUNITY_FIELDS, partial=True)

    new_stage = data.get("stage", old["stage"])
    if new_stage == "closed":
        if not (data.get("close_reason") or old["close_reason"]):
            raise V.ValidationError("Pick a reason for closing.")
    else:
        data["close_reason"] = None
    if "stage" in data and data["stage"] != old["stage"]:
        data["position"] = conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 FROM opportunities WHERE stage = ?", (data["stage"],)).fetchone()[0]

    changes = diff(old, data)
    changes.pop("position", None)
    if not changes:
        return jsonify(get_opportunity(opp_id))

    data["updated_at"] = config.now_str()
    update(conn, "opportunities", opp_id, data)

    name = opp_name({**old, **data})
    if "stage" in changes or "close_reason" in changes:
        sync_rejection_log(conn, old, {**old, **data})
    if "stage" in changes:
        stage_change = changes.pop("stage")
        reason = data.get("close_reason") or old["close_reason"]
        to_label = C.label(C.STAGES, new_stage)
        if new_stage == "closed":
            to_label += f" ({C.label(C.CLOSE_REASONS, reason)})"
        changes.pop("close_reason", None)
        log_activity(conn, "opportunity", opp_id, "stage_changed",
                     f"Moved {name} from {C.label(C.STAGES, old['stage'])} to {to_label}",
                     {"stage": stage_change, "close_reason": reason if new_stage == "closed" else None})
    if changes:
        fields = ", ".join(k.replace("_", " ") for k in changes)
        log_activity(conn, "opportunity", opp_id, "updated", f"Edited {name} ({fields})", changes)
    conn.commit()
    return jsonify(get_opportunity(opp_id))


def sync_rejection_log(conn, old, new):
    """Keep the rejection log in step with a card's stage.

    Closing as rejected or ghosted adds an entry (with a snapshot of the card, so the
    history survives if the card is deleted). Reopening removes that entry, unless
    you already wrote a lesson in it.
    """
    was = old["stage"] == "closed" and old["close_reason"] in ("rejected", "ghosted")
    now_rej = new["stage"] == "closed" and new["close_reason"] in ("rejected", "ghosted")
    if now_rej and not was:
        created = date.fromisoformat(old["created_at"][:10])
        conn.execute(
            "INSERT INTO rejections (opportunity_id, company, title, type, source, reason, stage_reached, days_open, "
            "is_seed, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (old["id"], new["company"], new["title"], new["type"], new["source"], new["close_reason"],
             old["stage"] if old["stage"] != "closed" else "sent",
             (date.fromisoformat(config.today_str()) - created).days, old["is_seed"], config.now_str()))
    elif was and now_rej and old["close_reason"] != new["close_reason"]:
        conn.execute("UPDATE rejections SET reason = ? WHERE id = (SELECT MAX(id) FROM rejections WHERE opportunity_id = ?)",
                     (new["close_reason"], old["id"]))
    elif was and not now_rej:
        conn.execute("DELETE FROM rejections WHERE opportunity_id = ? AND lesson = ''", (old["id"],))


@api.delete("/opportunities/<int:opp_id>")
def delete_opportunity(opp_id):
    conn = get_db()
    old = fetch_one("SELECT * FROM opportunities WHERE id = ?", (opp_id,), "Opportunity")
    conn.execute("DELETE FROM opportunities WHERE id = ?", (opp_id,))
    log_activity(conn, "opportunity", opp_id, "deleted", f"Deleted {opp_name(old)}")
    conn.commit()
    return jsonify(ok=True)


@api.post("/opportunities/reorder")
def reorder_opportunities():
    """Save the top-to-bottom order of cards in one pipeline column after a drag."""
    data = body()
    ids = data.get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
        abort(400, "ids must be a list of numbers.")
    conn = get_db()
    for pos, opp_id in enumerate(ids):
        conn.execute("UPDATE opportunities SET position = ? WHERE id = ?", (pos, opp_id))
    conn.commit()
    return jsonify(ok=True)


@api.post("/opportunities/<int:opp_id>/contacts")
def link_contact(opp_id):
    conn = get_db()
    contact_id = V.ref_id(body().get("contact_id"))
    if contact_id is None:
        abort(400, "contact_id is required.")
    o = fetch_one("SELECT * FROM opportunities WHERE id = ?", (opp_id,), "Opportunity")
    c = fetch_one("SELECT * FROM contacts WHERE id = ?", (contact_id,), "Contact")
    conn.execute("INSERT OR IGNORE INTO opportunity_contacts VALUES (?, ?)", (opp_id, contact_id))
    log_activity(conn, "opportunity", opp_id, "linked", f"Linked {c['name']} to {opp_name(o)}")
    conn.commit()
    return jsonify(ok=True)


@api.delete("/opportunities/<int:opp_id>/contacts/<int:contact_id>")
def unlink_contact(opp_id, contact_id):
    conn = get_db()
    conn.execute("DELETE FROM opportunity_contacts WHERE opportunity_id = ? AND contact_id = ?",
                 (opp_id, contact_id))
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- tasks

TASK_SQL = """
    SELECT t.*, o.company AS opp_company, o.title AS opp_title, ct.name AS contact_name,
           (SELECT COUNT(*) FROM checklist_items c WHERE c.task_id = t.id)                AS check_total,
           (SELECT COUNT(*) FROM checklist_items c WHERE c.task_id = t.id AND c.done = 1) AS check_done
    FROM tasks t
    LEFT JOIN opportunities o ON o.id = t.opportunity_id
    LEFT JOIN contacts ct     ON ct.id = t.contact_id
"""


def serialize_task(row):
    """Task row -> dict, with completeness calculated from its checklist when it has one."""
    t = dict(row)
    if t["status"] == "done":
        t["completeness"] = 100
    elif t.get("check_total"):
        t["completeness"] = round(100 * t["check_done"] / t["check_total"])
    return t


def get_task(task_id):
    return serialize_task(fetch_one(TASK_SQL + " WHERE t.id = ?", (task_id,), "Task"))


def next_repeat_date(d, repeat):
    """The next date for a repeating task."""
    if repeat == "daily":
        return d + timedelta(days=1)
    if repeat == "weekly":
        return d + timedelta(days=7)
    if repeat == "weekdays":
        d += timedelta(days=1)
        while d.weekday() >= 5:          # 5 = Saturday, 6 = Sunday
            d += timedelta(days=1)
        return d
    return None


def spawn_next_repeat(conn, task):
    """When a repeating task is finished, create the next copy (with a fresh checklist)."""
    base_str = task["planned_date"] or task["due_date"] or config.today_str()
    base = date.fromisoformat(base_str)
    nxt = next_repeat_date(base, task["repeat"])
    shift = nxt - base

    def moved(d):
        return (date.fromisoformat(d) + shift).isoformat() if d else None

    copy_cols = ["title", "opportunity_id", "contact_id", "start_time", "duration_min", "urgency",
                 "importance", "est_min", "energy", "repeat", "notes", "is_seed"]
    new = {k: task[k] for k in copy_cols}
    new.update(due_date=moved(task["due_date"]), planned_date=moved(task["planned_date"]),
               status="todo", completeness=0, created_at=config.now_str(), updated_at=config.now_str())
    if not new["due_date"] and not new["planned_date"]:
        new["planned_date"] = nxt.isoformat()
    new_id = insert(conn, "tasks", new)
    for item in checklist_for("task_id", task["id"]):
        insert(conn, "checklist_items", {"task_id": new_id, "text": item["text"], "done": 0,
                                         "position": item["position"], "created_at": config.now_str()})
    log_activity(conn, "task", new_id, "created",
                 f"Repeating task scheduled: {task['title']} ({new['planned_date'] or new['due_date']})")


@api.get("/tasks")
def list_tasks():
    """?status=open gives only unfinished tasks."""
    sql = TASK_SQL
    if request.args.get("status") == "open":
        sql += " WHERE t.status != 'done'"
    sql += " ORDER BY COALESCE(t.planned_date, t.due_date), t.start_time"
    return jsonify([serialize_task(r) for r in get_db().execute(sql).fetchall()])


@api.post("/tasks")
def create_task():
    conn = get_db()
    data = V.clean(body(), V.TASK_FIELDS)
    check_exists("opportunities", data.get("opportunity_id"), "Opportunity")
    check_exists("contacts", data.get("contact_id"), "Contact")
    data["created_at"] = data["updated_at"] = config.now_str()
    if data.get("status") == "done":
        data["completed_at"] = config.now_str()
    new_id = insert(conn, "tasks", data)
    log_activity(conn, "task", new_id, "created", f"Added task: {data['title']}")
    conn.commit()
    return jsonify(get_task(new_id)), 201


@api.get("/tasks/<int:task_id>")
def task_detail(task_id):
    t = get_task(task_id)
    t["checklist"] = checklist_for("task_id", task_id)
    t["activity"] = recent_activity("task", task_id)
    return jsonify(t)


@api.patch("/tasks/<int:task_id>")
def update_task(task_id):
    conn = get_db()
    old = fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,), "Task")
    data = V.clean(body(), V.TASK_FIELDS, partial=True)
    check_exists("opportunities", data.get("opportunity_id"), "Opportunity")
    check_exists("contacts", data.get("contact_id"), "Contact")
    changes = diff(old, data)
    if not changes:
        return jsonify(get_task(task_id))

    now = config.now_str()
    data["updated_at"] = now
    finished = changes.get("status", [None, None])[1] == "done"
    reopened = "status" in changes and old["status"] == "done"
    if finished:
        data["completed_at"] = now
    elif reopened:
        data["completed_at"] = None
    update(conn, "tasks", task_id, data)

    title = data.get("title", old["title"])
    if finished:
        changes.pop("status")
        log_activity(conn, "task", task_id, "completed", f"Finished task: {title}",
                     {"est_min": old["est_min"], "actual_min": data.get("actual_min", old["actual_min"])})
        if old["repeat"] != "none" or data.get("repeat", "none") != "none":
            spawn_next_repeat(conn, {**old, **data})
    elif reopened:
        changes.pop("status")
        log_activity(conn, "task", task_id, "reopened", f"Reopened task: {title}")
    if changes:
        fields = ", ".join(k.replace("_", " ") for k in changes)
        log_activity(conn, "task", task_id, "updated", f"Edited task: {title} ({fields})", changes)
    conn.commit()
    return jsonify(get_task(task_id))


@api.delete("/tasks/<int:task_id>")
def delete_task(task_id):
    conn = get_db()
    old = fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,), "Task")
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    log_activity(conn, "task", task_id, "deleted", f"Deleted task: {old['title']}")
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- contacts

CONTACT_LIST_SQL = """
    SELECT c.*,
           (SELECT MAX(i.happened_on) FROM interactions i WHERE i.contact_id = c.id) AS last_contacted,
           (SELECT COUNT(*) FROM interactions i WHERE i.contact_id = c.id)           AS interaction_count,
           (SELECT COUNT(*) FROM opportunity_contacts oc WHERE oc.contact_id = c.id) AS opportunity_count
    FROM contacts c
"""


@api.get("/contacts")
def list_contacts():
    rows = get_db().execute(CONTACT_LIST_SQL + " ORDER BY c.name").fetchall()
    return jsonify(rows_to_dicts(rows))


@api.post("/contacts")
def create_contact():
    conn = get_db()
    data = V.clean(body(), V.CONTACT_FIELDS)
    data["created_at"] = data["updated_at"] = config.now_str()
    new_id = insert(conn, "contacts", data)
    log_activity(conn, "contact", new_id, "created", f"Added contact: {data['name']}")
    conn.commit()
    return jsonify(fetch_one(CONTACT_LIST_SQL + " WHERE c.id = ?", (new_id,))), 201


@api.get("/contacts/<int:contact_id>")
def contact_detail(contact_id):
    conn = get_db()
    c = fetch_one(CONTACT_LIST_SQL + " WHERE c.id = ?", (contact_id,), "Contact")
    c["interactions"] = rows_to_dicts(conn.execute(
        """SELECT i.*, o.company AS opp_company, o.title AS opp_title FROM interactions i
           LEFT JOIN opportunities o ON o.id = i.opportunity_id
           WHERE i.contact_id = ? ORDER BY i.happened_on DESC, i.id DESC""", (contact_id,)).fetchall())
    c["opportunities"] = attach_contacts(rows_to_dicts(conn.execute(
        OPP_LIST_SQL + """ JOIN opportunity_contacts oc ON oc.opportunity_id = o.id
                           WHERE oc.contact_id = ? ORDER BY o.updated_at DESC""", (contact_id,)).fetchall()))
    c["tasks"] = [serialize_task(t) for t in conn.execute(
        TASK_SQL + " WHERE t.contact_id = ? ORDER BY t.status = 'done', COALESCE(t.planned_date, t.due_date)",
        (contact_id,)).fetchall()]
    c["activity"] = recent_activity("contact", contact_id)
    return jsonify(c)


@api.patch("/contacts/<int:contact_id>")
def update_contact(contact_id):
    conn = get_db()
    old = fetch_one("SELECT * FROM contacts WHERE id = ?", (contact_id,), "Contact")
    data = V.clean(body(), V.CONTACT_FIELDS, partial=True)
    changes = diff(old, data)
    if changes:
        data["updated_at"] = config.now_str()
        update(conn, "contacts", contact_id, data)
        fields = ", ".join(k.replace("_", " ") for k in changes)
        log_activity(conn, "contact", contact_id, "updated",
                     f"Edited contact: {data.get('name', old['name'])} ({fields})", changes)
        conn.commit()
    return jsonify(fetch_one(CONTACT_LIST_SQL + " WHERE c.id = ?", (contact_id,)))


@api.delete("/contacts/<int:contact_id>")
def delete_contact(contact_id):
    conn = get_db()
    old = fetch_one("SELECT * FROM contacts WHERE id = ?", (contact_id,), "Contact")
    conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    log_activity(conn, "contact", contact_id, "deleted", f"Deleted contact: {old['name']}")
    conn.commit()
    return jsonify(ok=True)


@api.post("/contacts/<int:contact_id>/interactions")
def log_interaction(contact_id):
    """Log an email/call/coffee chat. Optionally set the next follow-up date at the same time."""
    conn = get_db()
    c = fetch_one("SELECT * FROM contacts WHERE id = ?", (contact_id,), "Contact")
    raw = body()
    has_follow_up = "next_follow_up" in raw          # only touch the contact's date if it was sent
    next_follow_up = V.iso_date(raw.pop("next_follow_up", None))
    data = V.clean(raw, V.INTERACTION_FIELDS)
    data.setdefault("kind", "other")
    data["happened_on"] = data.get("happened_on") or config.today_str()
    check_exists("opportunities", data.get("opportunity_id"), "Opportunity")
    data["contact_id"] = contact_id
    data["created_at"] = config.now_str()
    new_id = insert(conn, "interactions", data)
    if has_follow_up:
        conn.execute("UPDATE contacts SET follow_up_date = ?, updated_at = ? WHERE id = ?",
                     (next_follow_up, config.now_str(), contact_id))
    kind = C.label(C.INTERACTION_KINDS, data["kind"])
    log_activity(conn, "contact", contact_id, "interaction_logged",
                 f"{kind} — {c['name']}" + (f": {data['note']}" if data.get("note") else ""),
                 {"interaction_id": new_id, "kind": data["kind"], "happened_on": data["happened_on"]})
    conn.commit()
    return jsonify(ok=True, id=new_id), 201


@api.delete("/interactions/<int:interaction_id>")
def delete_interaction(interaction_id):
    conn = get_db()
    fetch_one("SELECT id FROM interactions WHERE id = ?", (interaction_id,), "Interaction")
    conn.execute("DELETE FROM interactions WHERE id = ?", (interaction_id,))
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- checklists

def checklist_parent(item):
    """('task', id, title) or ('opportunity', id, name) for a checklist row."""
    if item["task_id"]:
        t = fetch_one("SELECT title FROM tasks WHERE id = ?", (item["task_id"],), "Task")
        return "task", item["task_id"], t["title"]
    o = fetch_one("SELECT * FROM opportunities WHERE id = ?", (item["opportunity_id"],), "Opportunity")
    return "opportunity", item["opportunity_id"], opp_name(o)


@api.post("/checklist")
def add_checklist_item():
    conn = get_db()
    raw = body()
    task_id = V.ref_id(raw.pop("task_id", None))
    opp_id = V.ref_id(raw.pop("opportunity_id", None))
    if (task_id is None) == (opp_id is None):
        abort(400, "Send exactly one of task_id or opportunity_id.")
    check_exists("tasks", task_id, "Task")
    check_exists("opportunities", opp_id, "Opportunity")
    data = V.clean(raw, V.CHECKLIST_FIELDS)
    col, parent = ("task_id", task_id) if task_id else ("opportunity_id", opp_id)
    data[col] = parent
    data["position"] = conn.execute(
        f"SELECT COALESCE(MAX(position), 0) + 1 FROM checklist_items WHERE {col} = ?", (parent,)).fetchone()[0]
    data["created_at"] = config.now_str()
    new_id = insert(conn, "checklist_items", data)
    conn.commit()
    return jsonify(fetch_one("SELECT * FROM checklist_items WHERE id = ?", (new_id,))), 201


@api.patch("/checklist/<int:item_id>")
def update_checklist_item(item_id):
    conn = get_db()
    old = fetch_one("SELECT * FROM checklist_items WHERE id = ?", (item_id,), "Checklist item")
    data = V.clean(body(), V.CHECKLIST_FIELDS, partial=True)
    update(conn, "checklist_items", item_id, data)
    if data.get("done") == 1 and not old["done"]:
        kind, parent_id, name = checklist_parent(old)
        log_activity(conn, kind, parent_id, "checklist_checked",
                     f"Checked off “{data.get('text', old['text'])}” on {name}")
    conn.commit()
    return jsonify(fetch_one("SELECT * FROM checklist_items WHERE id = ?", (item_id,)))


@api.delete("/checklist/<int:item_id>")
def delete_checklist_item(item_id):
    conn = get_db()
    fetch_one("SELECT id FROM checklist_items WHERE id = ?", (item_id,), "Checklist item")
    conn.execute("DELETE FROM checklist_items WHERE id = ?", (item_id,))
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- week view

@api.get("/week")
def week():
    """Everything for the This Week page: 7 day columns plus Overdue and Unscheduled lanes.

    ?start=YYYY-MM-DD picks the week (any date in it works; it snaps to Monday).
    A task sits on its planned day; if it has no planned day, on its due date.
    """
    conn = get_db()
    today = config.today_str()
    try:
        anchor = date.fromisoformat(request.args.get("start") or today)
    except ValueError:
        abort(400, "start must be a date like 2026-11-09.")
    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)
    days = [{"date": (monday + timedelta(days=i)).isoformat(), "items": [], "est_min": 0} for i in range(7)]
    by_date = {d["date"]: d for d in days}
    lo, hi = monday.isoformat(), sunday.isoformat()

    # Tasks in this week.
    for row in conn.execute(
            TASK_SQL + " WHERE COALESCE(t.planned_date, t.due_date) BETWEEN ? AND ?", (lo, hi)).fetchall():
        t = serialize_task(row)
        day = by_date[t["planned_date"] or t["due_date"]]
        day["items"].append({"kind": "task", **t})
        day["est_min"] += t["est_min"] or t["duration_min"] or 0

    # Opportunity deadlines and next actions in this week (not for closed cards).
    opps = rows_to_dicts(conn.execute(
        "SELECT * FROM opportunities WHERE stage != 'closed' AND "
        "(deadline BETWEEN ? AND ? OR next_action_date BETWEEN ? AND ?)", (lo, hi, lo, hi)).fetchall())
    for o in opps:
        if o["deadline"] and lo <= o["deadline"] <= hi:
            by_date[o["deadline"]]["items"].append({"kind": "deadline", **o})
        if o["next_action_date"] and lo <= o["next_action_date"] <= hi and o["next_action"]:
            by_date[o["next_action_date"]]["items"].append({"kind": "next_action", **o})

    # Sort each day: timed events by time first, then deadlines, then everything else by urgency.
    urgency_rank = {k: i for i, k in enumerate(reversed(C.keys(C.URGENCY)))}   # on_fire first

    def sort_key(item):
        timed = item["kind"] == "task" and item.get("start_time")
        kind_rank = {"deadline": 1, "next_action": 2, "task": 3}[item["kind"]]
        return (0 if timed else 1, item.get("start_time") or "", item.get("status") == "done",
                kind_rank, urgency_rank.get(item["urgency"], 9))
    for d in days:
        d["items"].sort(key=sort_key)

    # Overdue: unfinished tasks whose due date or planned day has passed, plus stale opportunity dates.
    overdue = [{"kind": "task", **serialize_task(r)} for r in conn.execute(
        TASK_SQL + " WHERE t.status != 'done' AND (t.due_date < ? OR t.planned_date < ?)"
                   " ORDER BY COALESCE(t.due_date, t.planned_date)", (today, today)).fetchall()]
    for o in rows_to_dicts(conn.execute(
            "SELECT * FROM opportunities WHERE stage NOT IN ('closed', 'offer') AND next_action != ''"
            " AND next_action_date < ? ORDER BY next_action_date", (today,)).fetchall()):
        overdue.append({"kind": "next_action", **o})
    for o in rows_to_dicts(conn.execute(
            "SELECT * FROM opportunities WHERE stage IN ('interested', 'preparing') AND deadline < ?"
            " ORDER BY deadline", (today,)).fetchall()):
        overdue.append({"kind": "deadline", **o})

    unscheduled = [{"kind": "task", **serialize_task(r)} for r in conn.execute(
        TASK_SQL + " WHERE t.status != 'done' AND t.planned_date IS NULL AND t.due_date IS NULL"
                   " ORDER BY t.created_at DESC").fetchall()]

    return jsonify(start=lo, end=hi, today=today, days=days, overdue=overdue, unscheduled=unscheduled)

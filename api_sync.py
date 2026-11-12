"""JSON API for the Discover page (postings found for you) and the School page (Canvas).

    GET  /api/discover?status=new        the inbox (new | added | dismissed) + sources + last run
    POST /api/discover/sources           save senders, career pages, keyword/location filters
    POST /api/discover/run               check every source now
    POST /api/discover/<id>/add          make it an Interested card in the Pipeline
    POST /api/discover/<id>/dismiss      hide it (POST .../restore brings it back)
    GET  /api/discover/<id>              one posting with its full text

    GET  /api/school                     upcoming assignments, course events, announcements, link status
    POST /api/school/links               save (or clear) the Canvas feed links
    POST /api/school/run                 sync Canvas now

    GET  /api/agent                      the latest agent chat (what the panel shows)
    POST /api/agent/chat                 send a message: {message, chat_id?, override_cap?}
    POST /api/agent/new                  start a fresh chat

The Canvas links are private, so GET only ever says whether they're set ("school.instructure.com …123.ics").
"""
import json

from flask import Blueprint, abort, jsonify, request

import agent
import ai
import ai_budget
import canvas_sync
import config
import discover
import fetching
import settings_store
from db import get_db, rows_to_dicts

api_sync = Blueprint("api_sync", __name__, url_prefix="/api")


@api_sync.before_request
def require_json_for_changes():
    """Cross-site protection, same as the other APIs: changes must be JSON."""
    if request.method in ("POST", "PATCH", "DELETE") and not request.is_json:
        abort(415, "Send JSON (Content-Type: application/json).")


@api_sync.errorhandler(ValueError)
def handle_value_error(e):
    return jsonify(error=str(e)), 400


@api_sync.errorhandler(fetching.FetchError)
def handle_fetch_error(e):
    return jsonify(error=str(e)), 400


@api_sync.errorhandler(agent.AgentError)
def handle_agent_error(e):
    return jsonify(error=str(e)), 400


@api_sync.errorhandler(ai_budget.BudgetError)
def handle_budget(e):
    return jsonify(error=str(e), cap_reached=True), 402


@api_sync.errorhandler(400)
@api_sync.errorhandler(404)
@api_sync.errorhandler(415)
def handle_http_error(e):
    return jsonify(error=e.description), e.code


def _last_run(value):
    try:
        return json.loads(value) if value else None
    except ValueError:
        return None


# ---------------------------------------------------------------- Discover

LIST_COLUMNS = ("id, source, org, title, location, type, link, deadline, summary, score, score_reason, "
                "status, opportunity_id, posted_at, found_at, description != '' AS has_text")


@api_sync.get("/discover")
def discover_list():
    conn = get_db()
    status = request.args.get("status", "new")
    if status not in ("new", "added", "dismissed"):
        abort(400, "status must be new, added, or dismissed.")
    order = "COALESCE(score, -1) DESC, found_at DESC" if status == "new" else "found_at DESC"
    items = rows_to_dicts(conn.execute(
        f"SELECT {LIST_COLUMNS} FROM discoveries WHERE status = ? ORDER BY {order} LIMIT 300", (status,)).fetchall())
    counts = {r["status"]: r["n"] for r in conn.execute("SELECT status, COUNT(*) AS n FROM discoveries GROUP BY status")}
    s = settings_store.get_all(conn)
    return jsonify(
        items=items, counts=counts,
        sources={"senders": s["discover_senders"], "boards": s["discover_boards"],
                 "keywords": s["discover_keywords"], "locations": s["discover_locations"]},
        last_run=_last_run(s["discover_last_run"]),
        sweep={"on": s["discover_sweep"] == "1", "last": _last_run(s["discover_sweep_last"])},
        gmail_ready=bool(config.GMAIL_ADDRESS and config.GMAIL_APP_PASSWORD),
        gmail_address=config.GMAIL_ADDRESS, ai_enabled=config.AI_ENABLED,
        profile_set=bool(s["skills_profile"].strip()))


@api_sync.get("/discover/<int:item_id>")
def discover_one(item_id):
    row = get_db().execute("SELECT * FROM discoveries WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        abort(404, "That posting isn't in Discover anymore.")
    return jsonify(dict(row))


@api_sync.post("/discover/sources")
def discover_sources():
    data = request.get_json(silent=True) or {}
    clean = {}
    if "senders" in data:
        clean["discover_senders"] = "\n".join(discover.check_sender(s) for s in discover.lines(data["senders"]))
    if "boards" in data:
        boards = []
        for entry in discover.lines(data["boards"]):
            kind, name = discover.parse_board(entry)       # raises ValueError with a helpful message
            boards.append(f"{kind}:{name}")
        clean["discover_boards"] = "\n".join(dict.fromkeys(boards))
    for field in ("keywords", "locations"):
        if field in data:
            clean[f"discover_{field}"] = ", ".join(w[:60] for w in discover.lines(data[field])[:50])
    settings_store.set_many(get_db(), clean)
    return jsonify(ok=True)


@api_sync.post("/discover/run")
def discover_run():
    data = request.get_json(silent=True) or {}
    result = discover.run(get_db(), override_cap=bool(data.get("override_cap")), notify_me=False)
    return jsonify(result)


@api_sync.post("/discover/sweep")
def discover_sweep():
    """Run the web sweep now (about 8-10 cents). The browser asks first at the AI cap."""
    data = request.get_json(silent=True) or {}
    ai_budget.check(get_db(), override=bool(data.get("override_cap")))     # 402 -> "run anyway?"
    return jsonify(discover.web_sweep(get_db(), override_cap=bool(data.get("override_cap")), notify_me=False))


@api_sync.post("/discover/sweep-setting")
def discover_sweep_setting():
    on = bool((request.get_json(silent=True) or {}).get("on"))
    settings_store.set_many(get_db(), {"discover_sweep": "1" if on else "0"})
    return jsonify(ok=True, on=on)


@api_sync.post("/discover/<int:item_id>/add")
def discover_add(item_id):
    opp_id = discover.add_to_pipeline(get_db(), item_id)
    return jsonify(ok=True, opportunity_id=opp_id)


@api_sync.post("/discover/<int:item_id>/<action>")
def discover_status(item_id, action):
    if action not in ("dismiss", "restore"):
        abort(404, "Unknown action.")
    conn = get_db()
    conn.execute("UPDATE discoveries SET status = ? WHERE id = ? AND status != 'added'",
                 ("dismissed" if action == "dismiss" else "new", item_id))
    conn.commit()
    return jsonify(ok=True)


@api_sync.post("/discover/score")
def discover_score():
    """Score unscored postings now (e.g. after you add a skills profile)."""
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(message=discover.score_new(get_db(), override_cap=bool(data.get("override_cap"))))
    except ai.AIError as e:
        raise ValueError(str(e))


# ---------------------------------------------------------------- School (Canvas)

@api_sync.get("/school")
def school():
    conn = get_db()
    s = settings_store.get_all(conn)
    today = config.today_str()
    assignments = rows_to_dicts(conn.execute(
        """SELECT c.id, c.course, c.title, c.url, c.due_at, c.all_day, c.task_id, t.status AS task_status
           FROM canvas_items c LEFT JOIN tasks t ON t.id = c.task_id
           WHERE c.kind = 'assignment' AND substr(c.due_at, 1, 10) >= ?
           ORDER BY c.due_at LIMIT 100""", (today,)).fetchall())
    events = rows_to_dicts(conn.execute(
        """SELECT id, course, title, url, due_at, all_day FROM canvas_items
           WHERE kind = 'event' AND substr(due_at, 1, 10) BETWEEN ? AND date(?, '+14 days')
           ORDER BY due_at LIMIT 60""", (today, today)).fetchall())
    announcements = rows_to_dicts(conn.execute(
        """SELECT id, course, title, url, posted_at, body FROM canvas_items
           WHERE kind = 'announcement' ORDER BY posted_at DESC LIMIT 40""").fetchall())
    cal = s["canvas_calendar_url"].strip()
    feeds = [f.strip() for f in s["canvas_announcement_feeds"].splitlines() if f.strip()]
    return jsonify(
        assignments=assignments, events=events, announcements=announcements,
        links={"calendar": canvas_sync.masked(cal) if cal else None,
               "feeds": [canvas_sync.masked(f) for f in feeds]},
        days_ahead=s["canvas_days_ahead"], last_run=_last_run(s["canvas_last_run"]))


@api_sync.post("/school/links")
def school_links():
    """Body: {calendar?: url, add_feed?: url, clear_calendar?: true, remove_feed?: index, days_ahead?: n}"""
    data = request.get_json(silent=True) or {}
    conn = get_db()
    s = settings_store.get_all(conn)
    feeds = [f.strip() for f in s["canvas_announcement_feeds"].splitlines() if f.strip()]
    clean = {}
    if data.get("calendar"):
        clean["canvas_calendar_url"] = canvas_sync.clean_feed_url(data["calendar"], "calendar")
    if data.get("clear_calendar"):
        clean["canvas_calendar_url"] = ""
    if data.get("add_feed"):
        url = canvas_sync.clean_feed_url(data["add_feed"], "announcements")
        if url not in feeds:
            feeds.append(url)
        clean["canvas_announcement_feeds"] = "\n".join(feeds)
    if "remove_feed" in data:
        index = int(data["remove_feed"])
        if 0 <= index < len(feeds):
            feeds.pop(index)
        clean["canvas_announcement_feeds"] = "\n".join(feeds)
    if "days_ahead" in data:
        days = int(data["days_ahead"])
        if not 1 <= days <= 180:
            raise ValueError("Days ahead must be between 1 and 180.")
        clean["canvas_days_ahead"] = str(days)
    settings_store.set_many(conn, clean)
    return jsonify(ok=True)


@api_sync.post("/school/run")
def school_run():
    return jsonify(canvas_sync.run(get_db(), notify_me=False))


# ---------------------------------------------------------------- Agent chat

def _chat_view(row):
    if row is None:
        return {"chat_id": None, "display": [], "cost": 0}
    return {"chat_id": row["id"], "display": json.loads(row["display"]), "cost": round(row["cost_usd"], 4)}


@api_sync.get("/agent")
def agent_latest():
    return jsonify({**_chat_view(agent.load_chat(get_db())), "ai_enabled": config.AI_ENABLED})


@api_sync.post("/agent/new")
def agent_new():
    return jsonify(_chat_view(agent.new_chat(get_db())))


@api_sync.post("/agent/chat")
def agent_chat():
    data = request.get_json(silent=True) or {}
    chat_id = data.get("chat_id")
    return jsonify(agent.chat(get_db(), int(chat_id) if chat_id else None, data.get("message", ""),
                              override_cap=bool(data.get("override_cap"))))

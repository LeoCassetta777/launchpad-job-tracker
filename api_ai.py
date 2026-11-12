"""JSON endpoints for the AI features and the Settings page. URLs start with /api.

    GET  /api/ai/status   is AI configured? which models?
    POST /api/ai/parse    {text, mode: "dump" | "posting", url?, title?}  ->  preview items
    POST /api/demo        {action: "load" | "wipe" | "reset"}             demo data on/off

Parsing never saves anything. The browser saves accepted previews through the
normal /api endpoints, so the usual validation and activity log apply.
"""
from flask import Blueprint, abort, jsonify, request

import ai
import ai_budget
import config
import seed
import settings_store
from db import get_db

api_ai = Blueprint("api_ai", __name__, url_prefix="/api")


@api_ai.before_request
def require_json_for_changes():
    # Same cross-site protection as api.py: writes must be JSON.
    if request.method == "POST" and not request.is_json:
        abort(415, "Send JSON (Content-Type: application/json).")


@api_ai.errorhandler(ai.AIError)
def handle_ai_error(e):
    return jsonify(error=str(e)), 400


@api_ai.errorhandler(ai_budget.BudgetError)
def handle_budget(e):
    # 402 = "payment required". cap_reached tells the browser to offer "Run anyway".
    return jsonify(error=str(e), cap_reached=True), 402


@api_ai.errorhandler(400)
@api_ai.errorhandler(415)
def handle_http_error(e):
    return jsonify(error=e.description), e.code


@api_ai.get("/ai/status")
def ai_status():
    # Only says whether a key exists. The key itself never leaves the server.
    return jsonify(enabled=config.AI_ENABLED, parse_model=config.PARSE_MODEL, smart_model=config.SMART_MODEL)


@api_ai.post("/ai/parse")
def ai_parse():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "dump")
    if mode not in ("dump", "posting"):
        abort(400, "mode must be 'dump' or 'posting'.")
    url = str(data.get("url") or "").strip()[:1000] or None
    if url and not url.lower().startswith(("http://", "https://")):
        url = None
    title = str(data.get("title") or "").strip()[:300] or None
    return jsonify(ai.parse(str(data.get("text") or ""), mode, url=url, title=title,
                            override_cap=data.get("override_cap") is True))


@api_ai.get("/ai/budget")
def ai_budget_summary():
    return jsonify(ai_budget.summary(get_db()))


@api_ai.post("/ai/budget")
def ai_budget_save():
    """{monthly_cap: 3.00, override_this_month: true|false}"""
    data = request.get_json(silent=True) or {}
    conn = get_db()
    changes = {}
    if "monthly_cap" in data:
        try:
            cap = round(float(data["monthly_cap"]), 2)
        except (TypeError, ValueError):
            abort(400, "The monthly cap must be a dollar amount, like 3.00.")
        if not 0 <= cap <= 500:
            abort(400, "The monthly cap must be between $0 and $500.")
        changes["ai_monthly_cap"] = f"{cap:.2f}"
    if "override_this_month" in data:
        changes["ai_cap_override_month"] = config.now().strftime("%Y-%m") if data["override_this_month"] else ""
    settings_store.set_many(conn, changes)
    return jsonify(ai_budget.summary(conn))


@api_ai.post("/demo")
def demo_data():
    action = (request.get_json(silent=True) or {}).get("action")
    if action not in ("load", "wipe", "reset"):
        abort(400, "action must be load, wipe, or reset.")
    conn = get_db()
    if action in ("wipe", "reset"):
        seed.wipe(conn)
    if action in ("load", "reset") and not seed.has_seed_data(conn):
        seed.seed(conn)
    return jsonify(ok=True, has_demo=seed.has_seed_data(conn))

"""Phase 5 endpoints: focus, motivation, and review (no AI except the coach).

    GET  /api/progress              points, level, streak, weekly goals, today's Top 3
    POST /api/goals                 {goals: [{kind, target}]}
    GET  /api/suggest?minutes=&energy=   "I have __ minutes": best 3 tasks that fit
    POST /api/focus                 {task_id, minutes}: log a finished focus session
    POST /api/pins                  {item_type, item_id}: pin to Today's Top 3
    DELETE /api/pins/<id>
    GET  /api/matrix                Eisenhower quadrants;  POST /api/matrix/move {item_type, item_id, urgent, important}
    POST /api/matrix/settings       {include_medium}
    GET  /api/shutdown              today's unfinished tasks + today's numbers;  POST /api/wins {text}
    GET  /api/stats                 numbers for the Stats page charts
    GET  /api/reviews, POST /api/reviews/generate, POST /api/reviews/<id>   weekly coach (coach.py)
"""
import json
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, jsonify, request

import ai
import ai_budget
import coach
import config
import constants as C
import progress
import settings_store
import validation as V
from db import get_db, log_activity, rows_to_dicts

api_focus = Blueprint("api_focus", __name__, url_prefix="/api")

URGENCY_RANK = {"chill": 1, "soon": 2, "pressing": 3, "on_fire": 4}
IMPORTANCE_RANK = {"low": 1, "medium": 2, "high": 3}
ENERGY_RANK = {"low": 1, "med": 2, "high": 3}


@api_focus.before_request
def require_json_for_changes():
    if request.method in ("POST", "DELETE") and not request.is_json:
        abort(415, "Send JSON (Content-Type: application/json).")


@api_focus.errorhandler(ai_budget.BudgetError)
def handle_budget(e):
    return jsonify(error=str(e), cap_reached=True), 402


@api_focus.errorhandler(ValueError)
@api_focus.errorhandler(ai.AIError)
def handle_error(e):
    return jsonify(error=str(e)), 400


@api_focus.errorhandler(400)
@api_focus.errorhandler(404)
@api_focus.errorhandler(415)
def handle_http_error(e):
    return jsonify(error=e.description), e.code


def _today():
    return config.now().date()


# ---------------------------------------------------------------- progress + goals + Top 3

def _pins(conn, day):
    out = []
    for p in conn.execute("SELECT * FROM pins WHERE day = ? ORDER BY position, id", (day,)).fetchall():
        if p["item_type"] == "task":
            row = conn.execute("SELECT id, title AS name, status, urgency, planned_date, due_date FROM tasks WHERE id = ?",
                               (p["item_id"],)).fetchone()
        else:
            row = conn.execute("SELECT id, company || CASE WHEN title != '' THEN ' · ' || title ELSE '' END AS name, "
                               "stage AS status, urgency FROM opportunities WHERE id = ?", (p["item_id"],)).fetchone()
        if row:
            out.append({"pin_id": p["id"], "item_type": p["item_type"], **dict(row)})
    return out


@api_focus.get("/progress")
def get_progress():
    conn = get_db()
    data = progress.summary(conn)
    data["top3"] = _pins(conn, _today().isoformat())
    data["goal_kinds"] = [{"key": k, "label": v[0], "icon": v[1]} for k, v in progress.GOAL_KINDS.items()]
    return jsonify(data)


@api_focus.post("/goals")
def save_goals():
    goals = (request.get_json(silent=True) or {}).get("goals")
    if not isinstance(goals, list) or len(goals) > 5:
        abort(400, "Send up to 5 goals.")
    clean = []
    for g in goals:
        if not isinstance(g, dict) or g.get("kind") not in progress.GOAL_KINDS:
            abort(400, f"Unknown goal type. Use one of: {', '.join(progress.GOAL_KINDS)}.")
        target = V.integer(1, 200)(g.get("target"))
        if not target:
            abort(400, "Each goal needs a target of at least 1.")
        clean.append({"kind": g["kind"], "target": target})
    settings_store.set_many(get_db(), {"weekly_goals": json.dumps(clean)})
    return get_progress()


@api_focus.post("/pins")
def add_pin():
    conn = get_db()
    data = request.get_json(silent=True) or {}
    item_type = data.get("item_type")
    item_id = V.ref_id(data.get("item_id"))
    if item_type not in ("task", "opportunity") or not item_id:
        abort(400, "Pin a task or an opportunity.")
    table = "tasks" if item_type == "task" else "opportunities"
    if conn.execute(f"SELECT id FROM {table} WHERE id = ?", (item_id,)).fetchone() is None:
        abort(404, "Not found.")
    day = _today().isoformat()
    count = conn.execute("SELECT COUNT(*) FROM pins WHERE day = ?", (day,)).fetchone()[0]
    if count >= 3:
        abort(400, "Today's Top 3 is full. Unpin one first.")
    conn.execute("INSERT OR IGNORE INTO pins (day, item_type, item_id, position, created_at) VALUES (?, ?, ?, ?, ?)",
                 (day, item_type, item_id, count, config.now_str()))
    conn.commit()
    return jsonify(_pins(conn, day))


@api_focus.delete("/pins/<int:pin_id>")
def remove_pin(pin_id):
    conn = get_db()
    conn.execute("DELETE FROM pins WHERE id = ?", (pin_id,))
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- "I have __ minutes" + focus timer

def task_score(t, today):
    """Higher = do it sooner. Urgency and importance, plus a boost as the due date nears."""
    score = URGENCY_RANK.get(t["urgency"], 1) * 3 + IMPORTANCE_RANK.get(t["importance"], 2) * 2
    reasons = []
    if t["due_date"]:
        days = (date.fromisoformat(t["due_date"]) - today).days
        if days < 0:
            score, reasons = score + 6, reasons + [f"overdue by {-days} day{'s' if days != -1 else ''}"]
        elif days == 0:
            score, reasons = score + 5, reasons + ["due today"]
        elif days <= 2:
            score, reasons = score + 3, reasons + [f"due in {days} day{'s' if days != 1 else ''}"]
        elif days <= 7:
            score += 1
    if t["planned_date"] == today.isoformat():
        score, reasons = score + 2, reasons + ["planned for today"]
    if t["urgency"] in ("pressing", "on_fire"):
        reasons.append(C.label(C.URGENCY, t["urgency"]).lower())
    if t["importance"] == "high":
        reasons.append("high importance")
    return score, reasons


@api_focus.get("/suggest")
def suggest():
    """Rule-based, no AI: the 3 best open tasks that fit the time and energy you have."""
    minutes = V.integer(5, 480)(request.args.get("minutes")) or 30
    energy = request.args.get("energy", "med")
    if energy not in ENERGY_RANK:
        abort(400, "energy must be low, med, or high.")
    today = _today()
    picks = []
    for t in get_db().execute("SELECT t.*, o.company AS opp_company FROM tasks t LEFT JOIN opportunities o "
                              "ON o.id = t.opportunity_id WHERE t.status != 'done' AND t.start_time IS NULL").fetchall():
        remaining = max(5, (t["est_min"] or 30) - (t["actual_min"] or 0))
        if remaining > minutes or ENERGY_RANK.get(t["energy"], 2) > ENERGY_RANK[energy]:
            continue
        score, reasons = task_score(t, today)
        picks.append({**dict(t), "score": score, "reasons": reasons, "remaining_min": remaining})
    picks.sort(key=lambda p: (-p["score"], p["remaining_min"]))
    return jsonify(picks[:3])


@api_focus.post("/focus")
def log_focus():
    """A finished (or stopped) focus session: add the minutes to the task's actual time."""
    conn = get_db()
    data = request.get_json(silent=True) or {}
    minutes = V.integer(1, 240)(data.get("minutes"))
    if not minutes:
        abort(400, "minutes is required.")
    task_id = V.ref_id(data.get("task_id"))
    title = "no task"
    if task_id:
        t = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if t is None:
            abort(404, "Task not found.")
        conn.execute("UPDATE tasks SET actual_min = COALESCE(actual_min, 0) + ?, updated_at = ? WHERE id = ?",
                     (minutes, config.now_str(), task_id))
        title = t["title"]
    log_activity(conn, "task" if task_id else "focus", task_id, "focus_session",
                 f"Focused {minutes} min on {title}", {"minutes": minutes, "task_id": task_id})
    conn.commit()
    return jsonify(ok=True, points=minutes // 5)


@api_focus.get("/focus/settings")
def focus_settings():
    s = settings_store.get_all(get_db())
    return jsonify(work=int(s["focus_work_min"]), brk=int(s["focus_break_min"]))


# ---------------------------------------------------------------- Eisenhower matrix

def _is_urgent(item, today):
    if item["urgency"] in ("pressing", "on_fire"):
        return True
    due = item.get("due_date") or item.get("deadline")
    return bool(due) and (date.fromisoformat(due) - today).days <= 3


@api_focus.get("/matrix")
def matrix():
    conn = get_db()
    include_medium = settings_store.get_all(conn)["matrix_include_medium"] == "1"
    important_levels = {"high", "medium"} if include_medium else {"high"}
    today = _today()
    items = [{"item_type": "task", **dict(t)} for t in conn.execute(
        "SELECT t.id, t.title AS name, t.urgency, t.importance, t.due_date, t.planned_date, t.est_min, "
        "o.company AS opp_company FROM tasks t LEFT JOIN opportunities o ON o.id = t.opportunity_id "
        "WHERE t.status != 'done'").fetchall()]
    items += [{"item_type": "opportunity", **dict(o)} for o in conn.execute(
        "SELECT id, company || CASE WHEN title != '' THEN ' · ' || title ELSE '' END AS name, urgency, importance, "
        "deadline, stage FROM opportunities WHERE stage NOT IN ('closed', 'offer')").fetchall()]
    for it in items:
        it["urgent"] = _is_urgent(it, today)
        it["important"] = it["importance"] in important_levels
        it["urgent_by_date"] = it["urgent"] and it["urgency"] not in ("pressing", "on_fire")
    return jsonify(items=items, include_medium=include_medium)


@api_focus.post("/matrix/move")
def matrix_move():
    """Dragging between quadrants changes urgency/importance to match."""
    conn = get_db()
    data = request.get_json(silent=True) or {}
    item_type, item_id = data.get("item_type"), V.ref_id(data.get("item_id"))
    if item_type not in ("task", "opportunity") or not item_id:
        abort(400, "Bad item.")
    table = "tasks" if item_type == "task" else "opportunities"
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        abort(404, "Not found.")
    include_medium = settings_store.get_all(conn)["matrix_include_medium"] == "1"
    changes = {}
    if data.get("urgent") and row["urgency"] not in ("pressing", "on_fire"):
        changes["urgency"] = "pressing"
    if not data.get("urgent") and row["urgency"] in ("pressing", "on_fire"):
        changes["urgency"] = "soon"
    important_now = row["importance"] == "high" or (include_medium and row["importance"] == "medium")
    if data.get("important") and not important_now:
        changes["importance"] = "high"
    if not data.get("important") and important_now:
        changes["importance"] = "low" if include_medium else "medium"
    if changes:
        sets = ", ".join(f"{k} = ?" for k in changes)
        conn.execute(f"UPDATE {table} SET {sets}, updated_at = ? WHERE id = ?", [*changes.values(), config.now_str(), item_id])
        name = row["title"] if item_type == "task" else row["company"]
        log_activity(conn, item_type, item_id, "updated", f"Re-prioritized {name} ({', '.join(f'{k} → {v}' for k, v in changes.items())})",
                     {k: [row[k], v] for k, v in changes.items()})
        conn.commit()
    due = row["due_date"] if item_type == "task" else row["deadline"]
    still_urgent = not data.get("urgent") and bool(due) and (date.fromisoformat(due) - _today()).days <= 3
    return jsonify(changes=changes, still_urgent_by_date=still_urgent)


@api_focus.post("/matrix/settings")
def matrix_settings():
    value = "1" if (request.get_json(silent=True) or {}).get("include_medium") else "0"
    settings_store.set_many(get_db(), {"matrix_include_medium": value})
    return jsonify(ok=True)


# ---------------------------------------------------------------- end-of-day shutdown

@api_focus.get("/shutdown")
def shutdown():
    conn = get_db()
    t = _today().isoformat()
    tasks = rows_to_dicts(conn.execute(
        "SELECT t.*, o.company AS opp_company FROM tasks t LEFT JOIN opportunities o ON o.id = t.opportunity_id "
        "WHERE t.status != 'done' AND COALESCE(t.planned_date, t.due_date) <= ? ORDER BY COALESCE(t.planned_date, t.due_date)",
        (t,)).fetchall())
    today_rows = conn.execute("SELECT * FROM activity_log WHERE is_seed = 0 AND created_at >= ?", (t,)).fetchall()
    done = [r["summary"].removeprefix("Finished task: ") for r in today_rows if r["action"] == "completed"]
    focus = sum(json.loads(r["details"] or "{}").get("minutes", 0) for r in today_rows if r["action"] == "focus_session")
    win = next((r["summary"].removeprefix("Win: ") for r in reversed(today_rows) if r["action"] == "win_logged"), None)
    return jsonify(tasks=tasks, done_today=done, focus_minutes=focus, points_today=sum(progress.points_for(r) for r in today_rows),
                   win=win, tomorrow=(_today() + timedelta(days=1)).isoformat())


@api_focus.post("/wins")
def log_win():
    text = V.text(300, required=True)((request.get_json(silent=True) or {}).get("text"))
    conn = get_db()
    log_activity(conn, "day", None, "win_logged", f"Win: {text}", {"date": _today().isoformat()})
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- stats

@api_focus.get("/stats")
def stats():
    conn = get_db()
    stages = [k for k in C.keys(C.STAGES) if k != "closed"]
    index = {k: i for i, k in enumerate(stages)}
    opps = {o["id"]: dict(o) for o in conn.execute("SELECT id, type, stage, created_at FROM opportunities").fetchall()}
    reached = {oid: index.get(o["stage"], 0) for oid, o in opps.items()}      # furthest stage reached
    first_at = defaultdict(dict)                                                # opp -> stage -> first time reached
    for r in conn.execute("SELECT * FROM activity_log WHERE action = 'stage_changed' AND entity_type = 'opportunity' "
                          "ORDER BY id").fetchall():
        old, new = (json.loads(r["details"] or "{}").get("stage") or [None, None])[:2]
        for s in (old, new):
            if r["entity_id"] in reached and s in index:
                reached[r["entity_id"]] = max(reached[r["entity_id"]], index[s])
        if new in index:
            first_at[r["entity_id"]].setdefault(new, r["created_at"])
    replied = {r["opportunity_id"] for r in conn.execute(
        "SELECT DISTINCT opportunity_id FROM interactions WHERE kind = 'replied' AND opportunity_id IS NOT NULL")}

    funnel = [{"stage": s, "label": C.label(C.STAGES, s), "count": sum(1 for v in reached.values() if v >= index[s])}
              for s in stages]
    sent = [oid for oid, v in reached.items() if v >= index["sent"]]
    responded = [oid for oid in sent if reached[oid] >= index["talking"] or oid in replied]
    waits = []
    for oid, times in first_at.items():
        if "sent" in times and "talking" in times and times["talking"] > times["sent"]:
            waits.append((datetime.fromisoformat(times["talking"]) - datetime.fromisoformat(times["sent"])).days)

    monday = progress.week_bounds()[0]
    weeks = []
    for i in range(7, -1, -1):
        m = monday - timedelta(weeks=i)
        counts = progress.week_counts(conn, m)
        weeks.append({"week": m.isoformat(), "applications": counts["applications"], "outreach": counts["outreach"],
                      "focus_hours": counts["focus_hours"], "tasks_done": counts["tasks_done"]})

    estimates = rows_to_dicts(conn.execute(
        "SELECT title, est_min, actual_min, completed_at FROM tasks WHERE status = 'done' AND est_min > 0 AND actual_min > 0 "
        "ORDER BY completed_at DESC LIMIT 12").fetchall())
    est_total = sum(e["est_min"] for e in estimates)
    return jsonify(
        funnel=funnel,
        sent=len(sent), responded=len(responded),
        response_rate=round(100 * len(responded) / len(sent)) if sent else None,
        avg_days_to_hear_back=round(sum(waits) / len(waits), 1) if waits else None, waits_measured=len(waits),
        weeks=weeks,
        estimates=list(reversed(estimates)),
        estimate_ratio=round(sum(e["actual_min"] for e in estimates) / est_total, 2) if est_total else None,
    )


# ---------------------------------------------------------------- weekly review (coach)

@api_focus.get("/reviews")
def list_reviews():
    conn = get_db()
    rows = rows_to_dicts(conn.execute("SELECT * FROM reviews ORDER BY week_start DESC LIMIT 26").fetchall())
    for r in rows:
        r["data"] = json.loads(r["data"])
    return jsonify(reviews=rows, this_week=progress.week_bounds()[0].isoformat())


@api_focus.post("/reviews/generate")
def generate_review():
    data = request.get_json(silent=True) or {}
    review = coach.generate(get_db(), override_cap=data.get("override_cap") is True)
    return jsonify(review)


@api_focus.post("/reviews/<int:rid>")
def save_review(rid):
    conn = get_db()
    if conn.execute("SELECT id FROM reviews WHERE id = ?", (rid,)).fetchone() is None:
        abort(404, "Review not found.")
    notes = V.text(10000)((request.get_json(silent=True) or {}).get("my_notes"))
    conn.execute("UPDATE reviews SET my_notes = ?, status = 'saved', updated_at = ? WHERE id = ?", (notes, config.now_str(), rid))
    log_activity(conn, "review", rid, "review_saved", "Saved the weekly review")
    conn.commit()
    return jsonify(ok=True)

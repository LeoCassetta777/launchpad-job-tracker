"""Points, levels, streaks, and weekly goals, all calculated from the activity log.

Nothing is stored separately: every number here is recomputed from what you
actually did (activity_log), so it can't drift out of sync.

Points
    finish a task 10 · log an interaction 15 · move a card forward 20
    reach Sent 25 · reach Talking 30 · reach Offer 100
    closed as rejected/ghosted 15 (a rejection means you applied)
    focus: 1 per 5 minutes · log a lesson 5 · log a win 5 · log a question 3 · send a document 5
Streak
    consecutive days on which you moved a card forward, logged an interaction, or finished a task.
Weekly goals (Monday-Sunday, Eastern)
    applications, outreach, focus_hours, tasks_done, interviews
"""
import json
from datetime import date, timedelta

import config
import constants as C
import settings_store

STAGE_INDEX = {k: i for i, k in enumerate(C.keys(C.STAGES))}

LEVELS = [
    (0, "Sticker Collector", "🌱"),
    (100, "Cover Letter Cadet", "✉️"),
    (250, "Networking Ninja", "🥷"),
    (500, "Interview Wrangler", "🤠"),
    (900, "Offer Magnet", "🧲"),
    (1500, "Career Rocketeer", "🚀"),
    (2500, "Launchpad Legend", "🏆"),
]

GOAL_KINDS = {
    "applications": ("Applications sent", "📨"),
    "outreach": ("Outreach (emails, calls, chats)", "✉️"),
    "focus_hours": ("Focus hours", "⏱️"),
    "tasks_done": ("Tasks finished", "✅"),
    "interviews": ("Conversations started (Talking)", "💬"),
}
DEFAULT_GOALS = [{"kind": "applications", "target": 5}, {"kind": "outreach", "target": 3},
                 {"kind": "focus_hours", "target": 10}]
OUTREACH_KINDS = {"emailed", "linkedin", "call", "coffee", "event"}


def _details(row):
    return json.loads(row["details"]) if row["details"] else {}


def _stage_move(row):
    """(old, new, close_reason) for a stage change, else None."""
    if row["action"] != "stage_changed":
        return None
    d = _details(row)
    old, new = (d.get("stage") or [None, None])[:2]
    return old, new, d.get("close_reason")


def points_for(row):
    """Points earned by one activity-log row."""
    action = row["action"]
    if action == "completed":
        return 10
    if action == "interaction_logged":
        return 15
    if action == "focus_session":
        return _details(row).get("minutes", 0) // 5
    if action in ("lesson_logged", "win_logged", "document_sent"):
        return 5
    if action == "question_logged":
        return 3
    move = _stage_move(row)
    if move:
        old, new, reason = move
        if new == "closed":
            return 15 if reason in ("rejected", "ghosted") else 5
        if new in STAGE_INDEX and old in STAGE_INDEX and STAGE_INDEX[new] > STAGE_INDEX[old]:
            return {"sent": 25, "talking": 30, "offer": 100}.get(new, 20)
    return 0


def is_streak_action(row):
    """Counts toward the streak: moved a card forward, logged an interaction, finished a task."""
    if row["action"] in ("completed", "interaction_logged"):
        return True
    move = _stage_move(row)
    return bool(move and move[1] != "closed" and move[0] in STAGE_INDEX and move[1] in STAGE_INDEX
                and STAGE_INDEX[move[1]] > STAGE_INDEX[move[0]])


def level_for(points):
    current = LEVELS[0]
    for lvl in LEVELS:
        if points >= lvl[0]:
            current = lvl
    i = LEVELS.index(current)
    nxt = LEVELS[i + 1] if i + 1 < len(LEVELS) else None
    return {"name": current[1], "icon": current[2], "floor": current[0], "number": i + 1,
            "next_name": nxt[1] if nxt else None, "next_at": nxt[0] if nxt else None}


def _rows(conn, since=None):
    sql = "SELECT * FROM activity_log WHERE is_seed = 0"
    params = []
    if since:
        sql += " AND created_at >= ?"
        params.append(since)
    return conn.execute(sql + " ORDER BY id", params).fetchall()


def streak(conn, today=None):
    """(days, at_risk). at_risk = the streak is alive but nothing counted yet today."""
    today = today or config.now().date()
    days = {r["created_at"][:10] for r in _rows(conn, (today - timedelta(days=400)).isoformat()) if is_streak_action(r)}
    at_risk = today.isoformat() not in days
    d = today if not at_risk else today - timedelta(days=1)
    count = 0
    while d.isoformat() in days:
        count += 1
        d -= timedelta(days=1)
    return count, at_risk and count > 0


def week_bounds(day=None):
    day = day or config.now().date()
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def week_counts(conn, monday):
    """Raw counts for one Monday-Sunday week, used by goals, stats, and the coach."""
    lo, hi = monday.isoformat(), (monday + timedelta(days=7)).isoformat()
    rows = [r for r in _rows(conn, lo) if r["created_at"] < hi]
    types = {r["id"]: r["type"] for r in conn.execute("SELECT id, type FROM opportunities").fetchall()}
    counts = {"applications": 0, "outreach": 0, "focus_minutes": 0, "tasks_done": 0, "interviews": 0,
              "points": 0, "wins": [], "lessons": 0}
    for r in rows:
        counts["points"] += points_for(r)
        move = _stage_move(r)
        if move and move[1] == "sent" and r["entity_type"] == "opportunity":
            counts["outreach" if types.get(r["entity_id"]) == "outreach" else "applications"] += 1
        if move and move[1] == "talking":
            counts["interviews"] += 1
        if r["action"] == "interaction_logged" and _details(r).get("kind") in OUTREACH_KINDS:
            counts["outreach"] += 1
        if r["action"] == "completed":
            counts["tasks_done"] += 1
        if r["action"] == "focus_session":
            counts["focus_minutes"] += _details(r).get("minutes", 0)
        if r["action"] == "win_logged":
            counts["wins"].append(r["summary"].removeprefix("Win: "))
        if r["action"] == "lesson_logged":
            counts["lessons"] += 1
    counts["focus_hours"] = round(counts["focus_minutes"] / 60, 1)
    return counts


def goals(conn):
    raw = settings_store.get_all(conn).get("weekly_goals") or ""
    try:
        return json.loads(raw) if raw else DEFAULT_GOALS
    except json.JSONDecodeError:
        return DEFAULT_GOALS


def goal_progress(conn, monday=None):
    monday = monday or week_bounds()[0]
    counts = week_counts(conn, monday)
    out = []
    for g in goals(conn):
        label, icon = GOAL_KINDS.get(g["kind"], (g["kind"], "🎯"))
        done = counts.get(g["kind"], 0)
        out.append({"kind": g["kind"], "label": label, "icon": icon, "target": g["target"], "done": done,
                    "percent": min(100, round(100 * done / g["target"])) if g["target"] else 100})
    return out, counts


def summary(conn):
    """Everything the home-page strip shows."""
    total = sum(points_for(r) for r in _rows(conn))
    days, at_risk = streak(conn)
    progress, counts = goal_progress(conn)
    monday, _ = week_bounds()
    return {"points": total, "level": level_for(total), "streak": days, "streak_at_risk": at_risk,
            "week_points": counts["points"], "goals": progress, "week_start": monday.isoformat()}

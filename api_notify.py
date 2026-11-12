"""Reminders, notifications, and calendar files.

JSON (under /api):
    GET  /api/notifications            the bell: recent reminders + unread count
    POST /api/notifications/read       mark them all read
    GET  /api/reminder-settings        current choices + what's set up (never the secrets)
    POST /api/reminder-settings        save choices and the two email addresses
    POST /api/test/email | /api/test/push | /api/reminders/run

Downloads and previews (plain pages):
    /calendar/opportunity/<id>.ics, /calendar/task/<id>.ics, /calendar/contact/<id>.ics
    /calendar/week.ics?start=YYYY-MM-DD
    /settings/preview/<digest|weekly|reminders>   see an email without sending it
"""
from datetime import date, timedelta

from flask import Blueprint, Response, abort, jsonify, request

import calendar_ics
import config
import notify
import reminders
import settings_store
import validation as V
from db import get_db

api_notify = Blueprint("api_notify", __name__)


@api_notify.before_request
def require_json_for_changes():
    if request.method == "POST" and not request.is_json:
        abort(415, "Send JSON (Content-Type: application/json).")


@api_notify.errorhandler(notify.NotifyError)
@api_notify.errorhandler(ValueError)
def handle_error(e):
    return jsonify(error=str(e)), 400


@api_notify.errorhandler(400)
@api_notify.errorhandler(404)
@api_notify.errorhandler(415)
def handle_http_error(e):
    return jsonify(error=e.description), e.code


# ---------------------------------------------------------------- the bell

@api_notify.get("/api/notifications")
def list_notifications():
    conn = get_db()
    rows = conn.execute("SELECT id, trigger, title, body, link, created_at, read_at, error, "
                        "email_sent_at, push_sent_at FROM notifications ORDER BY id DESC LIMIT 30").fetchall()
    unread = conn.execute("SELECT COUNT(*) FROM notifications WHERE read_at IS NULL").fetchone()[0]
    return jsonify(items=[dict(r) for r in rows], unread=unread)


@api_notify.post("/api/notifications/read")
def mark_read():
    conn = get_db()
    conn.execute("UPDATE notifications SET read_at = ? WHERE read_at IS NULL", (config.now_str(),))
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- settings

def _status():
    # True/False only. The password and topic themselves never leave the server.
    return {"gmail_address": config.GMAIL_ADDRESS, "notify_email": config.NOTIFY_EMAIL,
            "app_password_set": bool(config.GMAIL_APP_PASSWORD), "email_ready": config.email_ready(),
            "push_ready": config.push_ready(), "base_url": config.app_base_url()}


@api_notify.get("/api/reminder-settings")
def get_reminder_settings():
    return jsonify(settings=settings_store.public(settings_store.get_all(get_db())), status=_status(),
                   triggers=[{"key": k, "label": label} for k, label, _ in settings_store.TRIGGERS],
                   channels=settings_store.CHANNELS)


@api_notify.post("/api/reminder-settings")
def save_reminder_settings():
    data = request.get_json(silent=True) or {}
    clean = {}
    for key, _label, _default in settings_store.TRIGGERS:
        value = data.get(f"channel.{key}")
        if value is not None:
            if value not in settings_store.CHANNELS:
                raise ValueError(f"{key} must be one of {', '.join(settings_store.CHANNELS)}.")
            clean[f"channel.{key}"] = value
    if "deadline_days" in data:
        days = V.reminder_days(data["deadline_days"])
        if days in ("", "off"):
            raise ValueError("Default deadline reminders need at least one day, like 7,2,0.")
        clean["deadline_days"] = days
    if "followup_after_days" in data:
        n = V.integer(1, 60)(data["followup_after_days"])
        if n is None:
            raise ValueError("Follow-up nudge needs a number of days.")
        clean["followup_after_days"] = str(n)
    if "remind_demo" in data:
        clean["remind_demo"] = "1" if V.flag(data["remind_demo"]) else "0"
    for field, env_name in (("gmail_address", "GMAIL_ADDRESS"), ("notify_email", "NOTIFY_EMAIL")):
        if field in data:
            settings_store.save_env_value(env_name, V.email(data[field]))
    settings_store.set_many(get_db(), clean)
    return jsonify(ok=True, settings=settings_store.public(settings_store.get_all(get_db())), status=_status())


# ---------------------------------------------------------------- tests and manual run

@api_notify.post("/api/test/email")
def test_email():
    sample = [{"trigger": "deadline", "title": "Test reminder: this is what a deadline email looks like",
               "body": "If you can read this in your school inbox, email works. 🎉", "link": "/"}]
    notify.send_email("Test email", notify.render_email("reminders.html", items=sample),
                      "Test email from Launchpad. If you can read this, email works.")
    return jsonify(ok=True, message=f"Sent to {config.NOTIFY_EMAIL}. Check your inbox (and Junk).")


@api_notify.post("/api/test/push")
def test_push():
    notify.send_push("Test push — it works! 🎉", tags="tada")
    return jsonify(ok=True, message="Sent. It should pop up on your phone within a few seconds.")


@api_notify.post("/api/reminders/run")
def run_now():
    """Run the 15-minute check right now (respects quiet hours unless asked not to)."""
    data = request.get_json(silent=True) or {}
    log = reminders.run_checks(get_db(), ignore_quiet_hours=bool(data.get("ignore_quiet_hours")))
    return jsonify(ok=True, log=log)


# ---------------------------------------------------------------- calendar downloads

def _ics(filename, events):
    if not events:
        abort(404, "Nothing with a date to add.")
    return Response(calendar_ics.calendar(events), mimetype="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _row(table, row_id):
    row = get_db().execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        abort(404)
    return row


@api_notify.get("/calendar/opportunity/<int:opp_id>.ics")
def opportunity_ics(opp_id):
    return _ics(f"launchpad-opportunity-{opp_id}.ics", calendar_ics.opportunity_events(_row("opportunities", opp_id)))


@api_notify.get("/calendar/task/<int:task_id>.ics")
def task_ics(task_id):
    return _ics(f"launchpad-task-{task_id}.ics", calendar_ics.task_events(_row("tasks", task_id)))


@api_notify.get("/calendar/contact/<int:contact_id>.ics")
def contact_ics(contact_id):
    return _ics(f"launchpad-followup-{contact_id}.ics", calendar_ics.contact_events(_row("contacts", contact_id)))


@api_notify.get("/calendar/week.ics")
def week_ics():
    """Every dated task, deadline, next action, and contact follow-up in one Mon–Sun week."""
    try:
        anchor = date.fromisoformat(request.args.get("start") or config.today_str())
    except ValueError:
        abort(400, "start must be a date like 2026-11-09.")
    lo = anchor - timedelta(days=anchor.weekday())
    hi = lo + timedelta(days=6)
    lo_s, hi_s = lo.isoformat(), hi.isoformat()
    conn = get_db()
    events = []
    for t in conn.execute("SELECT * FROM tasks WHERE status != 'done' AND COALESCE(planned_date, due_date) "
                          "BETWEEN ? AND ?", (lo_s, hi_s)).fetchall():
        events += calendar_ics.task_events(t)
    for o in conn.execute("SELECT * FROM opportunities WHERE stage != 'closed' AND (deadline BETWEEN ? AND ? "
                          "OR next_action_date BETWEEN ? AND ?)", (lo_s, hi_s, lo_s, hi_s)).fetchall():
        events += calendar_ics.opportunity_events(o, within=(lo_s, hi_s))
    for c in conn.execute("SELECT * FROM contacts WHERE follow_up_date BETWEEN ? AND ?", (lo_s, hi_s)).fetchall():
        events += calendar_ics.contact_events(c)
    return _ics(f"launchpad-week-{lo_s}.ics", events)


# ---------------------------------------------------------------- email previews

@api_notify.get("/settings/preview/<kind>")
def preview_email(kind):
    """Show an email in the browser exactly as it would be sent, without sending it."""
    conn = get_db()
    today = config.now().date()
    if kind == "digest":
        return notify.render_email("digest.html", **reminders.digest_data(conn, today))
    if kind == "weekly":
        data = reminders.weekly_plan_data(conn, today)
        return notify.render_email("weekly_plan.html", **data, link=f"/week?start={data['monday'].isoformat()}")
    if kind == "reminders":
        settings = {**settings_store.get_all(conn), "remind_demo": "1"}
        items = reminders.find_reminders(conn, settings, today)
        return notify.render_email("reminders.html", items=items or [
            {"trigger": "deadline", "title": "(Nothing is due right now; this is a sample.)", "body": "", "link": "/"}])
    abort(404)

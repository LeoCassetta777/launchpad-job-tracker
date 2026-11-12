"""The reminder rules. run_checks() runs every 15 minutes (see scheduler.py).

Each rule looks at your data and proposes reminders with a unique "key", like
'deadline:12:2026-11-15:2' (opportunity 12, deadline Nov 15, 2 days before).
notify.deliver() sends only keys it has never seen, so checking every 15 minutes
never sends anything twice.

Rules:
  deadline     an opportunity deadline is 7 / 2 / 0 days away (or the card's own list)
  followup     an opportunity sat in Sent or Waiting with no update for 7 days
  contact      a contact's follow-up date has arrived
  next_action  an opportunity's next-action date has arrived
  digest       weekdays at 8:00 AM: today, overdue, this week's deadlines, follow-ups
  weekly_plan  Sundays at 6:00 PM: a nudge to plan next week

Quiet hours: nothing is sent between 10 PM and 7 AM. Reminders that come due then
wait for the first check after 7 AM.
"""
from datetime import date, timedelta

import json

import config
import constants as C
import notify
import progress
import settings_store

QUIET_START, QUIET_END = 22, 7          # 10 PM to 7 AM
LOOKBACK_DAYS = 14                      # don't nag about dates older than this

MOTIVATION = [
    "Every application is a lottery ticket you actually bought. Buy one today.",
    "One email can change a semester. Send the one you're putting off.",
    "Rejections are proof you're in the arena. Keep swinging.",
    "Small daily reps beat one heroic weekend.",
    "You don't need to feel ready. You need to hit send.",
    "Follow-ups land interviews more often than first emails do. Follow up.",
    "Future you is grateful for whatever you finish before lunch.",
    "Progress, not polish. Ship the draft.",
    "Your network grows one coffee chat at a time.",
    "Pick the scariest task and do ten minutes of it. That's it.",
]


def _opp_name(o):
    return f"{o['company']} · {o['title']}" if o["title"] else o["company"]


def _days_phrase(n):
    return "today" if n == 0 else "tomorrow" if n == 1 else f"in {n} days"


def in_quiet_hours(now):
    return now.hour >= QUIET_START or now.hour < QUIET_END


# ---------------------------------------------------------------- item reminders

def find_reminders(conn, settings, today):
    """All reminders that are due right now (already-sent ones are filtered later by key)."""
    items = []
    demo = "" if settings.get("remind_demo") == "1" else " AND is_seed = 0"
    default_days = [int(d) for d in settings["deadline_days"].split(",") if d.strip() != ""]
    oldest = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    t = today.isoformat()

    # Deadlines
    for o in conn.execute("SELECT * FROM opportunities WHERE stage NOT IN ('closed', 'offer') "
                          f"AND deadline >= ?{demo}", (t,)).fetchall():
        if o["reminders"] == "off":
            continue
        days = [int(d) for d in o["reminders"].split(",")] if o["reminders"] else default_days
        n = (date.fromisoformat(o["deadline"]) - today).days
        if n in days:
            when = _days_phrase(n)
            at = f" at {config.clock(o['deadline_time'])}" if o["deadline_time"] else ""
            items.append({
                "key": f"deadline:{o['id']}:{o['deadline']}:{n}", "trigger": "deadline",
                "title": f"Deadline {when}{at}: {_opp_name(o)}",
                "body": (f"Next action: {o['next_action']}" if o["next_action"] else f"Stage: {C.label(C.STAGES, o['stage'])}"),
                "link": f"/?open=opportunity:{o['id']}",
                "push_text": f"Deadline {when} — open Launchpad", "priority": "high" if n <= 2 else "default",
            })

    # Follow-up nudge: Sent/Waiting with no update for N days
    wait = int(settings["followup_after_days"])
    for o in conn.execute("SELECT * FROM opportunities WHERE stage IN ('sent', 'waiting')"
                          f"{demo}").fetchall():
        last = o["updated_at"][:10]
        idle = (today - date.fromisoformat(last)).days
        if idle >= wait:
            items.append({
                "key": f"followup:{o['id']}:{last}", "trigger": "followup",
                "title": f"No update in {idle} days: {_opp_name(o)}",
                "body": "Time to follow up, or move it to Closed (ghosted) if it's gone quiet for good.",
                "link": f"/?open=opportunity:{o['id']}",
                "push_text": "Time to follow up on something — open Launchpad",
            })

    # Contact follow-up dates
    for c in conn.execute("SELECT * FROM contacts WHERE follow_up_date BETWEEN ? AND ?"
                          f"{demo}", (oldest, t)).fetchall():
        late = (today - date.fromisoformat(c["follow_up_date"])).days
        items.append({
            "key": f"contact:{c['id']}:{c['follow_up_date']}", "trigger": "contact",
            "title": f"Follow up with {c['name']}" + (f" ({c['company']})" if c["company"] else "")
                     + ("" if late == 0 else f", {late} days late"),
            "body": c["notes"][:200] if c["notes"] else "",
            "link": f"/contacts/{c['id']}",
            "push_text": "A contact follow-up is due — open Launchpad",
        })

    # Next-action dates
    for o in conn.execute("SELECT * FROM opportunities WHERE stage != 'closed' AND next_action != '' "
                          f"AND next_action_date BETWEEN ? AND ?{demo}", (oldest, t)).fetchall():
        items.append({
            "key": f"next:{o['id']}:{o['next_action_date']}", "trigger": "next_action",
            "title": f"Next action for {_opp_name(o)}: {o['next_action']}",
            "body": "", "link": f"/?open=opportunity:{o['id']}",
            "push_text": "A next action is due today — open Launchpad",
        })
    return items


# ---------------------------------------------------------------- digest + weekly plan

def digest_data(conn, today, include_demo=True):
    """Everything for the morning digest email (also used by the preview page)."""
    demo = "" if include_demo else " AND t.is_seed = 0"
    demo_o = "" if include_demo else " AND is_seed = 0"
    t = today.isoformat()
    sunday = (today + timedelta(days=6 - today.weekday())).isoformat()
    tasks = [dict(r) for r in conn.execute(
        "SELECT t.*, o.company AS opp_company FROM tasks t LEFT JOIN opportunities o ON o.id = t.opportunity_id "
        f"WHERE t.status != 'done' AND COALESCE(t.planned_date, t.due_date) = ?{demo} "
        "ORDER BY t.start_time IS NULL, t.start_time", (t,)).fetchall()]
    overdue = [dict(r) for r in conn.execute(
        "SELECT t.*, o.company AS opp_company FROM tasks t LEFT JOIN opportunities o ON o.id = t.opportunity_id "
        f"WHERE t.status != 'done' AND (t.due_date < ? OR t.planned_date < ?){demo} "
        "ORDER BY COALESCE(t.due_date, t.planned_date)", (t, t)).fetchall()]
    deadlines = [dict(r) for r in conn.execute(
        "SELECT * FROM opportunities WHERE stage NOT IN ('closed', 'offer') "
        f"AND deadline BETWEEN ? AND ?{demo_o} ORDER BY deadline", (t, sunday)).fetchall()]
    contacts = [dict(r) for r in conn.execute(
        f"SELECT * FROM contacts WHERE follow_up_date <= ?{demo_o} ORDER BY follow_up_date", (t,)).fetchall()]
    for d in deadlines:
        d["when"] = _days_phrase((date.fromisoformat(d["deadline"]) - today).days)
    return {
        "today": today, "tasks": tasks, "overdue": overdue, "deadlines": deadlines, "contacts": contacts,
        "planned_min": sum((x["est_min"] or x["duration_min"] or 0) for x in tasks),
        "motivation": MOTIVATION[today.toordinal() % len(MOTIVATION)],
    }


def weekly_plan_data(conn, today, include_demo=True):
    demo_o = "" if include_demo else " AND is_seed = 0"
    demo_t = "" if include_demo else " AND is_seed = 0"
    monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    sunday = monday + timedelta(days=6)
    lo, hi = monday.isoformat(), sunday.isoformat()
    deadlines = [dict(r) for r in conn.execute(
        f"SELECT * FROM opportunities WHERE stage NOT IN ('closed', 'offer') AND deadline BETWEEN ? AND ?{demo_o} "
        "ORDER BY deadline", (lo, hi)).fetchall()]
    for d in deadlines:
        due = date.fromisoformat(d["deadline"])
        d["day"] = f"{due:%a %b} {due.day}"      # "Fri Nov 13" (no leading zero; works on Windows and Mac)
    unscheduled = conn.execute(f"SELECT COUNT(*) FROM tasks WHERE status != 'done' AND planned_date IS NULL "
                               f"AND due_date IS NULL{demo_t}").fetchone()[0]
    planned = conn.execute(f"SELECT COUNT(*), COALESCE(SUM(COALESCE(est_min, duration_min, 0)), 0) FROM tasks "
                           f"WHERE status != 'done' AND COALESCE(planned_date, due_date) BETWEEN ? AND ?{demo_t}",
                           (lo, hi)).fetchone()
    return {"monday": monday, "sunday": sunday, "deadlines": deadlines, "unscheduled": unscheduled,
            "planned_count": planned[0], "planned_hours": round(planned[1] / 60, 1)}


def _send_digest(conn, settings, today, now):
    key = f"digest:{today.isoformat()}"
    channels = settings_store.channels_for(settings, "digest")
    if not channels:
        return "digest off"
    data = digest_data(conn, today, include_demo=settings.get("remind_demo") == "1")
    count = len(data["tasks"]) + len(data["overdue"]) + len(data["deadlines"]) + len(data["contacts"])
    title = f"Your {now:%A} plan: {len(data['tasks'])} today, {len(data['overdue'])} overdue"
    nid = notify.claim(conn, key, "digest", title, link="/week", channels=channels)
    if not nid:
        return "digest already sent"
    return _send_one(conn, nid, channels, subject=title,
                     html=notify.render_email("digest.html", **data),
                     text=f"{title}\n{config.app_base_url()}/week\n\n{data['motivation']}",
                     push=f"Good morning — {count} things on your plate. Open Launchpad", link="/week")


def _send_weekly_plan(conn, settings, today):
    key = f"weekly_plan:{today.isoformat()}"
    channels = settings_store.channels_for(settings, "weekly_plan")
    if not channels:
        return "weekly plan off"
    data = weekly_plan_data(conn, today, include_demo=settings.get("remind_demo") == "1")
    link = f"/week?start={data['monday'].isoformat()}"
    title = "Plan your week"
    nid = notify.claim(conn, key, "weekly_plan", title, link=link, channels=channels)
    if not nid:
        return "weekly plan already sent"
    return _send_one(conn, nid, channels, subject=f"Plan your week of {data['monday']:%b} {data['monday'].day}",
                     html=notify.render_email("weekly_plan.html", **data, link=link),
                     text=f"Plan your week: {config.app_base_url()}{link}",
                     push="Sunday check-in: plan your week — open Launchpad", link=link)


def _send_one(conn, nid, channels, subject, html, text, push, link):
    results = []
    if "email" in channels:
        try:
            notify.send_email(subject, html, text)
            notify.mark(conn, [nid], "email_sent_at")
            results.append("emailed")
        except notify.NotifyError as e:
            notify.mark(conn, [nid], None, error=str(e))
            results.append(f"email failed: {e}")
    if "push" in channels:
        try:
            notify.send_push(push, click_path=link)
            notify.mark(conn, [nid], "push_sent_at")
            results.append("pushed")
        except notify.NotifyError as e:
            notify.mark(conn, [nid], None, error=str(e))
            results.append(f"push failed: {e}")
    return ", ".join(results)


# ---------------------------------------------------------------- the 15-minute check

def run_checks(conn, now=None, ignore_quiet_hours=False):
    """Find and send whatever is due. Returns a list of log lines."""
    now = now or config.now()
    if in_quiet_hours(now) and not ignore_quiet_hours:
        return [f"{now:%H:%M} quiet hours: nothing sent"]
    settings = settings_store.get_all(conn)
    today = now.date()
    log = [f"{now:%H:%M} reminders: " + notify.deliver(conn, find_reminders(conn, settings, today), settings)]
    if today.weekday() < 5 and 8 <= now.hour < 11:       # weekday mornings, 8-11 AM window
        log.append("digest: " + _send_digest(conn, settings, today, now))
    if today.weekday() == 6 and 18 <= now.hour < 22:     # Sunday evening
        log.append("weekly plan: " + _send_weekly_plan(conn, settings, today))
    if today.weekday() == 4 and 16 <= now.hour < 18:     # Friday 4-6 PM
        log.append("weekly review: " + _weekly_review(conn, settings, today))
    if now.hour >= 20:                                   # evening nudges (8-10 PM; quiet hours start at 10)
        log.append("evening: " + _evening_nudges(conn, settings, today, now))
    return log


# ---------------------------------------------------------------- Phase 5: coach + evening nudges

def _evening_nudges(conn, settings, today, now):
    """8 PM streak-at-risk and 9 PM shutdown nudges. Both are off unless turned on in Settings."""
    items = []
    if settings_store.channels_for(settings, "streak"):
        days, at_risk = progress.streak(conn, today)
        if at_risk:
            items.append({"key": f"streak:{today.isoformat()}", "trigger": "streak",
                          "title": f"Your {days}-day streak ends tonight: finish a task, log an interaction, or move a card forward",
                          "link": "/", "push_text": "Your streak is at risk — open Launchpad"})
    if now.hour >= 21 and settings_store.channels_for(settings, "shutdown"):
        items.append({"key": f"shutdown:{today.isoformat()}", "trigger": "shutdown",
                      "title": "Time for your 2-minute end-of-day shutdown", "link": "/shutdown",
                      "push_text": "2-minute shutdown time — open Launchpad"})
    return notify.deliver(conn, items, settings) if items else "nothing due"


def _weekly_review(conn, settings, today):
    """Friday afternoon: have the coach write this week's review (once), then send it."""
    import ai_budget
    import coach
    monday = coach.week_start_for(today)
    key = f"weekly_review:{monday.isoformat()}"
    if conn.execute("SELECT 1 FROM notifications WHERE key IN (?, ?)", (key, key + ":skipped")).fetchone():
        return "already done"
    review = conn.execute("SELECT * FROM reviews WHERE week_start = ?", (monday.isoformat(),)).fetchone()
    if review is None:
        try:
            coach.generate(conn)
        except ai_budget.BudgetError:
            notify.claim(conn, key + ":skipped", "weekly_review",
                         "Weekly review skipped: your AI spending cap is reached. Open Weekly review to run it anyway.",
                         link="/review", channels=[])
            return "skipped (AI cap reached)"
        review = conn.execute("SELECT * FROM reviews WHERE week_start = ?", (monday.isoformat(),)).fetchone()
    channels = settings_store.channels_for(settings, "weekly_review")
    nid = notify.claim(conn, key, "weekly_review", "Your weekly review is ready", link="/review", channels=channels)
    if not nid or not channels:
        return "generated"
    data = json.loads(review["data"])
    return _send_one(conn, nid, channels, subject="Your weekly review",
                     html=notify.render_email("weekly_review.html", coach=data["coach"], monday=monday),
                     text=data["coach"]["headline"] + f"\n\nRead it and add your notes: {config.app_base_url()}/review",
                     push="Your weekly review is ready — open Launchpad", link="/review")

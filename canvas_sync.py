"""Canvas sync: your assignments become tasks, and course announcements reach the 🔔 bell.

It reads two kinds of private links that Canvas gives every student, with no access
token and no admin approval:

  * the Calendar Feed (Canvas → Calendar → "Calendar Feed" at the bottom right), an
    .ics link with every assignment due date and course event across your courses;
  * each course's Announcements feed (a course → Announcements → the "RSS Feed" button
    at the top right), an Atom link per course.

Both links are like passwords: anyone with them can read that information. They're
saved in the Mac's database, used only here, and never sent back to the browser.

What it does every 2 hours, 7 AM to 9 PM:
  * Each assignment due in the next 45 days (Settings: canvas_days_ahead) becomes a task
    due that day, once. If you delete the task, it stays deleted. If Canvas moves the
    due date and the task isn't done, the task's due date moves too.
  * Each NEW announcement (posted in the last 3 days) is sent the way Settings says
    ("New Canvas announcement"), and all of them are listed on the School page.

Canvas data that needs a login (grades, submissions, discussions) isn't in these feeds.
"""
import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlparse

import config
import fetching
import settings_store
from db import log_activity

NEW_ANNOUNCEMENT_DAYS = 3        # only announcements this recent ping you (older ones are just listed)
ATOM = {"a": "http://www.w3.org/2005/Atom"}


# ---------------------------------------------------------------- checking the links you paste

def clean_feed_url(url, kind):
    """Tidy and check a pasted Canvas feed link. kind: 'calendar' or 'announcements'."""
    url = (url or "").strip()
    if url.startswith("webcal://"):              # Canvas sometimes shows calendar links as webcal://
        url = "https://" + url[len("webcal://"):]
    parts = urlparse(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("Paste the whole link, starting with https://")
    if "/feeds/" not in parts.path:
        where = ("Calendar → Calendar Feed (bottom right)" if kind == "calendar"
                 else "the course's Announcements page → RSS Feed (top right)")
        raise ValueError(f"That isn't a Canvas feed link (those contain /feeds/). Copy it from {where}.")
    if kind == "calendar" and not parts.path.endswith(".ics"):
        raise ValueError("The calendar link should end in .ics (Canvas → Calendar → Calendar Feed).")
    return url


def masked(url):
    """'https://school.instructure.com/feeds/calendars/user_abc123.ics' -> 'school.instructure.com …123.ics'"""
    parts = urlparse(url)
    return f"{parts.hostname} …{parts.path[-8:]}"


# ---------------------------------------------------------------- reading the calendar (.ics)

def _ics_unescape(value):
    return (value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
                 .replace("\\;", ";").replace("\\\\", "\\"))


def parse_ics(text):
    """The VEVENTs in an .ics file, each as {PROPERTY: (value, {param: value})}."""
    text = re.sub(r"\r?\n[ \t]", "", text)        # undo line folding (long lines continue with a space)
    events, current = [], None
    for line in text.splitlines():
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
        elif current is not None and ":" in line:
            head, value = line.split(":", 1)
            name, *params = head.split(";")
            current[name.upper()] = (_ics_unescape(value), dict(p.split("=", 1) for p in params if "=" in p))
    return events


def ics_time(value, params):
    """An .ics date/time -> (Eastern 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD', all_day)."""
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return date(int(value[:4]), int(value[4:6]), int(value[6:8])).isoformat(), True
    stamp = datetime.strptime(value.rstrip("Z")[:15], "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        stamp = stamp.replace(tzinfo=timezone.utc)
    else:
        try:
            stamp = stamp.replace(tzinfo=ZoneInfo(params["TZID"].strip('"')) if params.get("TZID") else config.TZ)
        except (ZoneInfoNotFoundError, ValueError):
            stamp = stamp.replace(tzinfo=config.TZ)
    return stamp.astimezone(config.TZ).strftime("%Y-%m-%d %H:%M"), False


def _split_course(summary):
    """'Essay 1 [ENT 501 Fall 2026]' -> ('Essay 1', 'ENT 501 Fall 2026')"""
    match = re.fullmatch(r"\s*(.*?)\s*\[([^\]]+)\]\s*", summary or "")
    return (match.group(1), match.group(2)) if match else ((summary or "").strip(), "")


def _upsert(conn, item):
    """Insert or refresh one Canvas item (by Canvas's uid). Returns the stored row."""
    now = config.now_str()
    conn.execute(
        """INSERT INTO canvas_items (uid, kind, course, title, url, due_at, all_day, posted_at, body, created_at, updated_at)
           VALUES (:uid, :kind, :course, :title, :url, :due_at, :all_day, :posted_at, :body, :now, :now)
           ON CONFLICT(uid) DO UPDATE SET kind = excluded.kind, course = excluded.course, title = excluded.title,
               url = excluded.url, due_at = excluded.due_at, all_day = excluded.all_day,
               posted_at = excluded.posted_at, body = excluded.body, updated_at = excluded.updated_at""",
        {"due_at": None, "all_day": 0, "posted_at": None, "body": "", "url": "", "course": "", **item, "now": now})
    return conn.execute("SELECT * FROM canvas_items WHERE uid = ?", (item["uid"],)).fetchone()


def _seen(conn, key):
    return conn.execute("SELECT 1 FROM sync_seen WHERE key = ?", (key,)).fetchone() is not None


def _mark_seen(conn, key):
    conn.execute("INSERT OR IGNORE INTO sync_seen (key, created_at) VALUES (?, ?)", (key, config.now_str()))


def _task_for(conn, row, due_day):
    """Make (or update) the task for one assignment. Returns 'created', 'moved', or None."""
    if row["task_id"]:
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (row["task_id"],)).fetchone()
        if task and task["status"] != "done" and task["due_date"] != due_day:
            conn.execute("UPDATE tasks SET due_date = ?, updated_at = ? WHERE id = ?", (due_day, config.now_str(), task["id"]))
            log_activity(conn, "task", task["id"], "updated", f"Canvas moved the due date of {task['title']} to {due_day}")
            return "moved"
        return None
    key = f"canvas_task:{row['uid']}"
    if _seen(conn, key):            # made once before and you deleted it: leave it gone
        return None
    due_time = row["due_at"][11:] if not row["all_day"] and len(row["due_at"] or "") > 10 else ""
    notes = "\n".join(filter(None, [
        f"From Canvas{': ' + row['course'] if row['course'] else ''}",
        f"Due {due_day}{' at ' + config.clock(due_time) if due_time else ''} (Eastern)",
        row["url"]]))
    title = f"{row['title']} · {row['course']}" if row["course"] else row["title"]
    now = config.now_str()
    cur = conn.execute(
        "INSERT INTO tasks (title, due_date, importance, notes, created_at, updated_at) VALUES (?, ?, 'high', ?, ?, ?)",
        (title[:300], due_day, notes, now, now))
    conn.execute("UPDATE canvas_items SET task_id = ? WHERE id = ?", (cur.lastrowid, row["id"]))
    log_activity(conn, "task", cur.lastrowid, "created", f"Added Canvas assignment: {title[:200]}")
    _mark_seen(conn, key)
    return "created"


def sync_calendar(conn, url, days_ahead):
    """Read the calendar feed. Returns a log line."""
    events = parse_ics(fetching.get(url, accept="text/calendar").decode("utf-8", errors="replace"))
    today = config.now().date()
    horizon = today + timedelta(days=days_ahead)
    created = moved = assignments = 0
    for ev in events:
        uid = ev.get("UID", ("", {}))[0].strip()
        if not uid or "DTSTART" not in ev:
            continue
        when, all_day = ics_time(*ev["DTSTART"])
        title, course = _split_course(ev.get("SUMMARY", ("", {}))[0])
        url_value = ev.get("URL", ("", {}))[0].strip()
        row = _upsert(conn, {
            "uid": uid, "kind": "assignment" if "assignment" in uid.lower() else "event",
            "course": course[:200], "title": title[:300] or "(untitled)",
            "url": url_value if fetching.is_web_link(url_value) else "",
            "due_at": when, "all_day": int(all_day),
            "body": fetching.html_to_text(ev.get("DESCRIPTION", ("", {}))[0])[:5000]})
        if row["kind"] != "assignment":
            continue
        assignments += 1
        due_day = when[:10]
        if today.isoformat() <= due_day <= horizon.isoformat():
            result = _task_for(conn, row, due_day)
            created += result == "created"
            moved += result == "moved"
    conn.commit()
    return (f"Calendar: {len(events)} items, {assignments} assignments; "
            f"{created} new task{'s' if created != 1 else ''}, {moved} due date{'s' if moved != 1 else ''} moved")


# ---------------------------------------------------------------- reading announcements (Atom)

def _atom_time(text):
    try:
        stamp = datetime.fromisoformat((text or "").strip().replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(config.TZ)
    except ValueError:
        return None


def sync_announcements(conn, url):
    """Read one course's announcement feed. Returns (log line, [notices for new ones])."""
    try:
        root = ET.fromstring(fetching.get(url, accept="application/atom+xml"))
    except ET.ParseError:
        raise fetching.FetchError("That announcement feed didn't come back as a feed. Copy the link again from Canvas.")
    course = (root.findtext("a:title", "", ATOM) or "").strip()
    course = re.sub(r"\s*(:\s*)?Announcements?( Feed)?\s*$", "", course, flags=re.I) or "Course"
    cutoff = config.now() - timedelta(days=NEW_ANNOUNCEMENT_DAYS)
    notices, total = [], 0
    for entry in root.findall("a:entry", ATOM):
        uid = (entry.findtext("a:id", "", ATOM) or "").strip()
        if not uid:
            continue
        total += 1
        link_el = entry.find("a:link", ATOM)
        link = link_el.get("href", "") if link_el is not None else ""
        posted = _atom_time(entry.findtext("a:published", "", ATOM) or entry.findtext("a:updated", "", ATOM))
        title = (entry.findtext("a:title", "", ATOM) or "(no title)").strip()[:300]
        body = fetching.html_to_text(entry.findtext("a:content", "", ATOM) or "")[:20000]
        _upsert(conn, {"uid": f"announcement:{uid}", "kind": "announcement", "course": course[:200], "title": title,
                       "url": link if fetching.is_web_link(link) else "", "body": body,
                       "posted_at": posted.strftime("%Y-%m-%d %H:%M") if posted else None})
        key = f"canvas_ann:{uid}"
        if not _seen(conn, key):
            _mark_seen(conn, key)
            if posted and posted >= cutoff:
                notices.append({"key": key, "trigger": "canvas", "title": f"📣 {course}: {title}",
                                "body": body[:400], "link": "/school",
                                "push_text": "New course announcement — open Launchpad"})
    conn.commit()
    return f"{course}: {total} announcement{'s' if total != 1 else ''}, {len(notices)} new", notices


# ---------------------------------------------------------------- the whole run

def run(conn, notify_me=True):
    """Sync the calendar and every announcement feed. Returns {"log": [lines], "configured": bool}."""
    import discover          # for announce() (bell + email/push the way Settings says)
    settings = settings_store.get_all(conn)
    log, notices = [], []
    cal = settings["canvas_calendar_url"].strip()
    feeds = [f for f in settings["canvas_announcement_feeds"].splitlines() if f.strip()]
    try:
        days_ahead = max(1, min(180, int(settings["canvas_days_ahead"])))
    except ValueError:
        days_ahead = 45
    if cal:
        try:
            log.append(sync_calendar(conn, cal, days_ahead))
        except fetching.FetchError as e:
            log.append(f"⚠️ Calendar: {e}")
    for feed in feeds:
        try:
            line, found = sync_announcements(conn, feed.strip())
            log.append(line)
            notices += found
        except fetching.FetchError as e:
            log.append(f"⚠️ Announcements ({masked(feed)}): {e}")
    if not cal and not feeds:
        log.append("Not connected yet: paste your Canvas links on the School page.")
    if notify_me:
        for notice in notices[:5]:                  # more than 5 at once = probably a first sync; don't spam
            log.append("notify: " + discover.announce(conn, settings, notice))
    settings_store.set_many(conn, {"canvas_last_run": json.dumps({"at": config.now_str(), "log": log})})
    return {"log": log, "configured": bool(cal or feeds)}

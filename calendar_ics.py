"""Calendar files (.ics) for "Add to calendar" and "Export this week".

.ics is the standard calendar format Outlook, Google Calendar, and Apple Calendar
all import. Rules followed here:
  * Timed events (interviews, calls, meetings) carry TZID=America/New_York plus a
    VTIMEZONE block describing Eastern daylight-saving rules, so Outlook places them
    at the right hour no matter what time zone the computer is set to.
  * Deadlines are all-day events (DTSTART;VALUE=DATE), which have no time zone at all.
  * Each event has a stable UID, so importing an updated file updates the event
    instead of duplicating it.
  * Lines end in CRLF and long lines are "folded" at 75 bytes, as the standard requires.
"""
from datetime import date, datetime, timedelta, timezone

import config

VTIMEZONE = [
    "BEGIN:VTIMEZONE",
    "TZID:America/New_York",
    "BEGIN:DAYLIGHT",
    "TZOFFSETFROM:-0500", "TZOFFSETTO:-0400", "TZNAME:EDT",
    "DTSTART:19700308T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
    "END:DAYLIGHT",
    "BEGIN:STANDARD",
    "TZOFFSETFROM:-0400", "TZOFFSETTO:-0500", "TZNAME:EST",
    "DTSTART:19701101T020000", "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
    "END:STANDARD",
    "END:VTIMEZONE",
]


def _escape(text):
    """Commas, semicolons, backslashes, and newlines must be escaped in .ics text."""
    return (str(text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line):
    """Split lines longer than 75 bytes; continuation lines start with a space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return [line]
    parts, current = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(current) + len(b) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += b
    parts.append(current.decode("utf-8"))
    return [parts[0]] + [" " + p for p in parts[1:]]


def event(uid, summary, day, start_time=None, minutes=None, description="", url=""):
    """One VEVENT. With start_time ("HH:MM") it's a timed Eastern event; otherwise all-day."""
    d = date.fromisoformat(day)
    lines = ["BEGIN:VEVENT", f"UID:{uid}@launchpad",
             f"DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
             f"SUMMARY:{_escape(summary)}"]
    if start_time:
        start = datetime.combine(d, datetime.strptime(start_time, "%H:%M").time())
        end = start + timedelta(minutes=minutes or 30)
        lines += [f"DTSTART;TZID=America/New_York:{start:%Y%m%dT%H%M%S}",
                  f"DTEND;TZID=America/New_York:{end:%Y%m%dT%H%M%S}"]
    else:
        lines += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
                  "X-MICROSOFT-CDO-ALLDAYEVENT:TRUE", "TRANSP:TRANSPARENT"]   # all-day: don't block the day
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    if url:
        lines.append(f"URL:{url}")
    lines.append("END:VEVENT")
    return lines


def calendar(events):
    """Wrap events into a complete .ics file (as text)."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Launchpad//Job search planner//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", *VTIMEZONE]
    for ev in events:
        lines += ev
    lines.append("END:VCALENDAR")
    out = []
    for line in lines:
        out += _fold(line)
    return "\r\n".join(out) + "\r\n"


# ---------------------------------------------------------------- events for Launchpad records

def _name(o):
    return f"{o['company']} · {o['title']}" if o["title"] else o["company"]


def opportunity_events(o, within=None):
    """Deadline and next-action events. `within=(first_day, last_day)` keeps only dates in that range."""
    base = config.app_base_url()
    url = f"{base}/?open=opportunity:{o['id']}"

    def wanted(day):
        return bool(day) and (within is None or within[0] <= day <= within[1])

    events = []
    if wanted(o["deadline"]):
        due = f" (due {config.clock(o['deadline_time'])})" if o["deadline_time"] else ""
        events.append(event(f"opp-{o['id']}-deadline", f"📅 Deadline{due}: {_name(o)}", o["deadline"],
                            description=f"{o['next_action'] or ''}\n{url}".strip(), url=url))
    if wanted(o["next_action_date"]) and o["next_action"]:
        events.append(event(f"opp-{o['id']}-next", f"➡️ {o['next_action']} ({o['company']})", o["next_action_date"],
                            description=url, url=url))
    return events


def task_events(t):
    day = t["planned_date"] or t["due_date"]
    if not day:
        return []
    url = f"{config.app_base_url()}/?open=task:{t['id']}"
    summary = ("🕑 " if t["start_time"] else "✅ ") + t["title"]
    return [event(f"task-{t['id']}", summary, day, t["start_time"], t["duration_min"] or t["est_min"],
                  description=f"{t['notes'] or ''}\n{url}".strip(), url=url)]


def contact_events(c):
    if not c["follow_up_date"]:
        return []
    url = f"{config.app_base_url()}/contacts/{c['id']}"
    who = c["name"] + (f" ({c['company']})" if c["company"] else "")
    return [event(f"contact-{c['id']}-followup", f"👤 Follow up with {who}", c["follow_up_date"],
                  description=url, url=url)]

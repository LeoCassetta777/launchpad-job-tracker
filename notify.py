"""Sending reminders: Gmail email, ntfy phone push, and the notification log.

    send_email(subject, html, text)    one email from your Gmail to your school inbox
    send_push(message, ...)            one phone push through ntfy
    deliver(conn, items, settings)     log new reminders once each, then send them
                                       (grouped: one email and one push per check)

Push messages are deliberately vague ("Deadline in 2 days — open Launchpad"):
anyone who learns the ntfy topic name could read them. Details go in email and the app.
"""
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr

from flask import render_template

import config
import settings_store

SUBJECT_PREFIX = "[Launchpad]"   # for your inbox rule


class NotifyError(Exception):
    pass


# ---------------------------------------------------------------- email

def send_email(subject, html, text):
    """Send one email through Gmail's mail server using the app password."""
    if not config.email_ready():
        raise NotifyError("Email isn't set up: add GMAIL_ADDRESS, GMAIL_APP_PASSWORD, and NOTIFY_EMAIL.")
    msg = EmailMessage()
    msg["Subject"] = f"{SUBJECT_PREFIX} {subject}"
    msg["From"] = formataddr(("Launchpad", config.GMAIL_ADDRESS))
    msg["To"] = config.NOTIFY_EMAIL
    msg.set_content(text)                       # plain-text version for any mail app
    msg.add_alternative(html, subtype="html")   # the styled version
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise NotifyError("Gmail rejected the login. Check GMAIL_ADDRESS and the app password in .env.")
    except (smtplib.SMTPException, OSError) as e:
        raise NotifyError(f"Couldn't send email: {e}")


def render_email(template, **context):
    """Render one of templates/email/*.html. Needs a Flask app context."""
    context.setdefault("base_url", config.app_base_url())
    return render_template(f"email/{template}", **context)


# ---------------------------------------------------------------- push

def send_push(message, title="Launchpad", priority="default", tags="rocket", click_path="/"):
    """Send one phone notification through ntfy. Keep `message` free of personal details."""
    if not config.push_ready():
        raise NotifyError("Push isn't set up: NTFY_TOPIC is empty in .env.")
    req = urllib.request.Request(
        f"{config.NTFY_SERVER}/{config.NTFY_TOPIC}",
        data=message.encode("utf-8"),
        method="POST",
        headers={"Title": title, "Priority": priority, "Tags": tags,
                 "Click": config.app_base_url() + click_path},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status >= 300:
                raise NotifyError(f"ntfy answered {resp.status}")
    except OSError as e:
        raise NotifyError(f"Couldn't send push: {e}")


# ---------------------------------------------------------------- logging + delivery

def claim(conn, key, trigger, title, body="", link="", channels=()):
    """Record a reminder. Returns its id, or None if this exact reminder was already handled.

    The UNIQUE key makes this safe even if two copies of the app run at once:
    only one INSERT can win, so nothing is ever sent twice.
    """
    cur = conn.execute(
        "INSERT OR IGNORE INTO notifications (key, trigger, title, body, link, channels, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (key, trigger, title, body, link, ",".join(channels), config.now_str()))
    conn.commit()
    return cur.lastrowid if cur.rowcount else None


def mark(conn, ids, column, error=None):
    for nid in ids:
        if error:
            conn.execute("UPDATE notifications SET error = COALESCE(error || ' | ', '') || ? WHERE id = ?", (error, nid))
        else:
            conn.execute(f"UPDATE notifications SET {column} = ? WHERE id = ?", (config.now_str(), nid))
    conn.commit()


_NOUNS = {"deadline": ("deadline", "deadlines"), "followup": ("follow-up nudge", "follow-up nudges"),
          "contact": ("contact to follow up", "contacts to follow up"),
          "next_action": ("next action", "next actions")}


def _summary_subject(items):
    """'4 reminders: 2 deadlines, 1 next action, 1 contact to follow up'"""
    counts = {}
    for i in items:
        counts[i["trigger"]] = counts.get(i["trigger"], 0) + 1
    parts = [f"{n} {_NOUNS[t][0] if n == 1 else _NOUNS[t][1]}" for t, n in counts.items() if t in _NOUNS]
    return f"{len(items)} reminders: " + ", ".join(parts)


def deliver(conn, items, settings):
    """Send a batch of reminders found in one check.

    Each item: {key, trigger, title, body, link, push_text, priority}
    Items already sent before (same key) are skipped. New ones are grouped into
    ONE email and ONE push, so a busy morning doesn't mean ten notifications.
    Returns a short summary for the log.
    """
    fresh = []
    for item in items:
        channels = settings_store.channels_for(settings, item["trigger"])
        if not channels:
            continue
        nid = claim(conn, item["key"], item["trigger"], item["title"], item.get("body", ""),
                    item.get("link", ""), channels)
        if nid:
            fresh.append({**item, "id": nid, "channels": channels})
    if not fresh:
        return "nothing new"

    summary = []
    by_email = [i for i in fresh if "email" in i["channels"]]
    if by_email:
        ids = [i["id"] for i in by_email]
        subject = by_email[0]["title"] if len(by_email) == 1 else _summary_subject(by_email)
        text = "\n\n".join(f"{i['title']}\n{i.get('body', '')}\n{config.app_base_url()}{i.get('link', '')}" for i in by_email)
        try:
            send_email(subject, render_email("reminders.html", items=by_email), text)
            mark(conn, ids, "email_sent_at")
            summary.append(f"emailed {len(by_email)}")
        except NotifyError as e:
            mark(conn, ids, None, error=str(e))
            summary.append(f"email failed: {e}")

    by_push = [i for i in fresh if "push" in i["channels"]]
    if by_push:
        ids = [i["id"] for i in by_push]
        message = by_push[0]["push_text"] if len(by_push) == 1 else f"{len(by_push)} reminders — open Launchpad"
        priority = "high" if any(i.get("priority") == "high" for i in by_push) else "default"
        try:
            send_push(message, priority=priority, click_path=by_push[0].get("link") or "/")
            mark(conn, ids, "push_sent_at")
            summary.append(f"pushed {len(by_push)}")
        except NotifyError as e:
            mark(conn, ids, None, error=str(e))
            summary.append(f"push failed: {e}")
    return "; ".join(summary)

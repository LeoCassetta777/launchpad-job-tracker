"""App settings you can change on the Settings page, stored in the database.

Secrets (passwords, API key, ntfy topic) are NOT here; they live in .env.
The two email addresses live in .env too (see save_env_value) so they're with
the rest of the email setup.
"""
from dotenv import set_key

import config

# Which way each reminder reaches you: "email", "push", "both", or "off".
TRIGGERS = [
    ("deadline", "Deadline coming up", "both"),
    ("followup", "Nudge: no reply after a week (Sent / Waiting)", "email"),
    ("contact", "Contact follow-up date reached", "both"),
    ("next_action", "Next-action date reached", "push"),
    ("digest", "Weekday morning digest (8:00 AM)", "email"),
    ("weekly_plan", "Sunday 6 PM “plan your week”", "email"),
    ("weekly_review", "Friday 4 PM weekly review from your coach", "email"),
    ("streak", "8 PM nudge when your streak is at risk", "off"),
    ("shutdown", "9 PM nudge to do your end-of-day shutdown", "off"),
    ("discover", "New postings found for you (Discover, every morning at 7)", "push"),
    ("canvas", "New Canvas announcement", "push"),
]
CHANNELS = ["email", "push", "both", "off"]

DEFAULTS = {
    **{f"channel.{key}": default for key, _label, default in TRIGGERS},
    "deadline_days": "7,2,0",      # days before a deadline; 0 = the morning of
    "followup_after_days": "7",    # nudge when Sent/Waiting has had no update this long
    "remind_demo": "0",            # 1 = include fake demo rows in reminders (for testing)
    "ai_monthly_cap": "3.00",      # dollars per calendar month (Eastern); see ai_budget.py
    "ai_cap_override_month": "",   # "2026-11" = ignore the cap for the rest of that month
    "skills_profile": "",          # your skills/experience/goals in plain text (used by fit checks)
    "weekly_goals": "",            # JSON list of {kind, target}; blank = progress.DEFAULT_GOALS
    "matrix_include_medium": "0",  # 1 = Medium importance counts as "important" in the Eisenhower view
    "focus_work_min": "25",        # focus timer (Pomodoro) lengths
    "focus_break_min": "5",
    # Discover (discover.py)
    "discover_senders": "80000hours.org",   # job-alert emails from these senders are read (one per line)
    "discover_boards": "",                   # career pages to watch, e.g. 'greenhouse:anthropic' (one per line)
    "discover_keywords": "",                 # career-page titles must contain one of these (blank = all)
    "discover_locations": "",                # career-page locations must contain one of these (blank = all)
    "discover_last_run": "",                 # JSON: when it last ran and what happened
    "discover_sweep": "1",                   # 1 = web sweep of company hiring pages Mon/Wed/Fri 7:20 AM (about 8-10 cents each)
    "discover_sweep_last": "",
    # Canvas (canvas_sync.py). The feed links are private: they are never sent back to the browser.
    "canvas_calendar_url": "",
    "canvas_announcement_feeds": "",         # one feed link per line
    "canvas_days_ahead": "45",               # make tasks for assignments due within this many days
    "canvas_last_run": "",
}


# Settings that are private links: never sent to the browser (see public()).
PRIVATE_KEYS = {"canvas_calendar_url", "canvas_announcement_feeds"}


def public(settings):
    """The settings minus the private ones, safe to send to the browser."""
    return {k: v for k, v in settings.items() if k not in PRIVATE_KEYS}


def get_all(conn):
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {**DEFAULTS, **{r["key"]: r["value"] for r in rows}}


def set_many(conn, values):
    for key, value in values.items():
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))
    conn.commit()


def channels_for(settings, trigger):
    """'both' -> ['email', 'push'], 'off' -> []"""
    choice = settings.get(f"channel.{trigger}", "off")
    return {"email": ["email"], "push": ["push"], "both": ["email", "push"]}.get(choice, [])


def save_env_value(name, value):
    """Write a non-secret setting (an email address) into .env and use it right away."""
    set_key(str(config.ENV_PATH), name, value, quote_mode="never")
    setattr(config, name, value)

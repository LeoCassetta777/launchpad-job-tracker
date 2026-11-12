"""The fixed choice lists the app uses (stages, urgency levels, and so on).

This is the single source of truth: the server validates against these lists,
and the same lists are handed to the browser (see app.py) so the dropdowns,
colors, and icons always match. To rename a stage or change an icon, edit it here.

Each entry is (key, label, icon). The key is what gets stored in the database.
"""

OPPORTUNITY_TYPES = [
    ("job", "Job posting", "💼"),
    ("internship", "Internship", "🎓"),
    ("fellowship", "Fellowship", "🏅"),
    ("outreach", "Outreach lead", "✉️"),
]

SOURCES = [
    ("linkedin", "LinkedIn", ""),
    ("12twenty", "12Twenty", ""),
    ("referral", "Referral", ""),
    ("cold_outreach", "Cold outreach", ""),
    ("company_site", "Company site", ""),
    ("job_board", "Job board", ""),       # e.g. 80,000 Hours, Idealist (Discover uses this)
    ("other", "Other", ""),
]

# One stage list shared by job postings AND outreach.
STAGES = [
    ("interested", "Interested", "💡"),
    ("preparing", "Preparing", "🛠️"),
    ("sent", "Sent", "📨"),          # applied or emailed
    ("waiting", "Waiting", "⏳"),     # waiting / following up
    ("talking", "Talking", "💬"),     # reply, call, interview
    ("offer", "Offer", "🎉"),
    ("closed", "Closed", "📦"),
]

CLOSE_REASONS = [
    ("accepted", "Accepted", "✅"),
    ("declined", "Declined", "🙅"),
    ("rejected", "Rejected", "🚫"),
    ("ghosted", "Ghosted", "👻"),
    ("withdrew", "Withdrew", "↩️"),
    ("not_a_fit", "Not a fit", "🧩"),
]

# Urgency = how soon it needs attention. Color AND icon, never color alone.
URGENCY = [
    ("chill", "Chill", "🌿"),
    ("soon", "Soon", "⏰"),
    ("pressing", "Pressing", "⚡"),
    ("on_fire", "On fire", "🔥"),
]

# Importance = how much it matters. Separate from urgency (Eisenhower view in Phase 5).
IMPORTANCE = [
    ("low", "Low", "★"),
    ("medium", "Medium", "★★"),
    ("high", "High", "★★★"),
]

TASK_STATUS = [
    ("todo", "To do", "⬜"),
    ("doing", "Doing", "🔄"),
    ("done", "Done", "✅"),
]

ENERGY = [
    ("low", "Low energy", "🔋"),
    ("med", "Medium energy", "🔋🔋"),
    ("high", "High energy", "🔋🔋🔋"),
]

# Repeating tasks: when you finish one, the next copy is created automatically.
REPEAT = [
    ("none", "Doesn't repeat", ""),
    ("daily", "Every day", "🔁"),
    ("weekdays", "Every weekday", "🔁"),
    ("weekly", "Every week", "🔁"),
]

INTERACTION_KINDS = [
    ("emailed", "I emailed", "📤"),
    ("replied", "They replied", "📥"),
    ("call", "Call", "📞"),
    ("coffee", "Coffee chat", "☕"),
    ("event", "Met at event", "🎤"),
    ("linkedin", "LinkedIn message", "💬"),
    ("other", "Other", "📝"),
]

# Phase 4: documents and interview questions
DOCUMENT_KINDS = [
    ("resume", "Resume", "📄"),
    ("cover_letter", "Cover letter", "✉️"),
    ("other", "Other", "📎"),
]

QUESTION_KINDS = [
    ("asked", "They asked me", "🎤"),
    ("likely", "Likely (AI)", "🔮"),
    ("to_ask", "I'll ask them", "🙋"),
    ("bank", "Practice", "📚"),
]

QUESTION_TAGS = [
    ("behavioral", "Behavioral", "🧭"),
    ("technical", "Technical", "🛠️"),
    ("about_me", "About me", "🙂"),
    ("about_ai", "About AI", "🤖"),
    ("company", "About the company", "🏢"),
    ("situational", "Situational", "🎲"),
    ("logistics", "Logistics", "📅"),
]

# A day with more planned work than this shows as overloaded on This Week.
DAILY_CAPACITY_HOURS = 6


def keys(choices):
    """Just the stored keys, e.g. keys(URGENCY) -> ['chill', 'soon', 'pressing', 'on_fire']."""
    return [c[0] for c in choices]


def label(choices, key):
    """Human label for a key, e.g. label(STAGES, 'sent') -> 'Sent'."""
    for k, lbl, _icon in choices:
        if k == key:
            return lbl
    return key or ""


def as_dict():
    """Everything above in a JSON-friendly shape for the browser."""
    def pack(choices):
        return [{"key": k, "label": l, "icon": i} for k, l, i in choices]

    return {
        "opportunity_types": pack(OPPORTUNITY_TYPES),
        "sources": pack(SOURCES),
        "stages": pack(STAGES),
        "close_reasons": pack(CLOSE_REASONS),
        "urgency": pack(URGENCY),
        "importance": pack(IMPORTANCE),
        "task_status": pack(TASK_STATUS),
        "energy": pack(ENERGY),
        "repeat": pack(REPEAT),
        "interaction_kinds": pack(INTERACTION_KINDS),
        "document_kinds": pack(DOCUMENT_KINDS),
        "question_kinds": pack(QUESTION_KINDS),
        "question_tags": pack(QUESTION_TAGS),
        "daily_capacity_hours": DAILY_CAPACITY_HOURS,
    }

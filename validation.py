"""Checks every value the browser sends before it reaches the database.

Each table has a FIELDS dict: field name -> a checker function. A checker takes
the raw value and returns a clean value, or raises ValueError with a message
the user can read. Unknown fields are rejected, so nothing unexpected can be
written. Phase 2 reuses these same rules to check what the AI returns.
"""
import re
from datetime import date

import constants as C


class ValidationError(ValueError):
    pass


# ---------- building blocks ----------

def text(max_len=500, required=False):
    def check(value):
        if value is None:
            value = ""
        if not isinstance(value, str):
            value = str(value)
        value = value.strip()
        if required and not value:
            raise ValueError("is required")
        if len(value) > max_len:
            raise ValueError(f"must be {max_len} characters or fewer")
        return value
    check.required = required   # clean() uses this to spot missing required fields
    return check


def choice(choices, nullable=False):
    allowed = C.keys(choices)

    def check(value):
        if nullable and value in (None, ""):
            return None
        if value not in allowed:
            raise ValueError(f"must be one of: {', '.join(allowed)}")
        return value
    return check


def iso_date(value):
    """'YYYY-MM-DD' or empty (stored as NULL)."""
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("must be a date like 2026-11-15")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError("must be a date like 2026-11-15")


def hhmm(value):
    """'HH:MM' 24-hour time or empty."""
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("must be a time like 14:30")
    return value


def integer(min_val=None, max_val=None):
    def check(value):
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            raise ValueError("must be a whole number")
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValueError("must be a whole number")
        if min_val is not None and value < min_val:
            raise ValueError(f"must be at least {min_val}")
        if max_val is not None and value > max_val:
            raise ValueError(f"must be at most {max_val}")
        return value
    return check


def url(value):
    """A web link. Only http/https, so a 'javascript:' link can never be saved."""
    value = text(1000)(value)
    if value and not re.match(r"^https?://", value, re.IGNORECASE):
        if "." in value and " " not in value:
            value = "https://" + value          # "acme.com/jobs" -> "https://acme.com/jobs"
        else:
            raise ValueError("must be a web address starting with http:// or https://")
    return value


def email(value):
    value = text(254)(value)
    if value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("doesn't look like an email address")
    return value


def tags(value):
    """Accepts 'AI, Security' or ['AI', 'Security']; stores 'ai,security'."""
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        raise ValueError("must be a comma-separated list")
    clean = []
    for t in value:
        t = str(t).strip().lower()
        if t and t not in clean:
            clean.append(t[:40])
    return ",".join(clean[:20])


def reminder_days(value):
    """'' (use the default), 'off', or days before the deadline like '7,2,0'."""
    value = text(50)(value).lower().replace(" ", "")
    if value in ("", "off"):
        return value
    try:
        days = sorted({int(d) for d in value.split(",") if d != ""}, reverse=True)
    except ValueError:
        raise ValueError("must be 'off' or days before the deadline, like 7,2,0")
    if not days or any(d < 0 or d > 60 for d in days):
        raise ValueError("days must be between 0 and 60")
    return ",".join(str(d) for d in days)


def flag(value):
    return 1 if value in (True, 1, "1", "true", "on") else 0


def ref_id(value):
    """An id pointing at another row (or empty for 'none')."""
    return integer(min_val=1)(value)


# ---------- per-table rules ----------

OPPORTUNITY_FIELDS = {
    "type": choice(C.OPPORTUNITY_TYPES),
    "company": text(200, required=True),
    "title": text(200),
    "link": url,
    "source": choice(C.SOURCES),
    "location": text(200),
    "pay": text(100),
    "stage": choice(C.STAGES),
    "close_reason": choice(C.CLOSE_REASONS, nullable=True),
    "urgency": choice(C.URGENCY),
    "importance": choice(C.IMPORTANCE),
    "deadline": iso_date,
    "deadline_time": hhmm,
    "next_action": text(300),
    "next_action_date": iso_date,
    "notes": text(20000),
    "tags": tags,
    # From "paste a posting" / the clipper (Phase 2)
    "summary": text(1000),
    "requirements": text(5000),      # one requirement per line
    "posting_text": text(60000),     # the original posting, kept for fit checks later
    "reminders": reminder_days,      # per-card deadline reminder override (Phase 3)
    "research_notes": text(20000),   # interview prep notes (Phase 4)
}

TASK_FIELDS = {
    "title": text(300, required=True),
    "opportunity_id": ref_id,
    "contact_id": ref_id,
    "due_date": iso_date,
    "planned_date": iso_date,
    "start_time": hhmm,
    "duration_min": integer(5, 24 * 60),
    "urgency": choice(C.URGENCY),
    "importance": choice(C.IMPORTANCE),
    "est_min": integer(0, 24 * 60),
    "actual_min": integer(0, 100000),
    "energy": choice(C.ENERGY),
    "completeness": integer(0, 100),
    "status": choice(C.TASK_STATUS),
    "repeat": choice(C.REPEAT),
    "notes": text(20000),
}

CONTACT_FIELDS = {
    "name": text(200, required=True),
    "company": text(200),
    "role": text(200),
    "email": email,
    "linkedin": url,
    "how_met": text(300),
    "notes": text(20000),
    "follow_up_date": iso_date,
}

INTERACTION_FIELDS = {
    "kind": choice(C.INTERACTION_KINDS),
    "happened_on": iso_date,
    "note": text(2000),
    "opportunity_id": ref_id,
}

DOCUMENT_FIELDS = {
    "kind": choice(C.DOCUMENT_KINDS),
    "label": text(150, required=True),
    "text": text(60000),
    "notes": text(5000),
}

QUESTION_FIELDS = {
    "opportunity_id": ref_id,
    "kind": choice(C.QUESTION_KINDS),
    "text": text(1000, required=True),
    "answer": text(10000),
    "tags": tags,
    "best": flag,
    "note": text(1000),
}

CHECKLIST_FIELDS = {
    "text": text(300, required=True),
    "done": flag,
}


def clean_each(data, rules):
    """Like clean(partial=True), but forgiving: a bad field is dropped with a warning
    instead of rejecting everything. Used for AI output, where one wrong field
    shouldn't throw away the whole card. Returns (clean_dict, warnings)."""
    out, warnings = {}, []
    for key, value in data.items():
        if key not in rules:
            continue
        if value is None or value == "" or value == []:
            continue
        try:
            out[key] = rules[key](value)
        except ValueError as e:
            warnings.append(f"Dropped {key.replace('_', ' ')} ({value!r}): it {e}.")
    return out, warnings


def clean(data, rules, partial=False):
    """Check a dict from the browser against a rules dict.

    partial=False (creating): every required field must be present.
    partial=True  (editing):  only check the fields that were sent.
    Returns the cleaned dict, or raises ValidationError listing every problem.
    """
    if not isinstance(data, dict):
        raise ValidationError("Expected a JSON object.")
    errors = []
    out = {}
    for key in data:
        if key not in rules:
            errors.append(f"Unknown field '{key}'.")
    for key, check in rules.items():
        if key not in data:
            # Missing is fine (the database default is used) unless the field is required.
            if not partial and getattr(check, "required", False):
                errors.append(f"{key.replace('_', ' ').capitalize()} is required.")
            continue
        try:
            out[key] = check(data[key])
        except ValueError as e:
            errors.append(f"{key.replace('_', ' ').capitalize()} {e}.")
    if errors:
        raise ValidationError(" ".join(errors))
    return out

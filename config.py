"""Settings for the whole app, read once from the .env file.

Everything else imports from here instead of reading environment variables
directly, so there is exactly one place to look when a setting is wrong.
"""
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Folder this file lives in (the project root).
BASE_DIR = Path(__file__).resolve().parent

# Load .env from the project root into os.environ.
load_dotenv(BASE_DIR / ".env")

# All dates and times in the app are Eastern Time.
TZ = ZoneInfo("America/New_York")

DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
# Reminders, backups, and the weekly coach run only where this is 1 (the Mac mini).
RUN_SCHEDULER = os.getenv("RUN_SCHEDULER", "1") == "1"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5050"))

# Where the database lives. Blank means "<project>/data".
DATA_DIR = Path(os.getenv("DATA_DIR") or (BASE_DIR / "data")).expanduser()
DB_PATH = DATA_DIR / "launchpad.db"

# Public address of the app (used by the clipper bookmarklet). Blank = work it out per request.
APP_URL = os.getenv("APP_URL", "").rstrip("/")

# AI settings. The key stays on the server: it is never sent to the browser.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
PARSE_MODEL = os.getenv("PARSE_MODEL") or "claude-haiku-5-5"
SMART_MODEL = os.getenv("SMART_MODEL") or "claude-sonnet-5-5"
AI_ENABLED = bool(ANTHROPIC_API_KEY)

# Reminders (Phase 3). The password and ntfy topic are secrets: server only.
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "").strip()          # sends FROM this account
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "").strip()            # sends TO this address
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "").strip()
ENV_PATH = BASE_DIR / ".env"


# Optional single-password login (see auth.py / set_password.py). Blank = no login.
PASSWORD_HASH = os.getenv("LAUNCHPAD_PASSWORD_HASH", "").strip()
SECRET_KEY = os.getenv("LAUNCHPAD_SECRET_KEY", "").strip()


def app_base_url():
    """Where links in emails and pushes point. APP_URL wins; otherwise this computer's address."""
    return APP_URL or f"http://{HOST}:{PORT}"


def email_ready():
    return bool(GMAIL_ADDRESS and GMAIL_APP_PASSWORD and NOTIFY_EMAIL)


def push_ready():
    return bool(NTFY_TOPIC)


def now():
    """Current date and time in Eastern Time."""
    return datetime.now(TZ)


def now_str():
    """Current Eastern time as text, e.g. '2026-11-09 14:03:12'. Used for timestamps in the database."""
    return now().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    """Today's Eastern date as text, e.g. '2026-11-09'."""
    return now().strftime("%Y-%m-%d")


def clock(hhmm):
    """'23:59' -> '11:59 PM' (for emails and calendar titles)."""
    hour, minute = (int(x) for x in hhmm.split(":"))
    return f"{hour % 12 or 12}:{minute:02d} {'PM' if hour >= 12 else 'AM'}"

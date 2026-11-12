"""Database helpers: opening connections, creating tables, and the activity log."""
import json
import sqlite3

from flask import g

import config


def connect():
    """Open a new SQLite connection with the settings this app relies on."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row            # rows behave like dicts: row["company"]
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite ignores REFERENCES unless this is on
    conn.execute("PRAGMA journal_mode = WAL") # lets the page read while a write happens
    return conn


def get_db():
    """The connection for the current web request (one per request, closed afterwards)."""
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    """Called by Flask after every request."""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


# Changes to the database after Phase 1, applied in order exactly once.
# SQLite keeps a counter (PRAGMA user_version) of how many have run, so each
# new phase just appends to this list and existing databases catch up on startup.
MIGRATIONS = [
    # 1 (Phase 2): posting details captured by "paste a posting" and the clipper.
    """ALTER TABLE opportunities ADD COLUMN summary TEXT NOT NULL DEFAULT '';
       ALTER TABLE opportunities ADD COLUMN requirements TEXT NOT NULL DEFAULT '';
       ALTER TABLE opportunities ADD COLUMN posting_text TEXT NOT NULL DEFAULT '';""",

    # 2 (Phase 3): reminders, the notification log, and settings you can change in the app.
    """ALTER TABLE opportunities ADD COLUMN reminders TEXT NOT NULL DEFAULT '';  -- '' = default, 'off', or '7,2,0'

       -- Every reminder, once. "key" makes repeats impossible: the same reminder for the
       -- same item and date can only be inserted one time. Also feeds the in-app bell.
       CREATE TABLE IF NOT EXISTS notifications (
           id          INTEGER PRIMARY KEY,
           key         TEXT NOT NULL UNIQUE,   -- e.g. 'deadline:12:2026-11-15:2'
           trigger     TEXT NOT NULL,          -- deadline, followup, contact, next_action, digest, weekly_plan, test
           title       TEXT NOT NULL,          -- full detail (shown in the app and email)
           body        TEXT NOT NULL DEFAULT '',
           link        TEXT NOT NULL DEFAULT '',  -- path inside the app, e.g. '/?open=opportunity:12'
           channels    TEXT NOT NULL DEFAULT '',  -- what was attempted: 'email', 'push', 'email,push'
           email_sent_at TEXT,
           push_sent_at  TEXT,
           error       TEXT,
           read_at     TEXT,
           created_at  TEXT NOT NULL
       );
       CREATE INDEX IF NOT EXISTS idx_notifications_time ON notifications(created_at);

       CREATE TABLE IF NOT EXISTS settings (
           key   TEXT PRIMARY KEY,
           value TEXT NOT NULL
       );""",

    # 3: what every AI call cost, for the spending meter and monthly cap (ai_budget.py).
    """CREATE TABLE IF NOT EXISTS ai_usage (
           id                 INTEGER PRIMARY KEY,
           created_at         TEXT NOT NULL,
           feature            TEXT NOT NULL,     -- 'brain_dump', 'posting', 'fit_check', ...
           model              TEXT NOT NULL,
           input_tokens       INTEGER NOT NULL,
           output_tokens      INTEGER NOT NULL,  -- includes the model's thinking
           cache_write_tokens INTEGER NOT NULL DEFAULT 0,
           cache_read_tokens  INTEGER NOT NULL DEFAULT 0,
           cost_usd           REAL NOT NULL,     -- estimated from ai_budget.PRICES
           over_cap           INTEGER NOT NULL DEFAULT 0   -- 1 = ran after the cap via an override
       );
       CREATE INDEX IF NOT EXISTS idx_ai_usage_time ON ai_usage(created_at);""",

    # 4 (Phase 4): documents, fit checks, interview questions, rejection log.
    """ALTER TABLE opportunities ADD COLUMN research_notes TEXT NOT NULL DEFAULT '';

       -- Resume and cover letter versions. The file itself is in DATA_DIR/documents.
       CREATE TABLE IF NOT EXISTS documents (
           id          INTEGER PRIMARY KEY,
           kind        TEXT NOT NULL DEFAULT 'resume',   -- resume, cover_letter, other
           label       TEXT NOT NULL,                    -- e.g. 'Resume - AI security v3'
           filename    TEXT NOT NULL DEFAULT '',         -- original name ('' = text pasted in, no file)
           stored_name TEXT NOT NULL DEFAULT '',         -- random name on disk
           size_bytes  INTEGER NOT NULL DEFAULT 0,
           text        TEXT NOT NULL DEFAULT '',         -- extracted (or pasted) text, used by fit checks
           notes       TEXT NOT NULL DEFAULT '',
           is_seed     INTEGER NOT NULL DEFAULT 0,
           created_at  TEXT NOT NULL,
           updated_at  TEXT NOT NULL
       );

       -- Which document versions you sent for an opportunity, and when.
       CREATE TABLE IF NOT EXISTS opportunity_documents (
           id             INTEGER PRIMARY KEY,
           opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
           document_id    INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
           sent_on        TEXT NOT NULL,
           note           TEXT NOT NULL DEFAULT '',
           created_at     TEXT NOT NULL
       );

       -- AI fit checks, kept as history (the newest one shows on the card).
       CREATE TABLE IF NOT EXISTS fit_checks (
           id             INTEGER PRIMARY KEY,
           opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
           document_id    INTEGER REFERENCES documents(id) ON DELETE SET NULL,
           document_label TEXT NOT NULL DEFAULT '',
           score          INTEGER NOT NULL,              -- 1-5
           score_reason   TEXT NOT NULL,
           result         TEXT NOT NULL,                 -- JSON: matches, gaps, talking points
           model          TEXT NOT NULL,
           cost_usd       REAL NOT NULL DEFAULT 0,
           created_at     TEXT NOT NULL
       );

       -- Interview questions. Together they form the question bank.
       CREATE TABLE IF NOT EXISTS questions (
           id             INTEGER PRIMARY KEY,
           opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE SET NULL,  -- kept if the card is deleted
           kind           TEXT NOT NULL DEFAULT 'asked',  -- asked, likely, to_ask, bank
           text           TEXT NOT NULL,
           answer         TEXT NOT NULL DEFAULT '',
           tags           TEXT NOT NULL DEFAULT '',       -- comma-separated, see constants.QUESTION_TAGS
           best           INTEGER NOT NULL DEFAULT 0,     -- 1 = my best answer to this question
           note           TEXT NOT NULL DEFAULT '',       -- e.g. why the AI thinks it will come up
           is_seed        INTEGER NOT NULL DEFAULT 0,
           created_at     TEXT NOT NULL,
           updated_at     TEXT NOT NULL
       );
       CREATE INDEX IF NOT EXISTS idx_questions_opp ON questions(opportunity_id);

       -- One row each time a card closes as rejected or ghosted. Company etc. are copied
       -- so the history survives even if the card is deleted later.
       CREATE TABLE IF NOT EXISTS rejections (
           id             INTEGER PRIMARY KEY,
           opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE SET NULL,
           company        TEXT NOT NULL,
           title          TEXT NOT NULL DEFAULT '',
           type           TEXT NOT NULL DEFAULT '',
           source         TEXT NOT NULL DEFAULT '',
           reason         TEXT NOT NULL,                  -- rejected or ghosted
           stage_reached  TEXT NOT NULL,                  -- the stage it was in before closing
           days_open      INTEGER,                        -- from when it was added to when it closed
           lesson         TEXT NOT NULL DEFAULT '',       -- "what did you learn?" (optional)
           is_seed        INTEGER NOT NULL DEFAULT 0,
           created_at     TEXT NOT NULL
       );""",

    # 5: tailored resumes (Phase 4 add-on) and Phase 5 (Top 3 pins, weekly reviews).
    """ALTER TABLE documents ADD COLUMN source_document_id INTEGER;   -- the resume it was tailored from
       ALTER TABLE documents ADD COLUMN opportunity_id INTEGER;       -- the role it was tailored for
       ALTER TABLE documents ADD COLUMN tailor_notes TEXT NOT NULL DEFAULT '';  -- JSON: what changed and why

       -- Today's Top 3: up to three pinned tasks or opportunities per day.
       CREATE TABLE IF NOT EXISTS pins (
           id         INTEGER PRIMARY KEY,
           day        TEXT NOT NULL,             -- 'YYYY-MM-DD'
           item_type  TEXT NOT NULL,             -- 'task' or 'opportunity'
           item_id    INTEGER NOT NULL,
           position   INTEGER NOT NULL DEFAULT 0,
           created_at TEXT NOT NULL,
           UNIQUE (day, item_type, item_id)
       );

       -- Weekly review + coach, one per week (Monday date).
       CREATE TABLE IF NOT EXISTS reviews (
           id         INTEGER PRIMARY KEY,
           week_start TEXT NOT NULL UNIQUE,
           data       TEXT NOT NULL,             -- JSON: the numbers that went in + the coach's reply
           my_notes   TEXT NOT NULL DEFAULT '',
           status     TEXT NOT NULL DEFAULT 'draft',   -- draft until you save it with your notes
           model      TEXT NOT NULL DEFAULT '',
           cost_usd   REAL NOT NULL DEFAULT 0,
           created_at TEXT NOT NULL,
           updated_at TEXT NOT NULL
       );""",

    # 6: Discover (postings found for you) and the Canvas sync.
    """-- Postings found by discover.py, waiting for you to add or dismiss them.
       CREATE TABLE IF NOT EXISTS discoveries (
           id             INTEGER PRIMARY KEY,
           source         TEXT NOT NULL,            -- 'email:80000hours.org', 'greenhouse:anthropic', ...
           external_id    TEXT NOT NULL,            -- the posting's id at that source (stops repeats)
           org            TEXT NOT NULL DEFAULT '',
           title          TEXT NOT NULL DEFAULT '',
           location       TEXT NOT NULL DEFAULT '',
           type           TEXT NOT NULL DEFAULT 'job',   -- job, internship, fellowship
           link           TEXT NOT NULL DEFAULT '',
           deadline       TEXT,                     -- 'YYYY-MM-DD' if the listing gave one
           summary        TEXT NOT NULL DEFAULT '',
           description    TEXT NOT NULL DEFAULT '', -- full posting text when the source has it
           score          INTEGER,                  -- 0-100 fit with your skills profile (AI); NULL = not scored
           score_reason   TEXT NOT NULL DEFAULT '',
           status         TEXT NOT NULL DEFAULT 'new',   -- new, added, dismissed
           opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE SET NULL,
           posted_at      TEXT,
           found_at       TEXT NOT NULL,
           UNIQUE (source, external_id)
       );
       CREATE INDEX IF NOT EXISTS idx_discoveries_status ON discoveries(status, score);

       -- Assignments, calendar events, and announcements read from your Canvas feeds.
       CREATE TABLE IF NOT EXISTS canvas_items (
           id         INTEGER PRIMARY KEY,
           uid        TEXT NOT NULL UNIQUE,         -- Canvas's own id for it
           kind       TEXT NOT NULL,                -- assignment, event, announcement
           course     TEXT NOT NULL DEFAULT '',
           title      TEXT NOT NULL DEFAULT '',
           url        TEXT NOT NULL DEFAULT '',
           due_at     TEXT,                         -- Eastern 'YYYY-MM-DD HH:MM' (assignments/events)
           all_day    INTEGER NOT NULL DEFAULT 0,
           posted_at  TEXT,                         -- Eastern 'YYYY-MM-DD HH:MM' (announcements)
           body       TEXT NOT NULL DEFAULT '',     -- plain text
           task_id    INTEGER REFERENCES tasks(id) ON DELETE SET NULL,  -- the task made for an assignment
           created_at TEXT NOT NULL,
           updated_at TEXT NOT NULL
       );

       -- Things already handled once (emails read, assignments turned into tasks), so a
       -- deleted task or a dismissed email never comes back.
       CREATE TABLE IF NOT EXISTS sync_seen (
           key        TEXT PRIMARY KEY,
           created_at TEXT NOT NULL
       );""",

    # 7: the agent chat on the Pipeline page (agent.py).
    """CREATE TABLE IF NOT EXISTS agent_chats (
           id         INTEGER PRIMARY KEY,
           title      TEXT NOT NULL DEFAULT '',    -- the first message, shortened
           messages   TEXT NOT NULL DEFAULT '[]',  -- JSON: the full conversation as sent to Claude (tool calls included)
           display    TEXT NOT NULL DEFAULT '[]',  -- JSON: what the chat panel shows (your messages, replies, actions)
           cost_usd   REAL NOT NULL DEFAULT 0,
           created_at TEXT NOT NULL,
           updated_at TEXT NOT NULL
       );""",
]


def init_db():
    """Create any missing tables, then apply any migrations not yet run. Safe on every startup."""
    schema = (config.BASE_DIR / "schema.sql").read_text(encoding="utf-8")
    with connect() as conn:
        conn.executescript(schema)
        done = conn.execute("PRAGMA user_version").fetchone()[0]
        for number, sql in enumerate(MIGRATIONS[done:], start=done + 1):
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {number}")


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def log_activity(conn, entity_type, entity_id, action, summary, details=None, is_seed=0):
    """Add one line to the activity log.

    entity_type: 'opportunity', 'task', 'contact', 'interaction', 'checklist'
    action:      'created', 'updated', 'stage_changed', 'completed', 'deleted', ...
    summary:     a sentence a human can read, e.g. 'Moved Acme to Sent'
    details:     optional dict (saved as JSON), e.g. {'stage': ['interested', 'sent']}
    """
    conn.execute(
        """INSERT INTO activity_log (entity_type, entity_id, action, summary, details, is_seed, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (entity_type, entity_id, action, summary,
         json.dumps(details) if details else None, is_seed, config.now_str()),
    )

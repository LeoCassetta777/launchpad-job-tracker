-- Launchpad database schema (SQLite).
-- Run automatically on startup by db.py. "IF NOT EXISTS" makes it safe to run every time.
--
-- Conventions:
--   * Dates are text 'YYYY-MM-DD'; times are text 'HH:MM' (24-hour); timestamps are
--     'YYYY-MM-DD HH:MM:SS'. Everything is Eastern Time.
--   * Choice columns (stage, urgency, ...) hold the keys listed in constants.py.
--   * is_seed = 1 marks fake demo rows from seed.py so they can be wiped without
--     touching your real data.

-- Jobs, internships, fellowships, and outreach leads.
-- (Later phases add columns through MIGRATIONS in db.py: summary, requirements, posting_text.)
CREATE TABLE IF NOT EXISTS opportunities (
    id               INTEGER PRIMARY KEY,
    type             TEXT NOT NULL DEFAULT 'job',
    company          TEXT NOT NULL,
    title            TEXT NOT NULL DEFAULT '',        -- role or title
    link             TEXT NOT NULL DEFAULT '',
    source           TEXT NOT NULL DEFAULT 'other',
    location         TEXT NOT NULL DEFAULT '',        -- city, or "Remote" / "Hybrid"
    pay              TEXT NOT NULL DEFAULT '',        -- free text, e.g. "$25/hr"
    stage            TEXT NOT NULL DEFAULT 'interested',
    close_reason     TEXT,                            -- only when stage = 'closed'
    urgency          TEXT NOT NULL DEFAULT 'chill',
    importance       TEXT NOT NULL DEFAULT 'medium',
    deadline         TEXT,                            -- date
    deadline_time    TEXT,                            -- optional time, e.g. '23:59'
    next_action      TEXT NOT NULL DEFAULT '',
    next_action_date TEXT,
    notes            TEXT NOT NULL DEFAULT '',
    tags             TEXT NOT NULL DEFAULT '',        -- comma-separated, e.g. 'ai,security'
    position         INTEGER NOT NULL DEFAULT 0,      -- order within its pipeline column
    is_seed          INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

-- People. Linked to opportunities many-to-many through opportunity_contacts.
CREATE TABLE IF NOT EXISTS contacts (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    company        TEXT NOT NULL DEFAULT '',
    role           TEXT NOT NULL DEFAULT '',
    email          TEXT NOT NULL DEFAULT '',
    linkedin       TEXT NOT NULL DEFAULT '',
    how_met        TEXT NOT NULL DEFAULT '',
    notes          TEXT NOT NULL DEFAULT '',
    follow_up_date TEXT,
    is_seed        INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opportunity_contacts (
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    contact_id     INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    PRIMARY KEY (opportunity_id, contact_id)
);

-- Things to do. Can point at an opportunity and/or a contact.
CREATE TABLE IF NOT EXISTS tasks (
    id             INTEGER PRIMARY KEY,
    title          TEXT NOT NULL,
    opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE SET NULL,
    contact_id     INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    due_date       TEXT,                    -- when it must be done
    planned_date   TEXT,                    -- the day you plan to work on it
    start_time     TEXT,                    -- set for interviews/calls/meetings -> timed block
    duration_min   INTEGER,                 -- length of the timed block
    urgency        TEXT NOT NULL DEFAULT 'chill',
    importance     TEXT NOT NULL DEFAULT 'medium',
    est_min        INTEGER,                 -- estimated minutes
    actual_min     INTEGER,                 -- logged minutes (focus timer, Phase 5)
    energy         TEXT NOT NULL DEFAULT 'med',
    completeness   INTEGER NOT NULL DEFAULT 0,  -- 0-100; ignored when the task has a checklist
    status         TEXT NOT NULL DEFAULT 'todo',
    repeat         TEXT NOT NULL DEFAULT 'none',
    notes          TEXT NOT NULL DEFAULT '',
    position       INTEGER NOT NULL DEFAULT 0,
    completed_at   TEXT,
    is_seed        INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

-- A dated log per contact. "Last contacted" = the newest happened_on here.
CREATE TABLE IF NOT EXISTS interactions (
    id             INTEGER PRIMARY KEY,
    contact_id     INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE SET NULL,
    kind           TEXT NOT NULL DEFAULT 'other',
    happened_on    TEXT NOT NULL,           -- date
    note           TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL
);

-- Subtasks. Each item belongs to exactly one task OR one opportunity.
CREATE TABLE IF NOT EXISTS checklist_items (
    id             INTEGER PRIMARY KEY,
    task_id        INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE CASCADE,
    text           TEXT NOT NULL,
    done           INTEGER NOT NULL DEFAULT 0,
    position       INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    CHECK ((task_id IS NULL) <> (opportunity_id IS NULL))
);

-- Every create, edit, stage change, and completion. Powers history, streaks,
-- stats, and the weekly coach. No foreign key on purpose: history survives deletes.
CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,      -- 'opportunity', 'task', 'contact', ...
    entity_id   INTEGER,
    action      TEXT NOT NULL,      -- 'created', 'updated', 'stage_changed', 'completed', ...
    summary     TEXT NOT NULL,      -- one human-readable line
    details     TEXT,               -- JSON with what changed (old -> new)
    is_seed     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_opp_stage        ON opportunities(stage);
CREATE INDEX IF NOT EXISTS idx_task_dates       ON tasks(planned_date, due_date);
CREATE INDEX IF NOT EXISTS idx_interact_contact ON interactions(contact_id, happened_on);
CREATE INDEX IF NOT EXISTS idx_check_task       ON checklist_items(task_id);
CREATE INDEX IF NOT EXISTS idx_check_opp        ON checklist_items(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_activity_entity  ON activity_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_activity_time    ON activity_log(created_at);

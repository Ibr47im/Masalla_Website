-- Delivery-note portal schema
-- Idempotent: safe to run on every app startup.

CREATE TABLE IF NOT EXISTS clients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('admin','staff','client')),
    client_id       INTEGER REFERENCES clients(id),
    floor           INTEGER,
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS delivery_notes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    note_number         TEXT NOT NULL UNIQUE,
    client_id           INTEGER NOT NULL REFERENCES clients(id),
    floor               INTEGER NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','confirmed','voided')),
    created_by          INTEGER NOT NULL REFERENCES users(id),
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    confirmed_by_name   TEXT,
    confirmed_at        TEXT,
    voided_by           INTEGER REFERENCES users(id),
    voided_at           TEXT,
    voided_reason       TEXT,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS delivery_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id         INTEGER NOT NULL REFERENCES delivery_notes(id) ON DELETE CASCADE,
    sort_order      INTEGER NOT NULL,
    name_en         TEXT NOT NULL,
    name_ar         TEXT,
    staff_quantity  INTEGER NOT NULL,
    client_quantity INTEGER
);

CREATE INDEX IF NOT EXISTS idx_notes_client ON delivery_notes(client_id);
CREATE INDEX IF NOT EXISTS idx_notes_status ON delivery_notes(status);
CREATE INDEX IF NOT EXISTS idx_notes_floor  ON delivery_notes(floor);
CREATE INDEX IF NOT EXISTS idx_items_note   ON delivery_items(note_id);

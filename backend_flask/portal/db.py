"""SQLite connection management for the portal."""
import os
import sqlite3
from pathlib import Path

from flask import g

_PACKAGE_DIR = Path(__file__).resolve().parent
_SCHEMA_PATH = _PACKAGE_DIR / "schema.sql"

_DEFAULT_DB_PATH = "/opt/masalla/data/portal.db"


def get_db_path():
    return os.environ.get("PORTAL_DB_PATH", _DEFAULT_DB_PATH)


def _connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """Per-request connection, stashed on flask.g."""
    if "portal_db" not in g:
        g.portal_db = _connect(get_db_path())
    return g.portal_db


def close_db(_exc=None):
    conn = g.pop("portal_db", None)
    if conn is not None:
        conn.close()


def ensure_initialized():
    """Idempotent schema bootstrap. Safe to call from every worker on startup."""
    path = get_db_path()
    conn = _connect(path)
    try:
        conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def query_one(sql, params=()):
    return get_db().execute(sql, params).fetchone()


def query_all(sql, params=()):
    return get_db().execute(sql, params).fetchall()


def execute(sql, params=()):
    conn = get_db()
    cursor = conn.execute(sql, params)
    conn.commit()
    return cursor


# --- Context-free helpers for CLI / scripts ------------------------------

def open_standalone():
    """Open a standalone connection (no Flask context). Caller must close."""
    return _connect(get_db_path())

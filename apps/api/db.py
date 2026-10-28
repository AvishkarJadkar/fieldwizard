"""SQLite match registry.

The pipeline is stateless (it writes result.json + tracks.json into a match
folder); this table only holds job state and a small summary for the list view,
so a crashed API never corrupts analysis output.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data")
DB_PATH = os.path.join(DATA, "fieldwizard.db")

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued',
    progress    INTEGER NOT NULL DEFAULT 0,
    message     TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    source      TEXT,
    outdir      TEXT,
    duration    REAL,
    error       TEXT,
    summary     TEXT
);
CREATE INDEX IF NOT EXISTS idx_matches_created ON matches(created_at DESC);
"""


def connect() -> sqlite3.Connection:
    os.makedirs(DATA, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def init() -> None:
    with _lock, connect() as con:
        con.executescript(SCHEMA)


def create(match_id: str, title: str, source: str, outdir: str, status: str = "queued") -> None:
    now = time.time()
    with _lock, connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO matches"
            " (id,title,status,progress,message,created_at,updated_at,source,outdir)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (match_id, title, status, 0, "Queued", now, now, source, outdir),
        )


def update(match_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock, connect() as con:
        con.execute(f"UPDATE matches SET {cols} WHERE id=?", (*fields.values(), match_id))


def get(match_id: str) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    return dict(row) if row else None


def list_all() -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT * FROM matches ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete(match_id: str) -> None:
    with _lock, connect() as con:
        con.execute("DELETE FROM matches WHERE id=?", (match_id,))


def public(row: dict) -> dict:
    """Serialise a row for the client, expanding the summary blob."""
    summary = {}
    if row.get("summary"):
        try:
            summary = json.loads(row["summary"])
        except Exception:
            summary = {}
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "progress": row["progress"],
        "message": row["message"],
        "created_at": row["created_at"],
        "duration": row.get("duration"),
        "error": (row.get("error") or "")[-600:] or None,
        **summary,
    }

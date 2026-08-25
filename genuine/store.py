"""SQLite storage: the shared fingerprint registry (§6.4) and API job rows.

Connections are opened per-operation (SQLite is fine with this at demo
concurrency) so there's no shared-connection threading hazard under uvicorn.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT UNIQUE NOT NULL,
    repo_url      TEXT NOT NULL,
    owner         TEXT NOT NULL DEFAULT '',
    repo_name     TEXT NOT NULL DEFAULT '',
    fingerprint   TEXT NOT NULL,           -- json list[int] MinHash signature
    repo_created_at TEXT,
    ingested_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    repo_url    TEXT NOT NULL,
    status      TEXT NOT NULL,             -- queued|running|done|error
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    result_json TEXT,
    error       TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_schema(db_path: str | Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(_SCHEMA)

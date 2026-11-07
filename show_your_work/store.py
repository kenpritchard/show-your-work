"""SQLite schema. Runs and reviews are append-only; links can be added and removed."""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    project TEXT NOT NULL,
    requirement TEXT NOT NULL,
    test_id TEXT NOT NULL,
    linked_by TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (project, requirement, test_id)
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    report_path TEXT NOT NULL,
    report_sha256 TEXT NOT NULL,
    provenance TEXT NOT NULL,
    code_digest TEXT NOT NULL,
    tracked_files INTEGER NOT NULL,
    tests INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_by_project ON runs (project, imported_at);
CREATE TABLE IF NOT EXISTS results (
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    seq INTEGER NOT NULL,
    test_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    message TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    requirement TEXT NOT NULL,
    decision TEXT NOT NULL,
    note TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    criterion_digest TEXT NOT NULL,
    code_digest TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS reviews_by_req ON reviews (project, requirement, review_id);
"""


def init(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn

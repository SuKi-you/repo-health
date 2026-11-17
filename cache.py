import sqlite3
from datetime import date, datetime
from pathlib import Path

DB = "data/cache.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS judgments (
    repo       TEXT NOT NULL,
    week       TEXT NOT NULL,
    result     TEXT NOT NULL,
    reason     TEXT,
    source     TEXT NOT NULL DEFAULT 'llm',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (repo, week)
)
"""


def connect(db_path=DB):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def week_key(today=None):
    day = today or date.today()
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def lookup(conn, repo, today=None):
    row = conn.execute(
        "SELECT repo, week, result, reason, source, updated_at FROM judgments "
        "WHERE repo = ? AND week = ?",
        (repo, week_key(today)),
    ).fetchone()
    return dict(row) if row else None


def save(conn, repo, result, reason="", source="llm", today=None):
    if source not in ("llm", "manual"):
        raise ValueError(f"未知来源: {source}")

    week = week_key(today)
    existing = conn.execute(
        "SELECT source FROM judgments WHERE repo = ? AND week = ?", (repo, week)
    ).fetchone()

    if existing and existing["source"] == "manual" and source == "llm":
        return False

    conn.execute(
        "INSERT INTO judgments (repo, week, result, reason, source, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(repo, week) DO UPDATE SET "
        "result = excluded.result, reason = excluded.reason, "
        "source = excluded.source, updated_at = excluded.updated_at",
        (repo, week, result, reason, source, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    return True

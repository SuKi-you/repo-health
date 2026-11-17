import json
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
    highlight  TEXT,
    panels     TEXT,
    metrics    TEXT,
    source     TEXT NOT NULL DEFAULT 'llm',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (repo, week)
)
"""

EXTRA_COLUMNS = ("highlight", "panels", "metrics")


def connect(db_path=DB):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)

    existing = [row[1] for row in conn.execute("PRAGMA table_info(judgments)")]
    for name in EXTRA_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE judgments ADD COLUMN {name} TEXT")
    return conn


def week_key(today=None):
    day = today or date.today()
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def _decode(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def lookup(conn, repo, today=None):
    row = conn.execute(
        "SELECT repo, week, result, reason, highlight, panels, metrics, source, updated_at "
        "FROM judgments WHERE repo = ? AND week = ?",
        (repo, week_key(today)),
    ).fetchone()
    if row is None:
        return None

    item = dict(row)
    item["panels"] = _decode(item.get("panels"), [])
    item["metrics"] = _decode(item.get("metrics"), None)
    return item


def save(
    conn, repo, result, reason="", source="llm", today=None,
    highlight="", panels=None, metrics=None,
):
    if source not in ("llm", "manual"):
        raise ValueError(f"未知来源: {source}")

    week = week_key(today)
    existing = conn.execute(
        "SELECT source FROM judgments WHERE repo = ? AND week = ?", (repo, week)
    ).fetchone()

    if existing and existing["source"] == "manual" and source == "llm":
        return False

    conn.execute(
        "INSERT INTO judgments "
        "(repo, week, result, reason, highlight, panels, metrics, source, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(repo, week) DO UPDATE SET "
        "result = excluded.result, reason = excluded.reason, "
        "highlight = excluded.highlight, panels = excluded.panels, "
        "metrics = excluded.metrics, source = excluded.source, "
        "updated_at = excluded.updated_at",
        (
            repo, week, result, reason, highlight,
            json.dumps(panels, ensure_ascii=False) if panels else None,
            json.dumps(metrics, ensure_ascii=False) if metrics else None,
            source, datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    return True

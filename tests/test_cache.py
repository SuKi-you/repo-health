from datetime import date

import cache


TODAY = date(2026, 11, 17)


def fresh(path=None):
    return cache.connect(path or ":memory:")


def test_save_then_lookup():
    conn = fresh()
    cache.save(conn, "acme/lib", "健康", "无红旗", "llm", TODAY)

    row = cache.lookup(conn, "acme/lib", TODAY)
    assert row["result"] == "健康"
    assert row["reason"] == "无红旗"
    assert row["source"] == "llm"
    assert row["week"] == "2026-W47"


def test_panels_and_metrics_roundtrip():
    conn = fresh()
    panels = ["downloads_line", "activity_strip"]
    metrics = {"release_age": 10, "commits_4w": 0.0}

    cache.save(conn, "acme/lib", "不健康", "0 提交", "llm", TODAY,
               highlight="52 周 0 提交", panels=panels, metrics=metrics)

    row = cache.lookup(conn, "acme/lib", TODAY)
    assert row["panels"] == panels
    assert row["metrics"] == metrics
    assert row["highlight"] == "52 周 0 提交"


def test_missing_panels_decoded_as_empty():
    conn = fresh()
    cache.save(conn, "acme/lib", "健康", "", "llm", TODAY)

    row = cache.lookup(conn, "acme/lib", TODAY)
    assert row["panels"] == []
    assert row["metrics"] is None


def test_different_week_is_a_miss():
    conn = fresh()
    cache.save(conn, "acme/lib", "健康", "", "llm", TODAY)

    assert cache.lookup(conn, "acme/lib", date(2026, 11, 24)) is None


def test_same_week_is_a_hit():
    conn = fresh()
    cache.save(conn, "acme/lib", "健康", "", "llm", date(2026, 11, 16))

    assert cache.lookup(conn, "acme/lib", TODAY)["result"] == "健康"


def test_llm_can_overwrite_llm():
    conn = fresh()
    cache.save(conn, "acme/lib", "健康", "", "llm", TODAY)
    assert cache.save(conn, "acme/lib", "不健康", "新数据", "llm", TODAY) is True

    assert cache.lookup(conn, "acme/lib", TODAY)["result"] == "不健康"


def test_llm_cannot_overwrite_manual():
    conn = fresh()
    cache.save(conn, "acme/lib", "不健康", "人工判定", "manual", TODAY)
    assert cache.save(conn, "acme/lib", "健康", "", "llm", TODAY) is False

    row = cache.lookup(conn, "acme/lib", TODAY)
    assert row["result"] == "不健康"
    assert row["source"] == "manual"


def test_manual_can_overwrite_manual():
    conn = fresh()
    cache.save(conn, "acme/lib", "不健康", "", "manual", TODAY)
    assert cache.save(conn, "acme/lib", "健康", "复核后修正", "manual", TODAY) is True

    assert cache.lookup(conn, "acme/lib", TODAY)["result"] == "健康"


def test_unknown_source_is_rejected():
    conn = fresh()
    try:
        cache.save(conn, "acme/lib", "健康", "", "human", TODAY)
    except ValueError:
        return
    raise AssertionError("应当拒绝未知来源")


def test_week_key_format():
    assert cache.week_key(date(2026, 1, 1)) == "2026-W01"
    assert cache.week_key(date(2026, 11, 17)) == "2026-W47"


def test_old_schema_is_migrated():
    import sqlite3

    path = ".tmp/old_cache.db"
    raw = sqlite3.connect(path)
    raw.executescript("""
        DROP TABLE IF EXISTS judgments;
        CREATE TABLE judgments (
            repo TEXT NOT NULL, week TEXT NOT NULL, result TEXT NOT NULL,
            reason TEXT, source TEXT NOT NULL DEFAULT 'llm',
            updated_at TEXT NOT NULL, PRIMARY KEY (repo, week)
        );
    """)
    raw.execute("INSERT INTO judgments VALUES ('old/lib','2026-W47','健康','', 'llm','x')")
    raw.commit()
    raw.close()

    conn = cache.connect(path)
    columns = [r[1] for r in conn.execute("PRAGMA table_info(judgments)")]

    assert "panels" in columns
    assert "highlight" in columns
    row = cache.lookup(conn, "old/lib", TODAY)
    assert row["result"] == "健康"
    assert row["panels"] == []

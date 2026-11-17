from datetime import date

import cache


TODAY = date(2026, 11, 17)


def fresh():
    return cache.connect(":memory:")


def test_save_then_lookup():
    conn = fresh()
    cache.save(conn, "acme/lib", "健康", "无红旗", "llm", TODAY)

    row = cache.lookup(conn, "acme/lib", TODAY)
    assert row["result"] == "健康"
    assert row["reason"] == "无红旗"
    assert row["source"] == "llm"
    assert row["week"] == "2026-W47"


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

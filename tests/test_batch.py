from datetime import date
from pathlib import Path

import batch
import cache


TODAY = date(2026, 11, 17)
TMP = Path(".tmp")


def make_db(name, rows):
    TMP.mkdir(exist_ok=True)
    path = TMP / f"{name}.db"
    if path.exists():
        path.unlink()
    conn = cache.connect(path)
    for repo, result in rows:
        cache.save(conn, repo, result, "", "llm", TODAY)
    conn.close()
    return str(path)


def test_all_cached_needs_no_model():
    db = make_db("batch_all", [("a/one", "健康"), ("a/two", "不健康")])

    out = batch.judge_many(["a/one", "a/two"], db_path=db, today=TODAY)

    assert len(out["items"]) == 2
    assert all(item["cached"] for item in out["items"])
    assert [batch.verdict_of(i) for i in out["items"]] == ["健康", "不健康"]


def test_order_is_preserved():
    db = make_db("batch_order", [("a/one", "健康"), ("a/two", "不健康"), ("a/three", "健康")])

    out = batch.judge_many(["a/two", "a/one", "a/three"], db_path=db, today=TODAY)

    assert [i["repo"] for i in out["items"]] == ["a/two", "a/one", "a/three"]


def test_bad_target_does_not_break_the_batch():
    db = make_db("batch_bad", [("a/one", "健康")])

    out = batch.judge_many(["a/one", "这不是一个仓库"], db_path=db, today=TODAY)

    assert out["items"][0]["cached"] is True
    assert "error" in out["items"][1]
    assert batch.verdict_of(out["items"][1]) == "错误"


def test_verdict_parsed_from_answer():
    item = {"answer": "项目：a/b\n了解程度：熟悉\n结论：不健康\n理由：..."}
    assert batch.verdict_of(item) == "不健康"


def test_load_targets_from_file():
    TMP.mkdir(exist_ok=True)
    path = TMP / "targets.txt"
    path.write_text(
        "# 注释\nhttps://github.com/a/one\n\nhttps://github.com/a/two\n", encoding="utf-8"
    )

    assert batch.load_targets([str(path)]) == [
        "https://github.com/a/one",
        "https://github.com/a/two",
    ]


def test_load_targets_from_args():
    assert batch.load_targets(["a/one", "a/two"]) == ["a/one", "a/two"]

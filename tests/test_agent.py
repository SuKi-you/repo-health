from datetime import date

import pytest

import agent
import cache


TODAY = date(2026, 11, 17)


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def complete(self, messages, tools=None, temperature=0):
        self.calls += 1
        if not self.script:
            raise AssertionError("脚本已用完，模型被多调用了一次")
        return self.script.pop(0)


def tool_call(call_id, name, **kwargs):
    import json

    return {
        "tool_calls": [
            {
                "id": call_id,
                "function": {"name": name, "arguments": json.dumps(kwargs)},
            }
        ]
    }


def fake_analyzer(owner, repo):
    return {"full_name": f"{owner}/{repo}", "release_age": 10, "missing": []}


def test_parse_full_url():
    assert agent.parse_repo("https://github.com/pandas-dev/pandas") == "pandas-dev/pandas"


def test_parse_url_with_tree_suffix():
    url = "https://github.com/pandas-dev/pandas/tree/main/pandas"
    assert agent.parse_repo(url) == "pandas-dev/pandas"


def test_parse_url_with_issues_suffix():
    url = "https://github.com/pandas-dev/pandas/issues/123"
    assert agent.parse_repo(url) == "pandas-dev/pandas"


def test_parse_plain_owner_repo():
    assert agent.parse_repo("acme/lib") == "acme/lib"
    assert agent.parse_repo("acme/lib.git") == "acme/lib"


@pytest.mark.parametrize(
    "bad",
    ["", "pandas", "https://github.com/only-one-part", "acme/lib/extra/deep", "a b/c"],
)
def test_parse_rejects_invalid(bad):
    with pytest.raises(agent.RepoNameError):
        agent.parse_repo(bad)


def test_cache_hit_never_calls_model():
    conn = cache.connect(":memory:")
    cache.save(conn, "acme/lib", "健康", "无红旗", "llm", TODAY)

    client = FakeClient([])
    out = agent.judge("acme/lib", client=client, conn=conn, today=TODAY)

    assert out["cached"] is True
    assert out["result"] == "健康"
    assert client.calls == 0


def test_full_tool_loop_saves_judgment():
    conn = cache.connect(":memory:")
    client = FakeClient(
        [
            tool_call("c1", "analyze_repo", owner="acme", repo="lib"),
            tool_call(
                "c2", "save_judgment", owner="acme", repo="lib",
                result="健康", reason="未命中红旗",
            ),
            {"content": "项目：acme/lib\n结论：健康\n理由：未命中红旗"},
        ]
    )

    out = agent.judge(
        "https://github.com/acme/lib",
        client=client,
        conn=conn,
        today=TODAY,
        analyzer=fake_analyzer,
    )

    assert out["cached"] is False
    assert "健康" in out["answer"]
    assert client.calls == 3

    row = cache.lookup(conn, "acme/lib", TODAY)
    assert row["result"] == "健康"
    assert row["source"] == "llm"


def test_lookup_tool_reports_miss_then_model_continues():
    conn = cache.connect(":memory:")
    client = FakeClient(
        [
            tool_call("c1", "lookup_judgment", owner="acme", repo="lib"),
            tool_call("c2", "analyze_repo", owner="acme", repo="lib"),
            tool_call(
                "c3", "save_judgment", owner="acme", repo="lib",
                result="不健康", reason="发版距今 900 天",
            ),
            {"content": "结论：不健康"},
        ]
    )

    out = agent.judge("acme/lib", client=client, conn=conn, today=TODAY, analyzer=fake_analyzer)

    assert out["cached"] is False
    assert cache.lookup(conn, "acme/lib", TODAY)["result"] == "不健康"


def test_invalid_tool_arguments_do_not_crash():
    conn = cache.connect(":memory:")
    client = FakeClient(
        [
            tool_call("c1", "analyze_repo", owner="bad owner", repo="lib"),
            {"content": "无法评估"},
        ]
    )

    out = agent.judge("acme/lib", client=client, conn=conn, today=TODAY, analyzer=fake_analyzer)
    assert out["answer"] == "无法评估"


def test_gives_up_after_max_steps():
    conn = cache.connect(":memory:")
    client = FakeClient(
        [tool_call(f"c{i}", "analyze_repo", owner="acme", repo="lib") for i in range(3)]
    )

    with pytest.raises(RuntimeError):
        agent.judge(
            "acme/lib", client=client, conn=conn, today=TODAY,
            analyzer=fake_analyzer, max_steps=3,
        )

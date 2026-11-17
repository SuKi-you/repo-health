import json
import re
import sys
from pathlib import Path

import analyze
import cache
import chart
from llm import ChatClient

PROMPT_FILE = Path("PROMPT.md")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
GH_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s?#]+)")

PANEL_TYPES = ["downloads_line", "downloads_weekly", "activity_strip", "commits_weekly"]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_judgment",
            "description": "查询该仓库 7 天内是否已有判定结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_repo",
            "description": "抓取并计算该仓库的健康度指标",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_judgment",
            "description": "保存最终判定结果，并指定用哪些图表支撑它",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "result": {"type": "string", "enum": ["健康", "不健康"]},
                    "reason": {"type": "string"},
                    "highlight": {"type": "string", "description": "一句话核心证据，不超过 30 字"},
                    "panels": {
                        "type": "array",
                        "items": {"type": "string", "enum": PANEL_TYPES},
                        "description": "支撑该结论的图表，1-2 个",
                    },
                },
                "required": ["owner", "repo", "result", "reason", "panels"],
            },
        },
    },
]


class RepoNameError(ValueError):
    pass


def parse_repo(text):
    text = (text or "").strip()
    match = GH_RE.search(text)
    if match:
        owner, name = match.group(1), match.group(2)
    elif text.count("/") == 1:
        owner, name = text.split("/")
    else:
        raise RepoNameError("链接无效，请提供 owner/repo 或 GitHub 项目链接")

    owner, name = owner.strip(), name.strip()
    if name.endswith(".git"):
        name = name[:-4]
    if not NAME_RE.match(owner) or not NAME_RE.match(name):
        raise RepoNameError("链接无效，请提供 owner/repo 或 GitHub 项目链接")
    return f"{owner}/{name}"


def _load_prompt():
    return PROMPT_FILE.read_text(encoding="utf-8")


def _run_tool(name, args, conn, analyzer, today, state):
    owner = args.get("owner", "")
    repo = args.get("repo", "")
    if not (NAME_RE.match(owner) and NAME_RE.match(repo)):
        return {"error": "owner/repo 格式不合法"}
    full = f"{owner}/{repo}"

    if name == "lookup_judgment":
        return cache.lookup(conn, full, today) or {"hit": False}

    if name == "analyze_repo":
        result = analyzer(owner, repo)
        if isinstance(result, dict) and "error" not in result:
            state["metrics"] = result
        return result

    if name == "save_judgment":
        panels = args.get("panels") or []
        panel_names = [p for p in panels if p in PANEL_TYPES]
        ok = cache.save(
            conn, full, args.get("result", ""), args.get("reason", ""), "llm", today,
            highlight=args.get("highlight", ""),
            panels=panel_names,
            metrics=state.get("metrics"),
        )
        state["saved"] = {
            "result": args.get("result", ""),
            "reason": args.get("reason", ""),
            "highlight": args.get("highlight", ""),
            "panels": panel_names,
        }
        return {"saved": ok}

    return {"error": f"未知工具 {name}"}


def judge(url, client=None, conn=None, today=None, analyzer=None, max_steps=6):
    repo_full = parse_repo(url)

    conn = conn or cache.connect()
    client = client or ChatClient()
    analyzer = analyzer or analyze.analyze_repo

    cached = cache.lookup(conn, repo_full, today)
    if cached:
        return {
            "repo": repo_full,
            "cached": True,
            "week": cached["week"],
            "result": cached["result"],
            "reason": cached["reason"],
            "highlight": cached.get("highlight") or "",
            "panels": cached.get("panels") or [],
            "metrics": cached.get("metrics"),
            "source": cached["source"],
        }

    messages = [
        {"role": "system", "content": _load_prompt()},
        {"role": "user", "content": f"请评估这个项目的健康度：https://github.com/{repo_full}"},
    ]

    state = {"metrics": None, "saved": None}
    answer = ""

    for _ in range(max_steps):
        message = client.complete(messages, TOOLS)
        calls = message.get("tool_calls") or []

        if not calls:
            answer = message.get("content") or ""
            break

        messages.append(
            {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": calls,
            }
        )
        for call in calls:
            function = call.get("function", {})
            try:
                args = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _run_tool(function.get("name", ""), args, conn, analyzer, today, state)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    else:
        raise RuntimeError(f"{max_steps} 轮内没有得到结论")

    saved = state.get("saved") or {}
    return {
        "repo": repo_full,
        "cached": False,
        "answer": answer,
        "result": saved.get("result"),
        "reason": saved.get("reason"),
        "highlight": saved.get("highlight", ""),
        "panels": saved.get("panels", []),
        "metrics": state.get("metrics"),
    }


def draw_chart(outcome, out_path):
    repo = outcome["repo"]
    metrics = outcome.get("metrics")
    if not metrics:
        owner, name = repo.split("/")
        metrics = analyze.analyze_repo(owner, name)
        if "error" in metrics:
            raise RuntimeError(metrics["error"])

    owner, name = repo.split("/")
    downloads, _ = analyze.fetch_downloads(name.lower())
    weeks, _ = analyze.fetch_weeks(owner, name)

    verdict = outcome.get("result")
    if not verdict:
        for line in (outcome.get("answer") or "").splitlines():
            if line.startswith("结论"):
                verdict = line.split("：", 1)[-1].strip()
                break
    verdict = verdict or "不健康"

    return chart.render(
        out_path,
        repo=repo,
        verdict=verdict,
        reason=outcome.get("reason") or "",
        metrics=metrics,
        series={"downloads": downloads or [], "weeks": weeks or []},
        panels=outcome.get("panels"),
        highlight=outcome.get("highlight") or "",
    )


def main(argv):
    if not argv:
        raise SystemExit("用法: python agent.py <链接> [--chart 输出.png]")

    args = list(argv)
    chart_path = None
    if "--chart" in args:
        index = args.index("--chart")
        if index + 1 >= len(args):
            raise SystemExit("--chart 后面要跟输出路径")
        chart_path = args[index + 1]
        del args[index:index + 2]

    if len(args) != 1:
        raise SystemExit("用法: python agent.py <链接> [--chart 输出.png]")

    try:
        outcome = judge(args[0])
    except (RepoNameError, RuntimeError) as exc:
        raise SystemExit(str(exc))

    if outcome.get("cached"):
        print(f"{outcome['repo']}  {outcome['result']}（缓存 {outcome['week']}）")
        print(f"理由：{outcome['reason']}")
    else:
        print(outcome["answer"])

    if chart_path:
        try:
            saved = draw_chart(outcome, chart_path)
            print(f"\n图表已保存：{saved}")
        except Exception as exc:
            print(f"\n图表生成失败（结论不受影响）：{exc}")


if __name__ == "__main__":
    main(sys.argv[1:])

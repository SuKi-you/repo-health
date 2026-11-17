import json
import re
from pathlib import Path

import analyze
import cache
from llm import ChatClient

PROMPT_FILE = Path("PROMPT.md")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
GH_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s?#]+)")

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
            "description": "保存最终判定结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "result": {"type": "string", "enum": ["健康", "不健康"]},
                    "reason": {"type": "string"},
                },
                "required": ["owner", "repo", "result", "reason"],
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


def _run_tool(name, args, conn, analyzer, today):
    owner = args.get("owner", "")
    repo = args.get("repo", "")
    if not (NAME_RE.match(owner) and NAME_RE.match(repo)):
        return {"error": "owner/repo 格式不合法"}
    full = f"{owner}/{repo}"

    if name == "lookup_judgment":
        row = cache.lookup(conn, full, today)
        return row or {"hit": False}

    if name == "analyze_repo":
        return analyzer(owner, repo)

    if name == "save_judgment":
        ok = cache.save(
            conn, full, args.get("result", ""), args.get("reason", ""), "llm", today
        )
        return {"saved": ok}

    return {"error": f"未知工具 {name}"}


def judge(url, client=None, conn=None, today=None, analyzer=None, max_steps=6):
    repo_full = parse_repo(url)
    owner, repo = repo_full.split("/")

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
            "source": cached["source"],
        }

    messages = [
        {"role": "system", "content": _load_prompt()},
        {
            "role": "user",
            "content": f"请评估这个项目的健康度：https://github.com/{repo_full}",
        },
    ]

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
            fn = call.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _run_tool(fn.get("name", ""), args, conn, analyzer, today)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    else:
        raise RuntimeError(f"{max_steps} 轮内没有得到结论")

    return {"repo": repo_full, "cached": False, "answer": answer}


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("用法: python agent.py <GitHub 链接 或 owner/repo>")

    try:
        outcome = judge(sys.argv[1])
    except RepoNameError as exc:
        raise SystemExit(str(exc))
    except RuntimeError as exc:
        raise SystemExit(str(exc))

    if outcome.get("cached"):
        print(f"{outcome['repo']}  {outcome['result']}（缓存 {outcome['week']}）")
        print(f"理由：{outcome['reason']}")
    else:
        print(outcome["answer"])

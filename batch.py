import concurrent.futures
import time
from pathlib import Path

import agent
import cache


def _judge_one(url, today, analyzer, db_path):
    conn = cache.connect(db_path)
    try:
        return agent.judge(url, conn=conn, today=today, analyzer=analyzer)
    except Exception as exc:
        return {"repo": url, "error": str(exc)}
    finally:
        conn.close()


def judge_many(urls, workers=4, today=None, analyzer=None, db_path=cache.DB):
    started = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_judge_one, url, today, analyzer, db_path) for url in urls
        ]
        for future in futures:
            results.append(future.result())
    return {"items": results, "elapsed": round(time.time() - started, 1)}


def verdict_of(item):
    if item.get("error"):
        return "错误"
    if item.get("cached"):
        return item.get("result", "?")
    for line in (item.get("answer") or "").splitlines():
        if line.startswith("结论"):
            return line.split("：", 1)[-1].strip()
    return "?"


def load_targets(args):
    if len(args) == 1 and Path(args[0]).exists():
        lines = Path(args[0]).read_text(encoding="utf-8").splitlines()
        return [
            line.strip()
            for line in lines
            if line.strip() and not line.strip().startswith("#")
        ]
    return args


def width(text):
    return sum(2 if ord(ch) > 127 else 1 for ch in text)


def pad(text, size):
    return text + " " * max(0, size - width(text))


def main(argv):
    if not argv:
        raise SystemExit("用法: python batch.py <repos.txt> | <链接1> <链接2> ...")

    targets = load_targets(argv)
    outcome = judge_many(targets, workers=4)

    print(pad("仓库", 34) + pad("结论", 10) + pad("来源", 8))
    print("-" * 54)
    for item in outcome["items"]:
        source = "缓存" if item.get("cached") else "模型"
        if item.get("error"):
            source = "-"
        print(pad(item.get("repo", "?"), 34) + pad(verdict_of(item), 10) + pad(source, 8))

    healthy = sum(1 for i in outcome["items"] if verdict_of(i) == "健康")
    bad = sum(1 for i in outcome["items"] if verdict_of(i) == "不健康")
    errors = sum(1 for i in outcome["items"] if i.get("error"))
    print()
    print(f"共 {len(outcome['items'])} 个 | 健康 {healthy} | 不健康 {bad} | 错误 {errors}")
    print(f"耗时 {outcome['elapsed']} 秒")


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])

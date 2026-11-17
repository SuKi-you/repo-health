import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, request, send_from_directory

import agent
import analyze

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"

app = Flask(__name__, static_folder=None)


def extract_verdict(outcome):
    if outcome.get("result"):
        return outcome["result"]
    for line in (outcome.get("answer") or "").splitlines():
        if line.startswith("结论"):
            return line.split("：", 1)[-1].strip()
    return "不健康"


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/<path:filename>")
def assets(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.post("/api/analyze")
def api_analyze():
    payload = request.get_json(silent=True) or {}
    target = (payload.get("url") or "").strip()
    if not target:
        return jsonify({"error": "请输入仓库链接"}), 400

    try:
        repo = agent.parse_repo(target)
    except agent.RepoNameError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        outcome = agent.judge(target)
    except Exception as exc:
        return jsonify({"error": f"分析失败：{exc}"}), 502

    metrics = outcome.get("metrics")
    owner, name = repo.split("/")
    if not metrics or "error" in metrics:
        metrics = analyze.analyze_repo(owner, name)
        if "error" in metrics:
            return jsonify({"error": metrics["error"]}), 502

    downloads, _ = analyze.fetch_downloads(name.lower())
    weeks, _ = analyze.fetch_weeks(owner, name)

    return jsonify({
        "repo": repo,
        "verdict": extract_verdict(outcome),
        "reason": outcome.get("reason") or "",
        "cached": bool(outcome.get("cached")),
        "week": outcome.get("week"),
        "metrics": metrics,
        "series": {
            "downloads": downloads or [],
            "weeks": weeks or [],
        },
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860, debug=False)

import os
import statistics
import time
from datetime import date, datetime, timedelta, timezone

import requests

API = "https://api.github.com"
PYPI = "https://pypistats.org/api/packages/{}/overall"
UA = {"User-Agent": "oss-health"}
RETRY_CODES = {202, 429, 500, 502, 503, 504}


def _github_headers():
    headers = dict(UA)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch(url, headers=None, tries=5, timeout=60):
    headers = headers or UA
    code = None
    for _ in range(tries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException:
            time.sleep(2)
            continue
        code = resp.status_code
        if code == 200:
            return resp.json(), 200
        if code in RETRY_CODES:
            time.sleep(3)
            continue
        return None, code
    return None, code


def to_date(value):
    if not value:
        return None
    if "T" in value:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    return date.fromisoformat(value)


def days_between(start, end):
    if start is None or end is None:
        return None
    return (end - start).days


def fetch_repo(owner, repo):
    return _fetch(f"{API}/repos/{owner}/{repo}", _github_headers())


def fetch_release(owner, repo):
    return _fetch(f"{API}/repos/{owner}/{repo}/releases/latest", _github_headers())


def fetch_issues(owner, repo):
    url = f"{API}/repos/{owner}/{repo}/issues?state=all&per_page=100&sort=created&direction=desc"
    return _fetch(url, _github_headers())


def fetch_weeks(owner, repo):
    return _fetch(f"{API}/repos/{owner}/{repo}/stats/commit_activity", _github_headers())


def fetch_contributors(owner, repo):
    return _fetch(f"{API}/repos/{owner}/{repo}/contributors?per_page=100", _github_headers())


def fetch_downloads(package):
    data, code = _fetch(PYPI.format(package), UA)
    if code != 200 or not data:
        return [], code
    rows = [r for r in data.get("data", []) if r.get("category") == "without_mirrors"]
    return sorted((r["date"], r["downloads"]) for r in rows), 200


def _median_close_days(issues, today):
    spans = []
    for item in issues:
        closed = to_date(item.get("closed_at"))
        created = to_date(item.get("created_at"))
        if closed and created:
            spans.append((closed - created).days)
    return statistics.median(spans) if spans else None


def _open_age_days(issues, today):
    ages = [
        (today - to_date(item["created_at"])).days
        for item in issues
        if item.get("closed_at") is None and item.get("created_at")
    ]
    return sum(ages) / len(ages) if ages else None


def _newest_issue_age(issues, today):
    dates = [to_date(item["created_at"]) for item in issues if item.get("created_at")]
    return (today - max(dates)).days if dates else None


def _sample_span(issues):
    dates = [to_date(item["created_at"]) for item in issues if item.get("created_at")]
    return (max(dates) - min(dates)).days if len(dates) > 1 else None


def _commits_4w(weeks, today):
    complete = [
        w for w in weeks
        if datetime.fromtimestamp(w["week"], tz=timezone.utc).date().toordinal() + 7
        <= today.toordinal()
    ]
    complete.sort(key=lambda w: w["week"], reverse=True)
    last4 = complete[:4]
    if not last4:
        return None
    return sum(w.get("total", 0) for w in last4) / 4


def _download_stats(series, today):
    if not series:
        return None, None, None
    values = [n for _, n in series]
    week_total = sum(
        n for d, n in series
        if to_date(d) and 0 <= (today - to_date(d)).days < 7
    )
    if len(values) < 56:
        return week_total, None, None
    recent = sum(values[-28:]) / 28
    before = sum(values[-56:-28]) / 28
    trend = recent / before - 1 if before else None
    weekly = [sum(values[i:i + 7]) / 7 for i in range(0, len(values) - 6, 7)]
    changes = [
        (weekly[i + 1] - weekly[i]) / weekly[i]
        for i in range(len(weekly) - 1)
        if weekly[i]
    ]
    noise = statistics.pstdev(changes) if len(changes) > 1 else None
    return week_total, trend, noise


def build_metrics(raw, today=None):
    today = today or date.today()
    repo = raw["repo"]
    release = raw.get("release") or {}
    issues_all = raw.get("issues") or []
    weeks = raw.get("weeks") or []
    contribs = raw.get("contribs") or []
    downloads = raw.get("downloads") or []

    issues = [i for i in issues_all if "pull_request" not in i]

    week_total, trend, noise = _download_stats(downloads, today)

    total_contrib = sum(c.get("contributions", 0) for c in contribs)
    top1 = max((c.get("contributions", 0) for c in contribs), default=None)

    metrics = {
        "full_name": repo.get("full_name"),
        "language": repo.get("language"),
        "archived": bool(repo.get("archived")),
        "release_age": days_between(to_date(release.get("published_at")), today),
        "push_age": days_between(to_date(repo.get("pushed_at")), today),
        "commits_4w": _commits_4w(weeks, today),
        "newest_issue_age": _newest_issue_age(issues, today),
        "median_close": _median_close_days(issues, today),
        "unclosed_ratio": (
            sum(1 for i in issues if i.get("closed_at") is None) / len(issues)
            if issues else None
        ),
        "stuck_days": _open_age_days(issues, today),
        "sample_span": _sample_span(issues),
        "dl_week": week_total,
        "dl_trend": trend,
        "dl_noise": noise,
        "top1_share": (top1 / total_contrib) if total_contrib else None,
    }

    missing = [k for k, v in metrics.items() if v is None]
    metrics["missing"] = sorted(set(missing))
    return metrics


def analyze_repo(owner, repo, package=None, today=None):
    today = today or date.today()

    repo_data, code = fetch_repo(owner, repo)
    if code != 200 or not repo_data:
        return {"error": f"无法获取仓库 {owner}/{repo}", "status": code}

    release, _ = fetch_release(owner, repo)
    issues, _ = fetch_issues(owner, repo)
    weeks, _ = fetch_weeks(owner, repo)
    contribs, _ = fetch_contributors(owner, repo)
    downloads, _ = fetch_downloads(package or repo.lower())

    raw = {
        "repo": repo_data,
        "release": release,
        "issues": issues,
        "weeks": weeks,
        "contribs": contribs,
        "downloads": downloads,
    }
    metrics = build_metrics(raw, today)
    metrics["package"] = package or repo.lower()
    return metrics


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2 or "/" not in sys.argv[1]:
        raise SystemExit("用法: python analyze.py owner/repo")
    owner_name, repo_name = sys.argv[1].split("/", 1)
    result = analyze_repo(owner_name, repo_name)
    print(json.dumps(result, ensure_ascii=False, indent=2))

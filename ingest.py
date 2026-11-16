import os
import sqlite3
import time
from datetime import date
import requests

REPOS = []
with open("config/repos.txt",encoding="utf-8") as f:
    for line in f:
        name = line.strip()
        if name and not name.startswith("#"):
            REPOS.append(name)
print("要抓",len(REPOS),"个仓库")

TODAY = date.today().isoformat()#获取今天的日期，并把它转换成标准格式的文本字符串。

HEADERS = {"User-Agent": "learn"}
TOKEN = os.environ.get("GITHUB_TOKEN")
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"
print("token:", "已配置" if TOKEN else "未配置")


def fetch(url):
    for _ in range(6):
        r = requests.get(url, headers=HEADERS)
        if r.status_code == 202:
            time.sleep(3)
            continue
        if r.status_code == 200:
            return r.json(), 200
        return None, r.status_code
    return None, 202


conn = sqlite3.connect("data/oss_health.db")
conn.execute("""
    CREATE TABLE IF NOT EXISTS repos_info (
        date               TEXT    NOT NULL,
        repo_id            INTEGER NOT NULL,
        full_name          TEXT,
        language           TEXT,
        stars              INTEGER,
        forks              INTEGER,
        open_issues        INTEGER,
        pushed_at          TEXT,
        latest_release_tag TEXT,
        latest_release_at  TEXT,
        PRIMARY KEY (date, repo_id)
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS issues (
        repo_id         INTEGER NOT NULL,
        issue_id        INTEGER NOT NULL,
        number          INTEGER,
        state           TEXT,
        created_at      TEXT,
        closed_at       TEXT,
        comments        INTEGER,
        is_pull_request INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (repo_id, issue_id)
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS commit_weekly (
        repo_id INTEGER NOT NULL,
        week    INTEGER NOT NULL,
        commits INTEGER,
        PRIMARY KEY (repo_id, week)
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS contributors (
        repo_id       INTEGER NOT NULL,
        login         TEXT    NOT NULL,
        contributions INTEGER,
        PRIMARY KEY (repo_id, login)
    )
""")

SQL = """
INSERT INTO repos_info VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(date, repo_id) DO UPDATE SET
    stars = excluded.stars, forks = excluded.forks,
    open_issues = excluded.open_issues, pushed_at = excluded.pushed_at,
    latest_release_tag = excluded.latest_release_tag,
    latest_release_at  = excluded.latest_release_at
"""

SQL_ISSUE = """
INSERT INTO issues VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(repo_id, issue_id) DO UPDATE SET
    state = excluded.state,
    closed_at = excluded.closed_at,
    comments = excluded.comments
"""

SQL_COMMIT = """
INSERT INTO commit_weekly VALUES (?, ?, ?)
ON CONFLICT(repo_id, week) DO UPDATE SET commits = excluded.commits
"""

SQL_CONTRIB = """
INSERT INTO contributors VALUES (?, ?, ?)
ON CONFLICT(repo_id, login) DO UPDATE SET contributions = excluded.contributions
"""

for name in REPOS:
    #给爬虫程序上防弹衣：如果Github拒绝了请求，它会自动跳过这个项目，继续抓下一个，从而防止程序崩溃。
    d, code = fetch(f"https://api.github.com/repos/{name}")
    if code != 200:
        print(f"{name:28} 跳过:HTTP{code}")
        continue

    rel, _ = fetch(f"https://api.github.com/repos/{name}/releases/latest")
    tag = rel["tag_name"] if rel else None
    released_at = rel["published_at"] if rel else None

    conn.execute(SQL, (TODAY, d["id"], d["full_name"], d.get("language"),
                            d["stargazers_count"], d["forks_count"],
                            d["open_issues_count"], d["pushed_at"],
                            tag, released_at))

    issues, _ = fetch(f"https://api.github.com/repos/{name}/issues?state=all&per_page=100")
    issues = issues or []
    for it in issues:
        conn.execute(SQL_ISSUE, (d["id"], it["id"], it.get("number"), it.get("state"),
                                 it.get("created_at"), it.get("closed_at"),
                                 it.get("comments", 0),
                                 1 if "pull_request" in it else 0))

    commits, _ = fetch(f"https://api.github.com/repos/{name}/stats/commit_activity")
    commits = commits or []
    for w in commits:
        conn.execute(SQL_COMMIT, (d["id"], w["week"], w["total"]))

    contribs, _ = fetch(f"https://api.github.com/repos/{name}/contributors?per_page=100")
    contribs = contribs or []
    for c in contribs:
        conn.execute(SQL_CONTRIB, (d["id"], c.get("login"), c.get("contributions")))

    print(f"{name:28} {d['stargazers_count']:>7} stars  {str(tag):12} issues={len(issues):3} weeks={len(commits):2} contribs={len(contribs):3}")

conn.commit()

rows=conn.execute("""
    SELECT full_name,MIN(stars),MAX(stars),MAX(stars)-MIN(stars)
    FROM repos_info
    GROUP BY repo_id
    ORDER BY 4 DESC
""").fetchall()
for r in rows:
    print(r)

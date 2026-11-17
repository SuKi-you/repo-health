import os
import sqlite3
import time
from datetime import date
import requests

REPOS = []
with open("config/repos.txt",encoding="utf-8") as f:
    for line in f:
        name = line.strip()#把字符串开头和结尾的空格、制表符、换行符都去除
        if name and not name.startswith("#"):#如果这一行是空的或者是注释，那么直接过滤掉即可
            REPOS.append(name)
print("抓取",len(REPOS),"个仓库")

PYPI = {}
with open("config/pypi.txt",encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            repo, pkg = line.split("=", 1)
            PYPI[repo.strip()] = pkg.strip()

TODAY = date.today().isoformat()#获取今天的日期，并把它转换成标准格式的文本字符串。

HEADERS = {"User-Agent": "learn"}
TOKEN = os.environ.get("GITHUB_TOKEN")
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"
print("token:", "已配置" if TOKEN else "未配置")

PLAIN = {"User-Agent": "learn"}


def fetch(url, headers=None):#增强鲁棒性
    code = None
    for _ in range(6):
        try:
            r = requests.get(url, headers=headers or HEADERS, timeout=60)
        except requests.RequestException:
            time.sleep(3)
            continue
        code = r.status_code
        if code == 200:
            return r.json(), 200
        if code in (202, 429) or code >= 500:
            time.sleep(5)
            continue
        return None, code
    return None, code


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
        archived           INTEGER,
        PRIMARY KEY (date, repo_id)
    )
""")
cols = [c[1] for c in conn.execute("PRAGMA table_info(repos_info)")]
if "archived" not in cols:
    conn.execute("ALTER TABLE repos_info ADD COLUMN archived INTEGER")
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
conn.execute("""
    CREATE TABLE IF NOT EXISTS downloads (
        date      TEXT    NOT NULL,
        package   TEXT    NOT NULL,
        downloads INTEGER,
        PRIMARY KEY (date, package)
    )
""")

#表的操作逻辑

SQL = """
INSERT INTO repos_info VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(date, repo_id) DO UPDATE SET
    stars = excluded.stars, forks = excluded.forks,
    open_issues = excluded.open_issues, pushed_at = excluded.pushed_at,
    latest_release_tag = excluded.latest_release_tag,
    latest_release_at  = excluded.latest_release_at,
    archived           = excluded.archived
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

SQL_DL = """
INSERT INTO downloads VALUES (?, ?, ?)
ON CONFLICT(date, package) DO UPDATE SET downloads = excluded.downloads
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
                            tag, released_at, d.get("archived")))

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

    pkg = PYPI.get(name)
    dl_rows = 0
    if pkg:
        data, _ = fetch(f"https://pypistats.org/api/packages/{pkg}/overall", headers=PLAIN)
        for x in (data or {}).get("data", []):
            if x["category"] == "without_mirrors":
                conn.execute(SQL_DL, (x["date"], pkg, x["downloads"]))
                dl_rows += 1
        time.sleep(1)

    print(f"{name:28} {d['stargazers_count']:>7} stars  {str(tag):12} issues={len(issues):3} weeks={len(commits):2} contribs={len(contribs):3} dl={dl_rows:3}")

conn.commit()

rows=conn.execute("""
    SELECT full_name,MIN(stars),MAX(stars),MAX(stars)-MIN(stars)
    FROM repos_info
    GROUP BY repo_id
    ORDER BY 4 DESC
""").fetchall()
for r in rows:
    print(r)

import sqlite3
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

conn = sqlite3.connect("data/oss_health.db")
conn.execute("""
    CREATE TABLE IF NOT EXISTS repos_info (
        date        TEXT    NOT NULL,
        repo_id     INTEGER NOT NULL,
        full_name   TEXT,
        language    TEXT,
        stars       INTEGER,
        forks       INTEGER,
        open_issues INTEGER,
        pushed_at   TEXT,
        PRIMARY KEY (date, repo_id)
    )
""")

SQL = """
INSERT INTO repos_info VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(date, repo_id) DO UPDATE SET
    stars = excluded.stars, forks = excluded.forks,
    open_issues = excluded.open_issues, pushed_at = excluded.pushed_at
"""

for name in REPOS:
    #给爬虫程序上防弹衣：如果Github拒绝了请求，它会自动跳过这个项目，继续抓下一个，从而防止程序崩溃。        
    r = requests.get(f"https://api.github.com/repos/{name}",
                     headers={"User-Agent": "learn"})
    if r.status_code !=200:
        print(f"{name:28} 跳过:HTTP{r.status_code}")
        continue

    d=r.json()
    conn.execute(SQL, (TODAY, d["id"], d["full_name"], d["language"],
                       d["stargazers_count"], d["forks_count"],
                       d["open_issues_count"], d["pushed_at"]))
    print(f"{name:28} {d['stargazers_count']:>7} stars")
conn.commit()

#涨幅，把数据库里积攒的历史数据拿出来，算出了每个项目在这段时间内“一共涨了多少颗星”，并按涨粉数量从高到低排名次
rows=conn.execute("""
    SELECT full_name,MIN(stars),MAX(stars),MAX(stars)-MIN(stars)
    FROM repos_info
    GROUP BY repo_id
    ORDER BY 4 DESC
""").fetchall()
for r in rows:
    print(r)

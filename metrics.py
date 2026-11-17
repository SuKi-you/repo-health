import sqlite3
from datetime import date, datetime

DB = "data/oss_health.db"
TODAY = date.today()


def to_date(s):
    if not s:
        return None
    if "T" in s:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    return date.fromisoformat(s)


def days_since(s):
    d = to_date(s)
    return None if d is None else (TODAY - d).days


def fmt_days(v):
    return "-" if v is None else f"{v}天"


def width(s):
    return sum(2 if ord(c) > 127 else 1 for c in s)


def lpad(s, n):
    return " " * max(0, n - width(s)) + s


def rpad(s, n):
    return s + " " * max(0, n - width(s))


def load_latest(conn):
    return conn.execute("""
        SELECT repo_id, full_name, latest_release_at, pushed_at, archived
        FROM repos_info
        WHERE date = (SELECT MAX(date) FROM repos_info)
        ORDER BY full_name
    """).fetchall()


def main():
    conn = sqlite3.connect(DB)
    rows = load_latest(conn)

    print(rpad("仓库", 30) + lpad("发版距今", 12) + lpad("push距今", 12) + lpad("归档", 8))
    print("-" * 62)
    for _, full_name, rel, pushed, archived in rows:
        print(
            rpad(full_name, 30)
            + lpad(fmt_days(days_since(rel)), 12)
            + lpad(fmt_days(days_since(pushed)), 12)
            + lpad("是" if archived else "否", 8)
        )


if __name__ == "__main__":
    main()

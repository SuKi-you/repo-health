import sqlite3
import statistics
from datetime import date, datetime, timedelta, timezone

DB = "data/oss_health.db"#设定数据库路径
PYPI_FILE = "config/pypi.txt"
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


def width(s):
    return sum(2 if ord(c) > 127 else 1 for c in s)


def lpad(s, n):
    return " " * max(0, n - width(s)) + s


def rpad(s, n):
    return s + " " * max(0, n - width(s))


def fmt_days(v):
    if v is None:
        return "-"
    return f"{v:.1f}天" if float(v) % 1 else f"{int(v)}天"


def fmt_ratio(v):
    return "-" if v is None else f"{v * 100:.0f}%"


def fmt_pct(v):
    return "-" if v is None else f"{v * 100:+.0f}%"


def fmt_num(v, digits=1):
    return "-" if v is None else f"{v:.{digits}f}"


def load_latest(conn):
    data = {}
    rows = conn.execute("""
        SELECT repo_id, full_name, latest_release_at, pushed_at, archived
        FROM repos_info
        WHERE date = (SELECT MAX(date) FROM repos_info)
        ORDER BY full_name
    """).fetchall()
    for repo_id, full_name, rel, pushed, archived in rows:
        data[repo_id] = {
            "name": full_name,
            "release_age": days_since(rel),
            "push_age": days_since(pushed),
            "archived": archived,
        }
    return data


def load_pypi_map():
    mapping = {}
    with open(PYPI_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                repo, pkg = line.split("=", 1)
                mapping[repo.strip()] = pkg.strip()
    return mapping


def resolve_packages(data):
    repo_to_pkg = load_pypi_map()
    pkg_to_repo = {}
    for repo_id, item in data.items():
        pkg = repo_to_pkg.get(item["name"])
        if pkg:
            pkg_to_repo[pkg] = repo_id
    return pkg_to_repo


# 批 2：issue 未关闭占比、近 4 周周均 commit、top1 贡献者占比、近 7 天下载量
def batch_activity(conn, data, pkg_to_repo):
    for repo_id, ratio in conn.execute("""
        SELECT repo_id,
               SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*)
        FROM issues WHERE is_pull_request = 0
        GROUP BY repo_id
    """):
        if repo_id in data:
            data[repo_id]["unclosed_ratio"] = ratio

    weeks = {}
    for repo_id, week, commits in conn.execute(
        "SELECT repo_id, week, commits FROM commit_weekly"
    ):
        weeks.setdefault(repo_id, []).append((week, commits or 0))
    for repo_id, items in weeks.items():
        if repo_id not in data:
            continue
        complete = [
            (w, c) for w, c in items
            if datetime.fromtimestamp(w, tz=timezone.utc).date().toordinal() + 7
            <= TODAY.toordinal()
        ]
        complete.sort(reverse=True)
        last4 = complete[:4]
        data[repo_id]["commits_4w"] = sum(c for _, c in last4) / 4 if last4 else None

    for repo_id, top, total in conn.execute("""
        SELECT repo_id, MAX(contributions), SUM(contributions)
        FROM contributors GROUP BY repo_id
    """):
        if repo_id in data and total:
            data[repo_id]["top1_share"] = top / total

    cutoff = (TODAY - timedelta(days=7)).isoformat()
    for package, total in conn.execute(
        "SELECT package, SUM(downloads) FROM downloads WHERE date >= ? GROUP BY package",
        (cutoff,),
    ):
        repo_id = pkg_to_repo.get(package)
        if repo_id in data:
            data[repo_id]["dl_week"] = total


# 批 3：最新 issue 距今（还有没有活跃需求）、未关闭 issue 的平均滞留天数
def batch_issues(conn, data):
    grouped = {}
    for repo_id, created, closed in conn.execute(
        "SELECT repo_id, created_at, closed_at FROM issues WHERE is_pull_request = 0"
    ):
        grouped.setdefault(repo_id, []).append((created, closed))

    for repo_id, items in grouped.items():
        if repo_id not in data:
            continue
        created_dates = [to_date(c) for c, _ in items if c]
        if created_dates:
            data[repo_id]["newest_issue_age"] = (TODAY - max(created_dates)).days
        open_days = [(TODAY - to_date(c)).days for c, closed in items if closed is None and c]
        data[repo_id]["stuck_days"] = sum(open_days) / len(open_days) if open_days else None


# 批 4：issue 中位关闭天数、样本时间跨度（跨仓库比较是否成立的前提）
def batch_close_time(conn, data):
    grouped = {}
    for repo_id, created, closed in conn.execute(
        "SELECT repo_id, created_at, closed_at FROM issues WHERE is_pull_request = 0"
    ):
        grouped.setdefault(repo_id, []).append((created, closed))

    for repo_id, items in grouped.items():
        if repo_id not in data:
            continue
        created_dates = [to_date(c) for c, _ in items if c]
        if created_dates:
            data[repo_id]["sample_span"] = (max(created_dates) - min(created_dates)).days
        close_days = [(to_date(cl) - to_date(c)).days for c, cl in items if c and cl]
        if close_days:
            data[repo_id]["median_close"] = statistics.median(close_days)


# 批 5：下载量 4 周趋势（近 4 周均值 vs 之前 4 周均值），同时给出周环比噪声
def batch_download_trend(conn, data, pkg_to_repo):
    series = {}
    for package, _, downloads in conn.execute(
        "SELECT package, date, downloads FROM downloads ORDER BY date"
    ):
        series.setdefault(package, []).append(downloads)

    for package, values in series.items():
        repo_id = pkg_to_repo.get(package)
        if repo_id not in data:
            continue
        if len(values) < 56:
            data[repo_id]["dl_trend"] = None
            data[repo_id]["dl_noise"] = None
            continue
        recent = sum(values[-28:]) / 28
        before = sum(values[-56:-28]) / 28
        data[repo_id]["dl_trend"] = recent / before - 1 if before else None

        weekly = [sum(values[i:i + 7]) / 7 for i in range(0, len(values) - 6, 7)]
        changes = [
            (weekly[i + 1] - weekly[i]) / weekly[i]
            for i in range(len(weekly) - 1)
            if weekly[i]
        ]
        data[repo_id]["dl_noise"] = statistics.pstdev(changes) if len(changes) > 1 else None


# 批 6：star 30 日增速，数据跨度不足 25 天时留空，避免拿 1 天数据冒充月增速
def batch_star_growth(conn, data):
    grouped = {}
    for repo_id, d, stars in conn.execute(
        "SELECT repo_id, date, stars FROM repos_info ORDER BY date"
    ):
        grouped.setdefault(repo_id, []).append((to_date(d), stars))

    for repo_id, items in grouped.items():
        if repo_id not in data:
            continue
        span = (items[-1][0] - items[0][0]).days
        data[repo_id]["star_span"] = span
        if span < 25:
            data[repo_id]["star_growth"] = None
            continue
        first, last = items[0][1], items[-1][1]
        data[repo_id]["star_growth"] = (last - first) / first if first else None


def show_table_a(data):
    print(rpad("仓库", 30) + lpad("发版距今", 12) + lpad("push距今", 12)
          + lpad("周commit", 11) + lpad("未关闭", 9) + lpad("top1", 8))
    print("-" * 82)
    for item in sorted(data.values(), key=lambda x: x["name"]):
        print(
            rpad(item["name"], 30)
            + lpad(fmt_days(item.get("release_age")), 12)
            + lpad(fmt_days(item.get("push_age")), 12)
            + lpad(fmt_num(item.get("commits_4w")), 11)
            + lpad(fmt_ratio(item.get("unclosed_ratio")), 9)
            + lpad(fmt_ratio(item.get("top1_share")), 8)
        )


def show_table_b(data):
    print()
    print(rpad("仓库", 30) + lpad("最新issue", 12) + lpad("滞留天数", 12)
          + lpad("中位关闭", 12) + lpad("样本跨度", 12))
    print("-" * 78)
    for item in sorted(data.values(), key=lambda x: x["name"]):
        print(
            rpad(item["name"], 30)
            + lpad(fmt_days(item.get("newest_issue_age")), 12)
            + lpad(fmt_days(item.get("stuck_days")), 12)
            + lpad(fmt_days(item.get("median_close")), 12)
            + lpad(fmt_days(item.get("sample_span")), 12)
        )


def fmt_count(v):
    if v is None:
        return "-"
    if v >= 100000000:
        return f"{v / 100000000:.2f}亿"
    if v >= 10000:
        return f"{v / 10000:.0f}万"
    return str(v)


def fmt_trend(v, noise):
    if v is None:
        return "-"
    if noise is None:
        return f"{v * 100:+.0f}%"
    return f"{v * 100:+.0f}%±{noise * 100:.0f}%"


def show_table_c(data):
    print()
    print(rpad("仓库", 30) + lpad("归档", 6) + lpad("周下载", 12)
          + lpad("下载4周", 14) + lpad("star30", 10))
    print("-" * 72)
    for item in sorted(data.values(), key=lambda x: x["name"]):
        print(
            rpad(item["name"], 30)
            + lpad("是" if item.get("archived") else "否", 6)
            + lpad(fmt_count(item.get("dl_week")), 12)
            + lpad(fmt_trend(item.get("dl_trend"), item.get("dl_noise")), 14)
            + lpad(fmt_pct(item.get("star_growth")), 10)
        )


def main():
    conn = sqlite3.connect(DB)
    data = load_latest(conn)
    pkg_to_repo = resolve_packages(data)
    batch_activity(conn, data, pkg_to_repo)
    batch_issues(conn, data)
    batch_close_time(conn, data)
    batch_download_trend(conn, data, pkg_to_repo)
    batch_star_growth(conn, data)
    show_table_a(data)
    show_table_b(data)
    show_table_c(data)


if __name__ == "__main__":
    main()

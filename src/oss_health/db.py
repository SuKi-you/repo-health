"""SQLite 接入层。

分区约定（AI + 自己写 的混合模式）：
  🟢 connect() / init_db() / __main__ 是样板，读懂即可，不用能默写。
  🔴 SCHEMA 是红区 —— 这是面试第一问「你表为什么这么设计」，必须你自己写。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("data/oss_health.db")


# ============================================================================
# 🔴 红区：你来写
# ============================================================================
# 要求：四张表，字段自己定，但必须能回答下面四个问题。
# 想清楚再动笔 —— 先到 NOTES.md 第 2 节写出你的答案，再来这里写 SQL。
#
#   Q1  GitHub 仓库可以改名（pandas-dev/pandas 曾经改过）。用 full_name 当主键，
#       改名后历史就断了。该用什么当主键？
#
#   Q2  每天抓一次，同一天跑两遍不能产生两行。主键该怎么设，
#       才能让「重复插入」被数据库自己挡住，而不是靠你在 Python 里写去重？
#
#   Q3  /issues 接口返回的列表里混着 Pull Request。分析「issue 关闭速度」时
#       必须把它们分开。是入库时就过滤掉，还是存下来打个标记？为什么？
#
#   Q4  带 If-None-Match 请求时，GitHub 命中缓存会返回 304 —— 而 304 没有 body。
#       要让程序在这种情况下还原出上一次的数据，缓存表必须存哪几列？
#
# 提示：CREATE TABLE IF NOT EXISTS；主键写对；该加的索引加上。
# ============================================================================

SCHEMA = """
-- TODO: repos / snapshots / issues / http_cache 四张表
"""


def connect(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """打开连接：建目录、开外键、让行能按列名取值。"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # isolation_level=None 表示关掉 Python 的隐式事务，事务由调用方显式 BEGIN/COMMIT
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row  # 这样才能 row["stars"]，而不是 row[3]
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> list[str]:
    """执行 SCHEMA，返回建完后库里有哪些业务表。"""
    if not SCHEMA.strip() or "TODO" in SCHEMA:
        raise SystemExit(
            "SCHEMA 还是空的。\n"
            "这是 M1 的任务：先去 NOTES.md 第 2 节回答那四个问题，再回来写四张表。"
        )

    conn.executescript(SCHEMA)

    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [row["name"] for row in rows]


if __name__ == "__main__":
    # 自检入口：python -m oss_health.db
    connection = connect()
    tables = init_db(connection)
    print(f"建表成功，共 {len(tables)} 张表：")
    for name in tables:
        columns = connection.execute(f"PRAGMA table_info({name})").fetchall()
        described = ", ".join(f"{col['name']}:{col['type'] or '?'}" for col in columns)
        print(f"  - {name}({described})")

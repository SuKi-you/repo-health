import os
import textwrap
from datetime import date, datetime
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(".cache") / "mpl"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as ticker
import numpy as np

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

DEFAULT_PANELS = ["downloads_line", "downloads_weekly"]
MAX_PANELS = 2

COLOR_OK = "#1a7f37"
COLOR_BAD = "#b42318"


def human(n):
    if n is None:
        return "—"
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.0f}万"
    if n >= 1_000:
        return f"{n / 1_000:.1f}千"
    return str(int(n))


def _series_values(series, key):
    return series.get(key) or []


def panel_downloads_line(ax, series, metrics, color):
    rows = _series_values(series, "downloads")
    if not rows:
        _empty(ax, "该项目不在 PyPI 上，无下载数据")
        return "PyPI 下载量"

    dates = [date.fromisoformat(d) for d, _ in rows]
    values = [n for _, n in rows]
    ax.plot(dates, values, color="#c9d6e3", linewidth=0.9, label="日下载")
    average = [np.mean(values[max(0, i - 6):i + 1]) for i in range(len(values))]
    ax.plot(dates, average, color="#1f6feb", linewidth=2.4, label="7 日均线")
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, p: human(v)))
    ax.tick_params(axis="x", rotation=30, labelsize=8)
    return "PyPI 下载量（近 181 天）"


def panel_downloads_weekly(ax, series, metrics, color):
    rows = _series_values(series, "downloads")
    if not rows:
        _empty(ax, "无下载数据")
        return "每周下载总量"

    values = [n for _, n in rows]
    chunks = [sum(values[i:i + 7]) for i in range(0, len(values), 7)][-26:]
    ax.bar(range(len(chunks)), chunks, color=color, width=0.75)
    ax.set_xticks(range(0, len(chunks), 4))
    ax.set_xticklabels([f"{-len(chunks) + i + 1}" for i in range(0, len(chunks), 4)], fontsize=8)
    ax.set_xlabel("周（相对今天的周数）", fontsize=8)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, p: human(v)))
    ax.text(0.02, 0.94, f"26 周合计 {human(sum(chunks))} 次", transform=ax.transAxes,
            ha="left", va="top", fontsize=10, color=color, fontweight="bold",
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.85))
    return "每周下载总量（近 26 周）"


def panel_activity_strip(ax, series, metrics, color):
    rows = _series_values(series, "weeks")
    if not rows:
        _empty(ax, "GitHub 仍在计算 commit 数据，稍后重试")
        return "近 52 周的开发活动"

    totals = [w.get("total", 0) for w in rows]
    peak = max(max(totals), 1)
    for i, value in enumerate(totals):
        face = "#e6e6e6" if value == 0 else plt.cm.Blues(0.35 + 0.6 * (value / peak))
        ax.add_patch(plt.Rectangle((i, 0.46), 0.85, 0.26, facecolor=face, edgecolor="none"))

    ax.set_xlim(-1, len(totals) + 0.5)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)

    active = sum(1 for t in totals if t > 0)
    ax.text(0.0, 0.30, f"有提交的周：{active} / {len(totals)}　｜　合计 {sum(totals)} 次",
            transform=ax.transAxes, fontsize=11, color=color, fontweight="bold")
    ax.text(0.0, 0.14, "一格 = 一周，灰色 = 这一周没有任何提交",
            transform=ax.transAxes, fontsize=8.5, color="#999999")
    return "近 52 周的开发活动｜每一格是一周"


def panel_commits_weekly(ax, series, metrics, color):
    rows = _series_values(series, "weeks")
    if not rows:
        _empty(ax, "无 commit 数据")
        return "每周 commit 数"

    totals = [w.get("total", 0) for w in rows]
    labels = [datetime.fromtimestamp(w["week"]).strftime("%m-%d") for w in rows]
    ax.bar(range(len(totals)), totals, color=color, width=0.75)
    ax.set_xticks(range(0, len(labels), 8))
    ax.set_xticklabels(labels[::8], fontsize=8)
    ax.set_ylim(0, max(max(totals) * 1.15, 1))
    return "每周 commit 数（近 52 周）"


def _empty(ax, message):
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=10, color="#999999")
    ax.axis("off")


PANELS = {
    "downloads_line": panel_downloads_line,
    "downloads_weekly": panel_downloads_weekly,
    "activity_strip": panel_activity_strip,
    "commits_weekly": panel_commits_weekly,
}


def resolve_panels(panels):
    if not isinstance(panels, (list, tuple)):
        return list(DEFAULT_PANELS)
    valid = [name for name in panels if name in PANELS]
    if not valid:
        return list(DEFAULT_PANELS)
    seen = []
    for name in valid:
        if name not in seen:
            seen.append(name)
    return seen[:MAX_PANELS]


def render(path, repo, verdict, reason, metrics, series, panels=None, highlight=""):
    names = resolve_panels(panels)
    color = COLOR_OK if verdict == "健康" else COLOR_BAD

    fig = plt.figure(figsize=(13.5, 7.8))
    grid = gridspec.GridSpec(3, len(names), height_ratios=[1.0, 2.3, 0.55],
                             hspace=0.42, wspace=0.2)

    head = fig.add_subplot(grid[0, :])
    head.axis("off")
    head.text(0.0, 0.95, repo, fontsize=13, color="#777777")
    head.text(0.0, 0.52, verdict, fontsize=30, fontweight="bold", color=color)
    wrapped = textwrap.fill(reason, width=64) if reason else ""
    head.text(0.0, 0.16, wrapped, fontsize=10.5, color="#333333", va="top", linespacing=1.5)

    stats = [
        ("发版距今", f"{metrics['release_age']}天" if metrics.get("release_age") is not None else "无发版"),
        ("4 周周均 commit",
         f"{metrics['commits_4w']:.1f}" if metrics.get("commits_4w") is not None else "—"),
        ("周下载量", human(metrics.get("dl_week"))),
        ("下载 4 周趋势",
         f"{metrics['dl_trend'] * 100:+.0f}%" if metrics.get("dl_trend") is not None else "—"),
        ("top1 贡献者",
         f"{metrics['top1_share'] * 100:.0f}%" if metrics.get("top1_share") is not None else "—"),
    ]
    for i, (label, value) in enumerate(stats):
        x = 0.50 + i * 0.102
        head.text(x, 0.56, value, fontsize=15, fontweight="bold", color="#111111")
        head.text(x, 0.24, label, fontsize=8, color="#888888")

    for column, name in enumerate(names):
        ax = fig.add_subplot(grid[1, column])
        title = PANELS[name](ax, series, metrics, color)
        ax.set_title(title, fontsize=11, pad=10)
        ax.grid(alpha=0.2, axis="y")
        ax.tick_params(labelsize=8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

    foot = fig.add_subplot(grid[2, :])
    foot.axis("off")
    parts = []
    if metrics.get("sample_span") is not None:
        parts.append(f"issue 样本跨度 {metrics['sample_span']} 天")
    if metrics.get("median_close") is not None:
        parts.append(f"中位关闭 {metrics['median_close']:.1f} 天")
    if metrics.get("stuck_days") is not None:
        parts.append(f"未关 issue 平均滞留 {metrics['stuck_days']:.0f} 天")
    parts.append(f"数据生成于 {date.today()}")
    foot.text(0.0, 0.5, "　｜　".join(parts), fontsize=9, color="#999999")

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(target, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return str(target)

from datetime import datetime, timezone
from pathlib import Path

import chart

TMP = Path(".tmp")

METRICS = {
    "release_age": 10,
    "commits_4w": 5.0,
    "dl_week": 12000,
    "dl_trend": 0.05,
    "top1_share": 0.3,
    "sample_span": 30,
    "median_close": 2.0,
    "stuck_days": 10,
    "archived": False,
}

EPOCH = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
SERIES = {
    "downloads": [(f"2026-10-{day:02d}", 1000 + day * 10) for day in range(1, 29)],
    "weeks": [{"week": EPOCH + i * 604800, "total": i % 5} for i in range(20)],
}


def test_render_creates_file():
    out = chart.render(TMP / "chart_one.png", "a/b", "健康", "无红旗", METRICS, SERIES,
                       ["downloads_line"])
    assert Path(out).exists()
    assert Path(out).stat().st_size > 1000


def test_render_two_panels():
    out = chart.render(TMP / "chart_two.png", "a/b", "不健康", "0 提交", METRICS, SERIES,
                       ["activity_strip", "downloads_weekly"], highlight="52 周 0 提交")
    assert Path(out).exists()


def test_invalid_panels_fall_back_to_default():
    assert chart.resolve_panels(["radar_chart"]) == chart.DEFAULT_PANELS


def test_empty_panels_use_default():
    assert chart.resolve_panels([]) == chart.DEFAULT_PANELS
    assert chart.resolve_panels(None) == chart.DEFAULT_PANELS


def test_panels_dedup_and_capped():
    chosen = chart.resolve_panels(
        ["downloads_line", "downloads_line", "activity_strip", "commits_weekly"]
    )
    assert chosen == ["downloads_line", "activity_strip"]


def test_render_without_series_does_not_crash():
    out = chart.render(TMP / "chart_empty.png", "a/b", "不健康", "无数据", METRICS, {},
                       ["activity_strip", "downloads_weekly"])
    assert Path(out).exists()


def test_human_formats():
    assert chart.human(1234) == "1.2千"
    assert chart.human(1234567) == "123万"
    assert chart.human(None) == "—"

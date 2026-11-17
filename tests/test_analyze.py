from datetime import date, datetime, timezone

import analyze


TODAY = date(2026, 11, 17)


def epoch(year, month, day):
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


def base_raw():
    return {
        "repo": {
            "full_name": "acme/lib",
            "language": "Python",
            "archived": False,
            "pushed_at": "2026-11-07T00:00:00Z",
        },
        "release": {"published_at": "2026-08-09T00:00:00Z"},
        "issues": [
            {"created_at": "2026-11-12T00:00:00Z", "closed_at": None},
            {"created_at": "2026-09-28T00:00:00Z", "closed_at": None},
            {"created_at": "2026-11-15T00:00:00Z", "closed_at": "2026-11-16T00:00:00Z"},
            {"created_at": "2026-11-10T00:00:00Z", "closed_at": "2026-11-13T00:00:00Z"},
            {
                "created_at": "2026-11-01T00:00:00Z",
                "closed_at": None,
                "pull_request": {"url": "..."},
            },
        ],
        "weeks": [
            {"week": epoch(2026, 10, 11), "total": 10},
            {"week": epoch(2026, 10, 18), "total": 20},
            {"week": epoch(2026, 10, 25), "total": 30},
            {"week": epoch(2026, 11, 1), "total": 40},
            {"week": epoch(2026, 11, 8), "total": 50},
            {"week": epoch(2026, 11, 15), "total": 999},
        ],
        "contribs": [
            {"login": "a", "contributions": 90},
            {"login": "b", "contributions": 10},
        ],
        "downloads": [
            (f"2026-{m:02d}-{d:02d}", 1000) for m in (9, 10, 11) for d in range(1, 29)
        ],
    }


def test_basic_metrics():
    m = analyze.build_metrics(base_raw(), TODAY)

    assert m["full_name"] == "acme/lib"
    assert m["archived"] is False
    assert m["release_age"] == 100
    assert m["push_age"] == 10


def test_pr_is_excluded():
    m = analyze.build_metrics(base_raw(), TODAY)

    assert m["unclosed_ratio"] == 0.5
    assert m["median_close"] == 2
    assert m["newest_issue_age"] == 2
    assert m["stuck_days"] == 27.5
    assert m["sample_span"] == 48


def test_incomplete_week_is_excluded():
    m = analyze.build_metrics(base_raw(), TODAY)
    assert m["commits_4w"] == 35.0


def test_contributor_concentration():
    m = analyze.build_metrics(base_raw(), TODAY)
    assert m["top1_share"] == 0.9


def test_download_week_and_trend():
    m = analyze.build_metrics(base_raw(), TODAY)
    assert m["dl_trend"] == 0.0
    assert m["dl_noise"] == 0.0
    assert m["dl_week"] == 7000


def test_complete_data_has_no_missing():
    m = analyze.build_metrics(base_raw(), TODAY)
    assert m["missing"] == []
    assert "star_growth" not in m


def test_no_issues_marks_missing():
    raw = base_raw()
    raw["issues"] = []
    m = analyze.build_metrics(raw, TODAY)

    assert m["median_close"] is None
    assert m["unclosed_ratio"] is None
    assert m["stuck_days"] is None
    assert "median_close" in m["missing"]
    assert "unclosed_ratio" in m["missing"]


def test_missing_release():
    raw = base_raw()
    raw["release"] = None
    m = analyze.build_metrics(raw, TODAY)

    assert m["release_age"] is None
    assert "release_age" in m["missing"]


def test_short_download_series_gives_no_trend():
    raw = base_raw()
    raw["downloads"] = [("2026-11-10", 500), ("2026-11-11", 600)]
    m = analyze.build_metrics(raw, TODAY)

    assert m["dl_trend"] is None
    assert m["dl_week"] == 600

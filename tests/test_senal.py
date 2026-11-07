"""Señal engine scoring: pure functions, no network."""
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import senal  # noqa: E402


def _v(id, daily, fmt="quiz", published="2026-11-01"):
    return {"id": id, "format": fmt, "published": published, "daily": daily}


def _cohort(n=9):
    return [_v(f"c{i}", [0, 100, 100] + [0] * 12, published="2026-10-10") for i in range(n)]


def test_typical_is_the_median_daily_and_cumulative_curve():
    daily, cum = senal.typical(_cohort(), "quiz", date(2026, 11, 7))
    assert daily[:4] == [0, 100, 100, 0] and cum[:4] == [0, 100, 200, 200]


def test_a_small_format_falls_back_to_the_whole_channel():
    vids = _cohort() + [_v("h1", [0, 5, 5] + [0] * 12, fmt="how_do_you_say", published="2026-10-10")]
    assert senal.typical(vids, "how_do_you_say", date(2026, 11, 7))[1][2] == 200


def test_the_video_itself_is_excluded_from_its_own_curve():
    vids = _cohort(8) + [_v("x", [0, 10_000, 10_000] + [0] * 12, published="2026-10-10")]
    assert senal.typical(vids, "quiz", date(2026, 11, 7), exclude="x")[1][2] == 200


def test_double_the_typical_with_enough_views_is_a_breakout():
    s = senal.score([0, 300, 300], [0, 100, 200])
    assert s == 3.0 and senal.state([0, 300, 300], s, 600) == "breakout"


def test_a_rise_after_day_two_is_a_second_wind():
    d = [0, 50, 50, 0, 0, 80]
    assert senal.state(d, senal.score(d, [0, 100, 200, 200, 200, 200]), 180) == "second_wind"


def test_far_below_typical_after_day_two_is_cold():
    d = [0, 20, 20, 0]
    assert senal.state(d, senal.score(d, [0, 100, 200, 200]), 40) == "cold"


def test_a_brand_new_video_has_no_score_and_is_normal():
    assert senal.score([0], [0]) is None and senal.state([0], None, 0) == "normal"


def test_why_lists_factors_above_one_and_a_half_times_the_channel():
    v = {"views": 1000, "retention": 90.0, "shares": 1, "subs": 0,
         "sources": {"SHORTS": 0.70, "YT_SEARCH": 0.25, "EXT": 0.05}}
    med = {"retention": 50.0, "shares_per_1k": 1.0, "subs_per_1k": 0.4}
    assert senal.why(v, med, {"SHORTS": 0.91, "YT_SEARCH": 0.07, "EXT": 0.02}) == ["search", "external", "retention"]


def test_a_video_without_views_has_no_why():
    v = {"views": 0, "retention": None, "shares": 0, "subs": 0, "sources": {}}
    assert senal.why(v, {"retention": 50.0, "shares_per_1k": 1.0, "subs_per_1k": 0.4}, {"SHORTS": 1.0}) == []


# --- engine data ---------------------------------------------------------------------------------
import json  # noqa: E402

import pytest  # noqa: E402


class _Resp:
    def __init__(self, rows):
        self.rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return {"rows": self.rows}


def test_empty_daily_has_no_score():
    assert senal.score([], [0, 100]) is None


def test_a_young_video_does_not_drag_older_ages_medians():
    old = [_v(f"o{i}", [0, 100, 100, 100], published="2026-10-10") for i in range(8)]
    young = [_v(f"y{i}", [0], published="2026-11-07") for i in range(5)]
    daily, _ = senal.typical(old + young, "quiz", date(2026, 11, 7))
    assert daily[:4] == [0, 100, 100, 100]


def test_why_lists_a_factor_when_the_channel_has_none_of_it():
    v = {"views": 100, "sources": {"EXT": 0.3}, "retention": 50, "shares": 0, "subs": 0}
    med = {"retention": 50, "shares_per_1k": 1, "subs_per_1k": 1}
    assert senal.why(v, med, {"EXT": 0}) == ["external"]


def test_sources_bucket_everything_else_as_external():
    rows = [["SHORTS", 70], ["YT_SEARCH", 25], ["EXT_URL", 3], ["PLAYLIST", 2]]
    out = senal.fetch_sources("a", date(2026, 11, 1), date(2026, 11, 7), "t", lambda *a, **k: _Resp(rows))
    assert out == pytest.approx({"SHORTS": .70, "YT_SEARCH": .25, "EXT": .05})
    assert senal.fetch_sources(None, date(2026, 11, 1), date(2026, 11, 7), "t", lambda *a, **k: _Resp([])) == {}


def test_daily_views_are_keyed_by_day():
    seen = {}

    def get(url, params, headers, timeout):
        seen.update(params)
        return _Resp([["2026-11-01", 0], ["2026-11-02", 150]])
    assert senal.fetch_daily("a", date(2026, 11, 1), date(2026, 11, 2), "t", get) == {"2026-11-01": 0, "2026-11-02": 150}
    assert seen["filters"] == "video==a" and seen["dimensions"] == "day"


def test_days_analytics_has_not_reached_are_estimated_from_snapshots():
    daily, est = senal.estimate_tail([0, 150], date(2026, 11, 2), date(2026, 11, 1),
                                     [(date(2026, 11, 2), 150), (date(2026, 11, 3), 230), (date(2026, 11, 4), 260)])
    assert daily == [0, 150, 80, 30] and est == 2


def test_payload_has_the_spec_shape_and_picks_the_star():
    vids = [dict(_v(f"c{i}", [0, 100, 100, 0], published="2026-10-10"), est_from=None, views=200, retention=60.0,
                 sources={"SHORTS": 1.0}, shares=1, subs=1) for i in range(9)]
    vids.append(dict(_v("star", [0, 500, 500, 0], published="2026-11-04"), est_from=2, views=1000, retention=80.0,
                     sources={"SHORTS": .5, "YT_SEARCH": .5}, shares=5, subs=5))
    p = senal.build_payload(vids, {"SHORTS": .9}, "2026-11-07T08:00:00", date(2026, 11, 5), date(2026, 11, 7))
    assert p["version"] == 1 and p["platforms"] == ["youtube"] and p["star"] == {"youtube": "star"}
    for v in p["videos"]:
        assert {"id", "platform", "format", "published", "age_days", "daily", "est_from", "views", "retention",
                "sources", "shares", "subs", "score", "state", "why"} <= set(v) and len(v["daily"]) <= 15
    assert p["channel"]["typical_cum"]["all"] and p["channel"]["median"]["retention"]


def _snapshot(day, views):
    d = senal.SENAL_DIR.parent / "stats"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"youtube_{day}.json").write_text(json.dumps({"videos": [
        {"id": "a", "type": "quiz", "views": views, "days": 2, "avg_view_pct": 70.0, "subs_gained": 1, "shares": 2}]}))


def _fake_get(url, params, headers, timeout):
    if params["dimensions"] == "day":
        return _Resp([["2026-11-05", 0], ["2026-11-06", 40]])
    return _Resp([["SHORTS", 9], ["YT_SEARCH", 1]])


def test_refresh_writes_the_json_under_senal_dir():
    _snapshot("2026-11-07", 100)
    path = senal.refresh(date(2026, 11, 7), _fake_get, "tok")
    assert path == senal.SENAL_DIR / "senal.json"
    d = json.loads(path.read_text())
    assert d["version"] == 1 and d["data_until"] == "2026-11-06" and d["videos"][0]["daily"] == [0, 40]


def test_a_token_failure_keeps_the_previous_json(monkeypatch):
    import channel_stats
    senal.SENAL_DIR.mkdir(parents=True, exist_ok=True)
    f = senal.SENAL_DIR / "senal.json"
    f.write_bytes(b'{"keep": 1}')

    def boom():
        raise RuntimeError("YouTube no está conectado")
    monkeypatch.setattr(channel_stats, "_youtube_token", boom)
    with pytest.raises(RuntimeError):
        senal.refresh(date(2026, 11, 7), _fake_get)
    assert f.read_bytes() == b'{"keep": 1}'


def test_refresh_if_stale_skips_a_fresh_file():
    senal.SENAL_DIR.mkdir(parents=True, exist_ok=True)
    (senal.SENAL_DIR / "senal.json").write_text(json.dumps({"read_at": datetime.now().isoformat()}))

    def get(*a, **k):
        raise AssertionError("must not call")
    assert senal.refresh_if_stale(get=get, token="t") is None

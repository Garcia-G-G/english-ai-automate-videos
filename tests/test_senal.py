"""Señal engine scoring: pure functions, no network."""
import sys
from datetime import date
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

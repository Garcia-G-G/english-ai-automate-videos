"""STEP 81 §1: the priority score, the day's mix, the stats refreshing themselves, sequel cards."""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import channel_stats as C  # noqa: E402
import daily_mix as D  # noqa: E402
import queue_priority as Q  # noqa: E402

CFG = {"prior_views": {"how_do_you_say": 1000, "phrases_level": 500, "choose_level": 100}, "a1": ["casa", "cocina", "fruta"],
       "default_prior": 100.0, "tier_c": ["restaurante"], "topic_scores": dict(Q.DEFAULT_TOPIC_SCORES)}


def _vid(vtype, views, days=10, cat="X", title="t"):
    return {"type": vtype, "views": views, "days": days, "category": cat, "title": title}


def test_format_score_is_the_median_over_how_do_you_say_and_falls_back_to_the_prior():
    stats = {"videos": [_vid("how_do_you_say", 1000)] * 5 + [_vid("phrases_level", 500)] * 5 + [_vid("choose_level", 900, days=1)] * 9}
    assert Q.format_score("phrases_level", stats, CFG)[0] == 0.5
    f, why = Q.format_score("choose_level", stats, CFG)           # young videos do not count: the prior 100/1000
    assert f == pytest.approx(0.1) and "previa" in why


def test_topic_scores_a_sequel_c_and_other():
    stats = {"videos": [_vid("how_do_you_say", 1202, cat="ANIMALES")]}
    t = lambda s: Q.topic_score(s, stats, CFG)[0]                 # noqa: E731
    assert t({"theme": "la cocina"}) == 1.0
    assert t({"theme": "más animales", "_meta": {"sequel_of": "animales"}}) == 0.85
    assert t({"theme": "más peces", "_meta": {"sequel_of": "peces"}}) == 0.6            # parent unknown: no sequel credit
    assert t({"theme": "en el restaurante"}) == 0.35 and t({"theme": "el espacio"}) == 0.6


def test_a_family_published_in_the_last_three_days_is_halved_so_two_kitchen_videos_never_follow():
    stats = {"videos": [_vid("how_do_you_say", 900, days=2, cat="COCINA")]}
    assert Q.freshness({"theme": "la cocina"}, stats, CFG)[0] == 0.5
    assert Q.freshness({"theme": "la fruta"}, stats, CFG)[0] == 1.0
    assert Q.freshness({"theme": "la cocina"}, {"videos": [_vid("how_do_you_say", 900, days=9, cat="COCINA")]}, CFG)[0] == 1.0


def test_the_score_multiplies_the_three_and_explains_itself():
    p, why = Q.score({"type": "how_do_you_say", "theme": "la casa"}, {}, CFG)
    assert p == 1000 and "formato ×1.00" in why and "tema ×1.00" in why and why.startswith("how_do_you_say")


def test_the_mix_is_three_how_do_you_say_then_one_other_then_full():
    assert D.next_slot([])["slot"] == "main" and D.next_slot(["how_do_you_say"] * 2)["slot"] == "main"
    other = D.next_slot(["how_do_you_say"] * 3)
    assert other["slot"] == "other" and other["types"][0] == "phrases_level" and other["tier_a_only"]
    assert D.next_slot(["how_do_you_say"] * 3 + ["phrases_level"])["slot"] == "full"


def test_the_other_slot_rotates_phrases_then_reto_then_level_test_and_grammar_goes_last():
    three = ["how_do_you_say"] * 3
    assert [D.next_slot(three, k)["types"][0] for k in range(4)] == ["phrases_level", "hecho_con_claude", "level_test", "phrases_level"]
    assert D.next_slot(three)["types"][-1] in D.GRAMMAR


def test_uploads_on_counts_only_that_day_and_platform():
    rows = [{"platform": "youtube", "video_type": "quiz", "published_at": "2026-11-12T08:00:00"},
            {"platform": "facebook", "video_type": "quiz", "published_at": "2026-11-12T08:00:00"},
            {"platform": "youtube", "video_type": "quiz", "published_at": "2026-11-11T08:00:00"}]
    assert D.uploads_on(rows, date(2026, 11, 12)) == ["quiz"]


def test_stats_refresh_when_older_than_twenty_hours_and_a_failure_is_returned_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "latest", lambda: {"read_at": (datetime(2026, 11, 12, 12) - timedelta(hours=5)).isoformat()})
    calls = []
    assert C.refresh_if_stale(now=datetime(2026, 11, 12, 12), do=lambda: calls.append(1)) == {"ran": False, "error": None} and not calls
    monkeypatch.setattr(C, "latest", lambda: {"read_at": (datetime(2026, 11, 12, 12) - timedelta(hours=21)).isoformat()})
    assert C.refresh_if_stale(now=datetime(2026, 11, 12, 12), do=lambda: calls.append(1))["ran"] is True and calls
    def boom():
        raise RuntimeError("quota")
    assert "quota" in C.refresh_if_stale(now=datetime(2026, 11, 12, 12), do=boom)["error"]
    monkeypatch.setattr(C, "latest", lambda: None)
    assert C.refresh_if_stale(do=lambda: None)["ran"] is True            # no snapshot at all


def test_the_auto_refresh_does_not_start_a_thread_under_pytest():
    before = C.AUTO["started"]
    C.start_auto_refresh()
    assert C.AUTO["started"] == before


def test_a_winner_without_a_sequel_gets_a_card_and_one_that_has_it_does_not():
    vids = [{"type": "how_do_you_say", "category": "ANIMALES", "views": 1202, "days": 4, "title": "a"},
            {"type": "how_do_you_say", "category": "CASA", "views": 900, "days": 5, "title": "c"},
            {"type": "how_do_you_say", "category": "FRUTA", "views": 300, "days": 5, "title": "f"},
            {"type": "how_do_you_say", "category": "COLORES", "views": 2000, "days": 2, "title": "young"}]
    got = C.sequel_suggestions(vids, ["más casa"])
    assert [r["category"] for r in got] == ["ANIMALES"]

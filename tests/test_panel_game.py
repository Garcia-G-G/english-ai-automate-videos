"""STEP 85 §6: XP, level, streak and achievements from a fixture history with known answers."""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from panel_core import game as G  # noqa: E402

CR = ZoneInfo("America/Costa_Rica")
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=CR)


def row(art, day, hh=9, platform="youtube", vtype="how_do_you_say", uid=None, **extra):
    d = date(2026, 11, 14) - timedelta(days=day)
    return {"platform": platform, "artifact": art, "video_type": vtype, "upload_id": uid or f"id-{art}",
            "published_at": f"{d}T{hh:02d}:00:00", "extra": extra}


def twelve():
    """12 videos, one a day for the last 12 days (today included), each on YouTube and then Facebook."""
    out = []
    for i in range(12):
        out += [row(f"a{i}", 11 - i, 9), row(f"a{i}", 11 - i, 10, platform="facebook")]
    return out


def senal_with_a_breakout():
    vids = [{"id": f"s{i}", "format": "how_do_you_say", "published": f"2026-10-{10 + i:02d}", "daily": [100, 100, 100, 100, 50], "est_from": None}
            for i in range(10)]
    vids.append({"id": "id-a3", "format": "how_do_you_say", "published": "2026-11-05", "daily": [500, 500, 500, 500], "est_from": None})
    return {"videos": vids, "data_until": "2026-11-12"}


def test_xp_level_and_the_first_platform_counts_once():
    g = G.compute(twelve(), None, now=NOW)
    assert g["xp"] == 12 * 50 and g["level"] == 1 and g["levelXp"] == 600 and g["levelSize"] == 1000      # not 24 x 50: Facebook adds nothing


def test_level_rolls_over_at_a_thousand():
    rows = [r for i in range(20) for r in (row(f"b{i}", 19 - i),)]
    assert G.compute(rows, None, now=NOW)["xp"] == 1000
    g = G.compute(rows + [row("b20", 0, 11)], None, now=NOW)
    assert (g["xp"], g["level"], g["levelXp"]) == (1050, 2, 50)


def test_a_breakout_adds_100_once_and_only_to_the_video_that_earned_it():
    g = G.compute(twelve(), senal_with_a_breakout(), now=NOW)
    assert g["xp"] == 12 * 50 + 100
    assert G.compute(twelve(), None, now=NOW)["xp"] == 600                                               # no Señal data: no award, nothing invented
    est = senal_with_a_breakout()
    est["videos"][-1]["est_from"] = 2                                                                   # day 3 is an estimate: left out
    assert G.compute(twelve(), est, now=NOW)["xp"] == 600


def test_a_rerendered_video_loses_its_ten():
    g = G.compute(twelve(), None, rerendered=lambda v: v["artifact"] == "a0", now=NOW)
    assert g["xp"] == 600 - 10


def test_a_scheduled_video_is_not_xp_yet_but_lights_todays_streak():
    rows = [row("a", 2), row("b", 1), row("c", 0, 20, scheduled_for="2026-11-14T20:00:00-06:00")]
    rows[2]["published_at"] = "2026-11-14T11:00:00"                                                      # uploaded now, goes live at 20:00
    g = G.compute(rows, None, now=NOW)
    assert g["xp"] == 100 and g["streakDays"] == 3 and g["streakIncludesToday"] is True


def test_the_streak_counts_consecutive_days_and_today_is_optional():
    assert (G.compute(twelve(), None, now=NOW)["streakDays"], G.compute(twelve(), None, now=NOW)["streakIncludesToday"]) == (12, True)
    rows = [row("a", 5), row("b", 4), row("c", 3), row("d", 1), row("e", 0)]                            # a gap two days ago
    assert G.compute(rows, None, now=NOW)["streakDays"] == 2
    yesterday_last = [row("a", 3), row("b", 2), row("c", 1)]
    g = G.compute(yesterday_last, None, now=NOW)
    assert (g["streakDays"], g["streakIncludesToday"]) == (3, False)                                    # the streak is alive until today ends
    assert G.compute([row("a", 3)], None, now=NOW)["streakDays"] == 0                                    # it broke yesterday


def test_midnight_in_costa_rica_not_in_utc():
    now = datetime(2026, 11, 14, 23, 45, tzinfo=CR)                                                      # 05:45 UTC on the 15th
    late = {"platform": "youtube", "artifact": "z", "video_type": "x", "upload_id": "z", "published_at": "2026-11-15T05:30:00+00:00", "extra": {}}
    prev = row("y", 1)
    g = G.compute([prev, late], None, now=now)
    assert g["streakDays"] == 2 and g["streakIncludesToday"] is True                                     # 23:30 CR is the 14th, not the 15th
    assert g["achievements"][0]["unlockedAt"] == "2026-11-13T09:00:00-06:00"
    after = {**late, "artifact": "w", "published_at": "2026-11-15T06:30:00+00:00"}                       # 00:30 CR on the 15th: tomorrow, ignored
    assert G.compute([prev, late, after], None, now=now)["streakDays"] == 2
    naive_next = {**late, "artifact": "v", "published_at": "2026-11-15T00:10:00"}                        # naive means Costa Rica
    assert G.compute([prev, late, naive_next], None, now=now)["xp"] == 100


def _by_id(g):
    return {a["id"]: a["unlockedAt"] for a in g["achievements"]}


def test_every_achievement_date_for_the_fixture_history():
    snaps = [(date(2026, 11, 10), [{"type": "how_do_you_say", "category": "CASA", "views": 800}, {"type": "how_do_you_say", "category": "MÁS CASA", "views": 700}]),
             (date(2026, 11, 12), [{"type": "how_do_you_say", "category": "Casa", "views": 800}, {"type": "how_do_you_say", "category": "MÁS CASA", "views": 1300}])]
    rej = [datetime(2026, 11, 1, 10, 0, tzinfo=CR), datetime(2026, 11, 5, 10, 0, tzinfo=CR)]
    ids = _by_id(G.compute(twelve(), senal_with_a_breakout(), snaps, rej, now=NOW))
    assert ids["first"] == "2026-11-03T09:00:00-06:00"                                                    # a0
    assert ids["v10"] == "2026-11-12T09:00:00-06:00"                                                      # a9
    assert ids["v50"] is None and ids["v100"] is None and ids["csd50"] is None                           # 12 videos
    assert ids["streak7"] == "2026-11-09T09:00:00-06:00" and ids["streak30"] is None
    assert ids["views1k"] == "2026-11-06T12:00:00-06:00"                                                  # 500+500 on day 1 of the 5th: the 6th, noon
    assert ids["week10k"] is None                                                                          # the fixture channel never reaches 10,000 in a week
    assert ids["sequelwin"] == "2026-11-12T12:00:00-06:00"                                                # not the 10th, when it still trailed
    assert ids["noreject"] == "2026-11-12T10:00:00-06:00"                                                 # the 1st is followed by one on the 5th: the 5th + 7 days


def test_fifty_how_do_you_say_and_a_hundred_videos():
    rows = [row(f"c{i}", 99 - i) for i in range(100)]
    ids = _by_id(G.compute(rows, None, now=NOW))
    assert ids["csd50"] == "2026-09-25T09:00:00-06:00" == ids["v50"] and ids["v100"] == "2026-11-14T09:00:00-06:00"
    assert ids["streak30"] == "2026-09-05T09:00:00-06:00"                                                  # the 30th consecutive day
    mixed = [row(f"d{i}", 99 - i, vtype="how_do_you_say" if i % 2 else "quiz") for i in range(100)]
    assert _by_id(G.compute(mixed, None, now=NOW))["csd50"] == "2026-11-14T09:00:00-06:00"                # only the 50 of that format count


def test_ten_thousand_views_in_a_week():
    sen = {"videos": [{"id": f"w{i}", "format": "x", "published": f"2026-10-{1 + i:02d}", "daily": [1500, 1000, 500]} for i in range(10)]}
    ids = _by_id(G.compute([], sen, now=NOW))
    assert ids["week10k"] is not None and ids["views1k"] == "2026-10-01T12:00:00-06:00"                    # 1,500 on day 0 of the first video
    quiet = {"videos": [{"id": "q", "format": "x", "published": "2026-10-01", "daily": [10, 10]}]}
    assert _by_id(G.compute([], quiet, now=NOW))["week10k"] is None


def test_no_history_is_zero_and_nothing_unlocked():
    g = G.compute([], None, now=NOW)
    assert (g["xp"], g["level"], g["levelXp"], g["streakDays"], g["streakIncludesToday"]) == (0, 1, 0, 0, False)
    assert [a["id"] for a in g["achievements"]] == [i for i, *_ in G.CATALOG] and all(a["unlockedAt"] is None for a in g["achievements"])


def test_an_unlock_is_announced_once_and_not_again_after_a_restart(tmp_path, monkeypatch):
    state = tmp_path / "state" / "game_seen.json"
    cur = {"g": G.compute(twelve()[:18], None, now=NOW)}                                                  # 9 videos
    monkeypatch.setattr(G, "snapshot", lambda now=None: cur["g"])
    sent = []
    G.recompute(sent.append, path=state)
    assert sent == []                                                                                      # the first run records, it does not announce
    cur["g"] = G.compute(twelve()[:20], None, now=NOW)                                                    # the 10th video
    G.recompute(sent.append, path=state)
    kinds = [e["type"] for e in sent]
    assert kinds == ["achievement.unlocked", "game"] and sent[0]["achievement"]["id"] == "v10" and sent[1]["game"]["xp"] == 500
    G.recompute(sent.append, path=state)                                                                   # nothing changed
    G.recompute(sent.append, path=state)                                                                   # a "restart": same file
    assert len(sent) == 2
    cur["g"] = G.compute(twelve(), None, now=NOW)                                                          # XP moves, nothing new unlocks
    G.recompute(sent.append, path=state)
    assert [e["type"] for e in sent[2:]] == ["game"]


def test_the_catalog_has_the_fixture_ids():
    import json
    fixture = json.loads((ROOT / "panel" / "contract-fixtures" / "game.json").read_text(encoding="utf-8"))
    assert {a["id"] for a in fixture["achievements"]} <= {i for i, *_ in G.CATALOG}

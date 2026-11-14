"""STEP 81 §2: publishing slots. Pure functions, a fake clock, no network."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import slots as S  # noqa: E402

CR = ZoneInfo("America/Costa_Rica")


def _at(day, hh, mm=0):
    return datetime(2026, 11, day, hh, mm, tzinfo=CR)


def test_the_slots_are_the_four_costa_rica_times_and_the_config_matches():
    cfg = S.settings()
    assert cfg["slots"] == ["08:30", "12:00", "16:00", "19:30"] and cfg["tz"] == "America/Costa_Rica"
    got = S.next_slots(_at(12, 7), [], 5, cfg)
    assert [(g.day, g.hour, g.minute) for g in got] == [(12, 8, 30), (12, 12, 0), (12, 16, 0), (12, 19, 30), (13, 8, 30)]


def test_a_taken_slot_is_skipped_and_nothing_goes_within_two_and_a_half_hours_of_it():
    cfg = S.settings()
    got = S.next_slots(_at(12, 7), [_at(12, 11, 0)], 3, cfg)              # a video at 11:00 blocks 12:00 (1 h) but not 16:00
    assert [(g.hour, g.minute) for g in got] == [(8, 30), (16, 0), (19, 30)]
    assert S.next_slots(_at(12, 7), [_at(12, 8, 30)], 1, cfg)[0].hour == 12


def test_at_most_four_a_day_and_a_slot_in_the_past_is_never_offered():
    cfg = {**S.settings(), "max_per_day": 2}
    taken = [_at(12, 8, 30), _at(12, 16, 0)]
    assert S.next_slots(_at(12, 7), taken, 1, cfg)[0].day == 13
    assert S.next_slots(_at(12, 8, 20), [], 1, S.settings())[0].hour == 12      # 08:30 is inside the 15 min lead


def test_taken_times_read_the_scheduled_slot_first_and_only_youtube():
    rows = [{"platform": "youtube", "published_at": "2026-11-12T01:00:00", "extra": {"scheduled_for": "2026-11-12T12:00:00-06:00"}},
            {"platform": "youtube", "published_at": "2026-11-11T20:00:00"},
            {"platform": "facebook", "published_at": "2026-11-12T08:00:00"},
            {"platform": "youtube", "published_at": "nonsense"}]
    got = S.taken_times(rows)
    assert [(t.day, t.hour) for t in got] == [(11, 20), (12, 12)]


def test_publish_at_is_rfc3339_utc():
    assert S.publish_at(_at(12, 12, 0)) == "2026-11-12T18:00:00.000Z"


def test_fill_plan_follows_the_days_mix_and_names_what_fills_each_slot():
    ranked = [(f"h{i}", {"type": "how_do_you_say"}) for i in range(4)] + [("p1", {"type": "phrases_level"}),
                                                                       ("c1", {"type": "choose_level"})]
    plan = S.fill_plan(S.next_slots(_at(12, 7), [], 4), ranked)
    assert [p[2] for p in plan] == ["h0", "h1", "h2", "p1"]               # three «Cómo se dice», then the «other» slot


def test_the_youtube_body_carries_publish_at_and_goes_private(monkeypatch):
    import uploader
    seen = {}

    class Resp:
        status_code, headers, text = 500, {}, "stop here"

        def json(self):
            return {}

    def post(url, **kw):
        seen["body"] = kw["json"]
        return Resp()
    monkeypatch.setattr(uploader.requests, "post", post)
    up = uploader.YouTubeUploader.__new__(uploader.YouTubeUploader)
    up._token_data = {"access_token": "x"}
    vid = Path(__file__)
    up.upload_video(str(vid), "t", "d", publish_at="2026-11-12T18:00:00.000Z")
    assert seen["body"]["status"]["publishAt"] == "2026-11-12T18:00:00.000Z" and seen["body"]["status"]["privacyStatus"] == "private"


def test_main_upload_hands_youtube_a_publish_at_and_the_ledger_remembers_the_slot(monkeypatch):
    import main
    monkeypatch.setattr(main, "next_youtube_slot", lambda: _at(30, 12, 0))
    assert main.slots.publish_at(main.next_youtube_slot()) == "2026-11-30T18:00:00.000Z"


def test_the_panels_guarded_upload_schedules_youtube_and_only_youtube(monkeypatch):
    import admin
    seen = []

    class M:
        def upload(self, platform, path, on_session=None, **kw):
            seen.append((platform, kw))
            return {"success": True, "upload_id": "x", "url": "u"}
    slot = datetime(2026, 12, 1, 12, 0, tzinfo=CR)
    monkeypatch.setattr(S, "next_free", lambda *a, **k: slot)
    import upload_limits
    monkeypatch.setattr(upload_limits, "claim", lambda *a: True)
    monkeypatch.setattr(upload_limits, "release", lambda *a: None)
    import publication_log
    monkeypatch.setattr(publication_log, "record_attempt", lambda **k: None)
    yt = admin._guarded_upload_unlocked(M(), "a", "youtube", "/nope.mp4", title="t")
    fb = admin._guarded_upload_unlocked(M(), "a", "facebook", "/nope.mp4", title="t")
    assert seen[0][1]["publish_at"] == "2026-12-01T18:00:00.000Z" and yt["scheduled_for"] == slot.isoformat()
    assert "publish_at" not in seen[1][1] and "scheduled_for" not in fb


# ── STEP 85 §0: free «Sale». Cases ported from panel/src/lib/schedule.test.ts ──

_TAKEN = [(_at(14, 8, 30), "MÉDICO"), (_at(14, 12, 0), "YA LO RESOLVÍ"), (_at(14, 16, 0), "Test FAMILIA"), (_at(14, 19, 30), "MÁS ANIMALES")]
_NOW = _at(14, 17, 0)


def test_free_time_labels_and_days_match_the_front_end():
    assert S.long_label(_at(14, 21, 15)) == "sábado 14 nov a las 21:15"
    d = S.next_days(datetime(2026, 11, 29, 22, 0, tzinfo=CR), 4)
    assert [x[1] for x in d] == ["Hoy", "Mañana", "mar 1 dic", "mié 2 dic"] and d[2][0].isoformat() == "2026-12-01"
    assert S.next_days(datetime(2026, 11, 15, 3, 0, tzinfo=ZoneInfo("UTC")), 1)[0][0].isoformat() == "2026-11-14"


def test_free_time_blocks_only_the_past_or_too_soon():
    assert "ya pasó" in S.check_time(_at(14, 16, 30), _TAKEN, _NOW)["error"]
    assert "15 min" in S.check_time(_at(14, 17, 10), _TAKEN, _NOW)["error"]
    assert S.check_time(datetime(2026, 11, 16, 10, 0, tzinfo=CR), _TAKEN, _NOW) == {"error": None, "warnings": []}


def test_free_time_warns_without_blocking_about_spacing_and_a_fifth_video():
    r = S.check_time(_at(14, 21, 15), _TAKEN, _NOW)
    assert r["error"] is None
    assert r["warnings"] == ["A 1 h 45 min de «MÁS ANIMALES» (lo normal: 2,5 h).", "Sería el 5.º vídeo de ese día (lo normal: 4)."]
    assert S.check_time(_at(14, 19, 30), _TAKEN, _NOW)["warnings"][0] == "A la misma hora que «MÁS ANIMALES»."


def test_which_usual_slots_are_taken():
    assert S.taken_at(_at(14, 16, 0), _TAKEN) == "Test FAMILIA" and S.taken_at(_at(15, 16, 0), _TAKEN) is None


def test_garcias_time_is_accepted_with_warnings_and_marked_garcia():
    got = S.explicit(_at(14, 21, 15), _TAKEN, _NOW)
    assert got["scheduled_by"] == "garcia" and len(got["warnings"]) == 2


def test_garcias_time_in_the_past_is_refused():
    import pytest
    with pytest.raises(ValueError, match="ya pasó"):
        S.explicit(_at(14, 16, 30), _TAKEN, _NOW)


def test_auto_fill_still_respects_the_limits_and_is_marked_auto():
    cfg = S.settings()
    got = S.next_slots(_NOW, [t for t, _ in _TAKEN], 1, cfg)[0]
    assert got.day == 15 and (got.hour, got.minute) == (8, 30)           # the 4-a-day day is skipped
    assert S.AUTO == "auto"


def test_the_guarded_upload_records_who_chose_the_time(monkeypatch):
    import admin
    import upload_limits
    import publication_log
    seen = []

    class M:
        def upload(self, platform, path, on_session=None, **kw):
            seen.append(kw)
            return {"success": True, "upload_id": "x", "url": "u"}
    monkeypatch.setattr(upload_limits, "claim", lambda *a: True)
    monkeypatch.setattr(upload_limits, "release", lambda *a: None)
    monkeypatch.setattr(publication_log, "record_attempt", lambda **k: None)
    auto = datetime(2026, 12, 1, 12, 0, tzinfo=CR)
    monkeypatch.setattr(S, "next_free", lambda *a, **k: auto)
    r1 = admin._guarded_upload_unlocked(M(), "a", "youtube", __file__, title="t")
    assert r1["scheduled_by"] == "auto"
    r2 = admin._guarded_upload_unlocked(M(), "b", "youtube", __file__, title="t", scheduled_for=_at(14, 21, 15))
    assert r2["scheduled_by"] == "garcia" and "scheduled_by" not in seen[1]


def test_scheduling_a_past_time_from_revisar_is_refused_before_any_upload(monkeypatch):
    import admin
    import uploader
    monkeypatch.setattr(uploader, "get_upload_manager", lambda: (_ for _ in ()).throw(AssertionError("must not upload")))
    past = datetime.now(CR) - timedelta(minutes=5)
    failed = admin._schedule_approved({"name": "a", "path": Path("/nope.mp4")}, {}, ["youtube"], past)
    assert "ya pasó" in failed["youtube"]

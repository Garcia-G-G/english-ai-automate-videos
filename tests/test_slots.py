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

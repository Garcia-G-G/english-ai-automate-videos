"""STEP 85b §6: better thumbnails for what is published: only on ticks, YouTube only when the memo says yes, 40 a day."""
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from thumbs import better, publish  # noqa: E402


def R(status=200, text=""):
    return SimpleNamespace(status_code=status, ok=200 <= status < 300, json=lambda: {}, text=text)


def _video(root, name, stage="uploaded", size=(1080, 1920), sent=None, platform="youtube"):
    d = root / "output" / stage / "quiz"
    (d / f"{name}.thumb").mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (200, 30, 30)).save(d / f"{name}.thumb" / "thumb.jpg")
    meta = {"thumbnail": {"platforms": {platform: {"result": "ok", "sha": sent}}} if sent else {}}
    (d / f"{name}.json").write_text(json.dumps(meta))
    return d / f"{name}.thumb" / "thumb.jpg"


def _row(name, platform="youtube", vid="v1", at="2026-11-01"):
    return {"artifact": name, "platform": platform, "upload_id": vid, "published_at": at, "published_title": name}


def _memo(tmp_path, state):
    m = tmp_path / "caps.json"
    publish.remember(publish.SHORTS, state, "t", date(2026, 11, 1), m)
    return m


def test_it_proposes_only_videos_whose_thumbnail_differs_best_performers_first(tmp_path):
    _video(tmp_path, "a"), _video(tmp_path, "b")
    same = _video(tmp_path, "same")
    _video(tmp_path, "same", sent=better._sha(same))
    rows = [_row("a", vid="1"), _row("b", vid="2"), _row("same", vid="3")]
    out = better.proposals(rows, {"1": 10, "2": 500}, tmp_path, _memo(tmp_path, "yes"))
    assert [p["artifact"] for p in out] == ["b", "a"] and out[0]["views"] == 500


def test_youtube_is_left_out_unless_the_memo_says_yes_facebook_is_not(tmp_path):
    _video(tmp_path, "a"), _video(tmp_path, "f", platform="facebook")
    rows = [_row("a"), _row("f", "facebook", "9")]
    for state in ("no", "unknown"):
        assert [p["platform"] for p in better.proposals(rows, None, tmp_path, _memo(tmp_path, state))] == ["facebook"]
    assert len(better.proposals(rows, None, tmp_path, _memo(tmp_path, "yes"))) == 2


def test_a_16x9_video_uses_the_channel_memo_not_the_shorts_one(tmp_path):
    _video(tmp_path, "lesson", size=(1280, 720))
    memo = _memo(tmp_path, "yes")                                  # Shorts yes says nothing about long videos
    assert better.proposals([_row("lesson")], None, tmp_path, memo) == []
    publish.remember(publish.CHANNEL, "yes", "t", date(2026, 11, 1), memo)
    assert len(better.proposals([_row("lesson")], None, tmp_path, memo)) == 1


def test_nothing_is_sent_by_listing(tmp_path):
    _video(tmp_path, "a")
    calls = []
    better.proposals([_row("a")], None, tmp_path, _memo(tmp_path, "yes"))
    assert calls == []                                              # proposals() takes no HTTP callable at all


def _props(tmp_path, n):
    return [{"artifact": f"a{i}", "platform": "facebook", "video_id": str(i), "jpg": _video(tmp_path, f"a{i}", platform="facebook"), "vertical": True} for i in range(n)]


def test_apply_sends_only_what_it_is_given_and_stops_at_40_a_day(tmp_path):
    sent = []
    post = lambda url, **k: sent.append(url) or R(200)                                  # noqa: E731
    q, log = tmp_path / "q.json", tmp_path / "l.jsonl"
    res = better.apply(_props(tmp_path, 3), None, lambda: "tok", None, post, date(2026, 11, 2), q, tmp_path / "m.json", log)
    assert [r["result"] for r in res] == ["ok"] * 3 and len(sent) == 3 and better.used_today(date(2026, 11, 2), q) == 3
    q.write_text(json.dumps({"date": "2026-11-02", "count": 39}))
    res = better.apply(_props(tmp_path, 3), None, lambda: "tok", None, post, date(2026, 11, 2), q, tmp_path / "m.json", log)
    assert [r["result"] for r in res] == ["ok", "deferred", "deferred"] and len(sent) == 4
    assert better.used_today(date(2026, 11, 3), q) == 0                                # a new day starts at zero


def test_apply_records_the_sha_and_never_raises(tmp_path):
    log = tmp_path / "l.jsonl"
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("net"))                   # noqa: E731
    res = better.apply(_props(tmp_path, 1), None, lambda: "tok", None, boom, date(2026, 11, 2), tmp_path / "q.json", tmp_path / "m.json", log)
    assert res[0]["result"] == "error"
    ok = better.apply(_props(tmp_path, 1), None, lambda: "tok", None, lambda *a, **k: R(200), date(2026, 11, 2), tmp_path / "q2.json", tmp_path / "m.json", log)
    assert "sha" in json.loads(log.read_text().splitlines()[-1]) and ok[0]["result"] == "ok"


def test_apply_skips_youtube_when_the_memo_turned_to_no(tmp_path):
    p = {"artifact": "a", "platform": "youtube", "video_id": "1", "jpg": _video(tmp_path, "a"), "vertical": True}
    res = better.apply([p], lambda: "t", None, lambda *a, **k: R(200), lambda *a, **k: R(200), date(2026, 11, 2), tmp_path / "q.json", _memo(tmp_path, "no"), tmp_path / "l")
    assert res[0]["result"] == "skipped"

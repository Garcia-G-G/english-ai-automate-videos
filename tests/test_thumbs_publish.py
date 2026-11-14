"""STEP 85b §4: the thumbnail goes up after processing; the answer is remembered; nothing blocks an upload."""
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from thumbs import publish as P  # noqa: E402


def R(status=200, body=None, text=""):
    return SimpleNamespace(status_code=status, ok=200 <= status < 300, json=lambda: body or {}, text=text)


def _jpg(tmp_path):
    p = tmp_path / "thumb.jpg"
    p.write_bytes(b"jpg")
    return p


def test_it_waits_for_processing_with_backoff_then_gives_up_after_30_minutes():
    seq = [R(body={"items": [{"processingDetails": {"processingStatus": s}}]}) for s in ("processing", "processing", "succeeded")]
    sleeps = []
    assert P.wait_processed("v", "t", lambda *a, **k: seq.pop(0), sleeps.append) is True
    assert sleeps == [10, 16.0]
    never = lambda *a, **k: R(body={"items": [{"processingDetails": {"processingStatus": "processing"}}]})     # noqa: E731
    slept = []
    assert P.wait_processed("v", "t", never, slept.append, max_seconds=1800) is False and sum(slept) > 1800 - 130
    assert P.wait_processed("v", "t", lambda *a, **k: R(body={"items": [{"processingDetails": {"processingStatus": "failed"}}]}), lambda s: None) is False


@pytest.mark.parametrize("status,vertical,expected", [(200, True, "ok"), (403, True, "forbidden_shorts"), (403, False, "forbidden_channel"),
                                                       (429, True, "rate_limited"), (500, False, "error")])
def test_the_status_is_classified(status, vertical, expected):
    assert P.classify(status, vertical) == expected


def _ok_get(*a, **k):
    return R(body={"items": [{"processingDetails": {"processingStatus": "succeeded"}}]})


def test_a_403_on_a_short_is_remembered_and_the_next_call_is_skipped_for_30_days(tmp_path):
    memo = tmp_path / "caps.json"
    calls = []
    post = lambda *a, **k: calls.append(1) or R(403, text="forbidden")                   # noqa: E731
    out = P.youtube("v", _jpg(tmp_path), True, "t", _ok_get, post, lambda s: None, date(2026, 11, 14), memo)
    assert out["result"] == "forbidden_shorts" and P.capability(P.SHORTS, memo)["state"] == "no"
    again = P.youtube("v2", _jpg(tmp_path), True, "t", _ok_get, post, lambda s: None, date(2026, 12, 1), memo)
    assert again["result"] == "skipped" and len(calls) == 1
    later = P.youtube("v3", _jpg(tmp_path), True, "t", _ok_get, post, lambda s: None, date(2026, 12, 14), memo)
    assert later["result"] == "forbidden_shorts" and len(calls) == 2                      # re-checked on day 30


def test_success_is_remembered_as_yes_and_a_16x9_video_uses_its_own_key(tmp_path):
    memo = tmp_path / "caps.json"
    out = P.youtube("v", _jpg(tmp_path), True, "t", _ok_get, lambda *a, **k: R(200), lambda s: None, date(2026, 11, 14), memo)
    assert out["result"] == "ok" and P.capability(P.SHORTS, memo)["state"] == "yes" and P.capability(P.CHANNEL, memo)["state"] == "unknown"
    P.youtube("w", _jpg(tmp_path), False, "t", _ok_get, lambda *a, **k: R(403), lambda s: None, date(2026, 11, 14), memo)
    assert P.capability(P.CHANNEL, memo)["state"] == "no" and P.capability(P.SHORTS, memo)["state"] == "yes"


def test_a_thumbnail_error_never_raises_into_the_upload(tmp_path):
    def boom(*a, **k):
        raise RuntimeError("network")
    assert P.youtube("v", _jpg(tmp_path), True, "t", _ok_get, boom, lambda s: None, date(2026, 11, 14), tmp_path / "c.json")["result"] == "error"
    assert P.facebook("v", _jpg(tmp_path), "tok", boom)["result"] == "error"


def test_not_processed_in_time_is_reported_without_calling_the_thumbnail_api(tmp_path):
    calls = []
    never = lambda *a, **k: R(body={"items": []})                                        # noqa: E731
    out = P.youtube("v", _jpg(tmp_path), True, "t", never, lambda *a, **k: calls.append(1), lambda s: None, date(2026, 11, 14), tmp_path / "c.json")
    assert out["result"] == "not_processed" and not calls


def test_facebook_posts_the_image_as_the_preferred_thumbnail(tmp_path):
    seen = {}

    def post(url, **kw):
        seen.update(url=url, **kw)
        return R(200)
    assert P.facebook("123", _jpg(tmp_path), "tok", post)["result"] == "ok"
    assert seen["url"].endswith("/123/thumbnails") and seen["data"] == {"is_preferred": "true"} and "source" in seen["files"]
    assert P.facebook("123", _jpg(tmp_path), "tok", lambda *a, **k: R(403, text="perm"))["result"] == "forbidden"


def test_the_panel_line_says_what_is_known_in_spanish(tmp_path):
    memo = tmp_path / "c.json"
    assert "próximo Short lo prueba" in P.capability_line(path=memo)
    P.remember(P.SHORTS, "no", "403", date(2026, 11, 14), memo)
    assert P.capability_line(path=memo) == "YouTube aún no deja poner miniatura a los Shorts de este canal (se vuelve a probar el 14/12)."
    P.remember(P.SHORTS, "yes", "ok", date(2026, 11, 14), memo)
    assert "acepta" in P.capability_line(path=memo)


def test_the_answer_is_written_into_the_sidecar(tmp_path):
    side = tmp_path / "a.json"
    side.write_text(json.dumps({"thumbnail": {"chosen": "A"}}))
    P.record(side, "youtube", {"result": "forbidden_shorts", "message": "HTTP 403"})
    got = json.loads(side.read_text())["thumbnail"]
    assert got["chosen"] == "A" and got["platforms"]["youtube"]["result"] == "forbidden_shorts"


def test_the_daily_quota_stays_under_the_limit_at_four_uploads():
    q = P.daily_quota(4)
    assert q == {"used": 6600, "limit": 10000, "share": 0.66}


def test_the_follow_up_logs_the_outcome_and_survives_the_folder_moving(tmp_path):
    jpg = _jpg(tmp_path)
    log = tmp_path / "log.jsonl"
    out = P.after_youtube_upload("art", "vid", jpg, True, "tok", _ok_get, lambda *a, **k: R(403, text="no"), log, background=False, memo=tmp_path / "caps.json")
    jpg.unlink()                                                                         # the folder moved: the bytes were read first
    line = json.loads(log.read_text().splitlines()[0])
    assert out["result"] == "forbidden_shorts" and line["artifact"] == "art" and line["result"] == "forbidden_shorts"


def test_a_missing_image_means_no_follow_up_and_no_error(tmp_path):
    assert P.after_youtube_upload("a", "v", tmp_path / "none.jpg", True, "t", background=False) is None


# ── Facebook: wired after the reel is published ──────────────────────

def test_facebook_follow_up_posts_the_preferred_thumbnail_logs_it_and_never_leaks_the_token(tmp_path):
    calls = []
    log = tmp_path / "log.jsonl"
    out = P.after_facebook_upload("art", "999", _jpg(tmp_path), "SECRET", lambda url, **k: calls.append((url, k)) or R(200), log, background=False)
    assert out["result"] == "ok" and calls[0][0].endswith("/999/thumbnails") and calls[0][1]["data"] == {"is_preferred": "true"}
    line = json.loads(log.read_text().splitlines()[0])
    assert line["platform"] == "facebook" and line["video_id"] == "999" and "SECRET" not in log.read_text()


def test_facebook_refusal_or_error_is_recorded_and_the_reel_stays(tmp_path):
    log = tmp_path / "log.jsonl"
    denied = P.after_facebook_upload("a", "1", _jpg(tmp_path), "T", lambda *a, **k: R(403, text="perm"), log, background=False)
    boom = P.after_facebook_upload("b", "2", _jpg(tmp_path), "TOK", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("net TOK")), log, background=False)
    assert denied["result"] == "forbidden" and boom["result"] == "error" and "TOK" not in boom["message"]
    assert len(log.read_text().splitlines()) == 2


def test_facebook_without_a_token_is_recorded_not_raised(tmp_path, monkeypatch):
    monkeypatch.delenv("FB_PAGE_TOKEN", raising=False)
    out = P.after_facebook_upload("a", "1", _jpg(tmp_path), None, None, tmp_path / "l.jsonl", background=False)
    assert out["result"] == "forbidden" and "FB_PAGE_TOKEN" in out["message"]


def test_facebook_runs_in_the_background_by_default(tmp_path):
    t = P.after_facebook_upload("a", "1", _jpg(tmp_path), "T", lambda *a, **k: R(200), tmp_path / "l.jsonl")
    t.join(5)
    assert (tmp_path / "l.jsonl").exists()

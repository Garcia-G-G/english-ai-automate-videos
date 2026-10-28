#!/usr/bin/env python3
"""STEP 67: an upload error says Google's reason, and the panel knows the 24 h limit.

    python3 -m pytest tests/test_upload_limits.py

All HTTP is mocked. Nothing uploads.
"""
import json
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import uploader  # noqa: E402
import upload_limits as L  # noqa: E402

TOKEN = "ya29.secret-token-do-not-log"


class Resp:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = json.dumps(body)

    def json(self):
        return self._body


def _google(status, reason, message):
    return Resp(status, {"error": {"code": status, "message": message,
                                   "errors": [{"reason": reason, "message": message}]}})


def _upload(monkeypatch, tmp_path, init=None, chunk=None):
    monkeypatch.setattr(uploader.requests, "post", lambda url, **kw: init)
    monkeypatch.setattr(uploader.requests, "put", lambda *a, **k: chunk)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 16)
    yt = uploader.YouTubeUploader()
    yt._token_data = {"access_token": TOKEN}
    return yt.upload_video(str(video), "Título", "Desc", ["Tag"])


@pytest.mark.parametrize("status, reason, spanish", [
    (400, "uploadLimitExceeded", "el canal llegó a su límite de subidas de 24 h"),
    (403, "quotaExceeded", "Cuota diaria de la API agotada; vuelve mañana después de la 1:00."),
    (400, "invalidTitle", "YouTube rechazó el título (invalidTitle)."),
])
def test_the_init_reason_is_kept_and_said_in_spanish(monkeypatch, tmp_path, caplog, status, reason, spanish):
    caplog.set_level(logging.DEBUG)
    result = _upload(monkeypatch, tmp_path, init=_google(status, reason, "Google says why."))
    assert not result.success
    assert result.error == f"youtube {status} {reason}: Google says why."
    assert spanish in L.spanish(result.error)
    assert TOKEN not in caplog.text and "Authorization" not in caplog.text and "Bearer" not in caplog.text


def test_a_chunk_failure_keeps_its_reason_and_the_session(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    result = _upload(monkeypatch, tmp_path, init=Resp(200, {}, {"Location": "https://upload.example/s"}),
                     chunk=_google(403, "quotaExceeded", "Quota."))
    assert result.error == "youtube 403 quotaExceeded: Quota." and result.session_uri == "https://upload.example/s"
    assert TOKEN not in caplog.text


def _attempts(*published, failed=None):
    rows = [{"platform": "youtube", "status": "published", "at": t} for t in published]
    if failed:
        rows.append({"platform": "youtube", "status": "failed", "at": failed,
                     "detail": "youtube 400 uploadLimitExceeded: The user has exceeded the number of videos"})
    return rows


DAY = ["2026-10-15T17:35:17", "2026-10-15T17:35:22", "2026-10-15T17:35:26", "2026-10-15T23:48:18",
       "2026-10-15T23:48:54", "2026-10-16T00:13:01", "2026-10-16T00:13:05", "2026-10-16T00:13:11",
       "2026-10-16T10:47:52", "2026-10-16T10:47:57"]


def test_the_slot_is_the_oldest_upload_of_the_last_24_h_plus_24_h(tmp_path):
    path = tmp_path / "attempts.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in
                            _attempts("2026-10-14T09:25:36", *DAY, failed="2026-10-16T10:47:58")))
    from publication_log import read_attempts
    rows, now = read_attempts(path), datetime(2026, 10, 16, 16, 30)
    assert len(L.published_last_24h(rows, now)) == 10
    assert L.next_free_slot(rows, now) == datetime(2026, 10, 16, 17, 35, 17)
    assert L.limit_block(rows, now) == ("YouTube: el canal llegó a su límite de subidas de 24 h. "
                                        "Se libera hacia las 17:35.")
    assert L.limit_block(rows, datetime(2026, 10, 16, 17, 36)) is None       # the slot came
    assert L.limit_block(rows + _attempts("2026-10-16T16:40:00"), now) is None  # a later upload worked


def test_a_batch_stops_at_the_first_upload_limit():
    seen = []

    def one(video):
        seen.append(video)
        if video == "b":
            return [{"success": False, "error": "youtube 400 uploadLimitExceeded: no"}]
        return [{"success": True}]
    message = L.run_batch(["a", "b", "c", "d"], one)
    assert seen == ["a", "b"] and "límite de subidas" in message
    assert L.run_batch(["a"], lambda v: [{"success": False, "error": "youtube 400 invalidTitle: x"}]) is None


def test_a_double_press_makes_one_attempt(monkeypatch, tmp_path):
    """The second press, while the first upload runs, records nothing and sends nothing."""
    sys.modules.setdefault("streamlit", __import__("streamlit"))
    import admin
    import publication_log
    rows, release_first = [], threading.Event()
    monkeypatch.setattr(publication_log, "record_attempt", lambda **kw: rows.append(kw["status"]))

    class Manager:
        calls = 0

        def upload(self, platform, path, on_session=None, **kw):
            Manager.calls += 1
            release_first.wait(5)
            return {"success": False, "error": "youtube 400 uploadLimitExceeded: no"}
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    first = threading.Thread(target=admin._guarded_upload, args=(Manager(), "a1", "youtube", str(video)))
    first.start()
    while not rows:
        pass
    second = admin._guarded_upload(Manager(), "a1", "youtube", str(video))
    release_first.set()
    first.join(5)
    assert second.get("in_flight") and Manager.calls == 1
    assert rows == ["started", "failed"]

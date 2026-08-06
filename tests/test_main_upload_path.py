#!/usr/bin/env python3
"""main.py's upload path must record what it publishes.

    python3 -m pytest tests/test_main_upload_path.py

THE GAP THIS CLOSES. 0b996bc unified the two dashboard upload paths behind
resolve_upload_metadata so the record and the request could not describe
different text. main.py's upload_video was never in that scope: it built its
own metadata inline and never called publication_log at all — `grep` found
zero callers outside tests/.

That is the path `python main.py --batch N --upload` runs, so unattended
publishing would put videos live that nothing in this repo could name.

The API is stubbed. Nothing here uploads.
"""

import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import publication_log as PL  # noqa: E402

SCRIPT = {"question": "¿Qué significa 'fabric' en inglés?",
          "full_script": "¿Qué significa 'fabric' en inglés?",
          "hashtags": ["#LearnEnglish"],
          "_meta": {"category": "vocabulary"}}


class _Result:
    """Shaped like uploader.UploadResult."""
    def __init__(self, success=True, upload_id="vid123",
                 url="https://youtu.be/vid123", error=None):
        self.success, self.upload_id, self.url, self.error = (
            success, upload_id, url, error)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """main.upload_video with the uploader and the ledger both redirected."""
    import main

    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(PL, "LEDGER_PATH", ledger)
    monkeypatch.setattr(PL, "LEDGER_DIR", tmp_path)
    # The idempotency work added an attempt log and a post-publish file move.
    # Both must land in tmp_path, not in the repo's real output/.
    monkeypatch.setattr(PL, "ATTEMPTS_PATH", tmp_path / "attempts.jsonl")
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)

    sent = []

    class FakeManager:
        # on_session is passed by the real manager.upload as of the
        # idempotency change; the stub must accept it.
        def upload(self, platform, path, title=None, description=None,
                   hashtags=None, on_session=None):
            sent.append({"platform": platform, "path": path, "title": title,
                         "description": description, "hashtags": hashtags})
            if on_session:
                on_session("https://upload.example/s/1", 17)
            return rig.result

    fake_uploader = types.ModuleType("uploader")
    fake_uploader.UploadManager = FakeManager

    class VideoMetadata:
        def __init__(self, title, description, hashtags, privacy="public"):
            self.title, self.description = title, description
            self.hashtags, self.privacy = hashtags, privacy

        @property
        def full_description(self):
            return self.description

    fake_uploader.VideoMetadata = VideoMetadata
    monkeypatch.setitem(sys.modules, "uploader", fake_uploader)

    video = tmp_path / "fabric_20260804_101010.mp4"
    video.write_bytes(b"not really an mp4")

    rig.main, rig.sent, rig.ledger, rig.video = main, sent, ledger, video
    rig.result = _Result()
    return rig


def _rows(ledger):
    if not ledger.exists():
        return []
    return [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]


# ── the ledger row ───────────────────────────────────────────────────

def test_a_successful_upload_writes_a_ledger_row(rig):
    """The whole point. Before this, --batch --upload left no record."""
    out = rig.main.upload_video(rig.video, "quiz", SCRIPT, ["youtube"])

    rows = _rows(rig.ledger)
    assert len(rows) == 1, f"no ledger row written; outcome={out}"
    assert rows[0]["platform"] == "youtube"
    assert rows[0]["upload_id"] == "vid123"
    assert rows[0]["url"] == "https://youtu.be/vid123"


def test_the_row_carries_the_POST_adaptation_title(rig):
    """record_publication's docstring requires the strings actually handed to
    the API. Recording the pre-adaptation title is what made the previous
    record unjoinable to the live video — it was missing #Shorts."""
    rig.main.upload_video(rig.video, "quiz", SCRIPT, ["youtube"])

    row = _rows(rig.ledger)[0]
    assert row["published_title"] == rig.sent[0]["title"], (
        "recorded a different title than the one sent")
    assert row["published_description"] == rig.sent[0]["description"]


def test_the_artifact_key_matches_the_dashboard_convention(rig):
    """admin.py records video_file.stem. A different key here would make the
    two paths' rows unjoinable."""
    rig.main.upload_video(rig.video, "quiz", SCRIPT, ["youtube"],
                          artifact=rig.video.stem)

    assert _rows(rig.ledger)[0]["artifact"] == "fabric_20260804_101010"


def test_the_key_defaults_to_the_video_stem_when_not_passed(rig):
    rig.main.upload_video(rig.video, "quiz", SCRIPT, ["youtube"])

    assert _rows(rig.ledger)[0]["artifact"] == "fabric_20260804_101010"


def test_every_platform_gets_its_own_row(rig):
    """One row per publication, not one per artifact — each platform has its
    own id and its own adapted text."""
    rig.main.upload_video(rig.video, "quiz", SCRIPT, ["youtube", "tiktok"])

    assert sorted(r["platform"] for r in _rows(rig.ledger)) == ["tiktok", "youtube"]


# ── failures are not recorded, and not lost ──────────────────────────

def test_a_failed_upload_writes_no_row(rig):
    rig.result = _Result(success=False, upload_id=None, url=None,
                         error="quota exceeded")

    out = rig.main.upload_video(rig.video, "quiz", SCRIPT, ["youtube"])

    assert _rows(rig.ledger) == []
    assert out["uploaded"] == []


def test_a_failed_upload_is_returned_not_swallowed(rig):
    """The old body wrapped everything in `except Exception`, logged one line
    and returned None, so a batch could not tell success from failure."""
    rig.result = _Result(success=False, error="quota exceeded")

    out = rig.main.upload_video(rig.video, "quiz", SCRIPT, ["youtube"])

    assert out["errors"], "the failure did not reach the caller"
    assert "quota exceeded" in out["errors"][0]["error"]


def test_a_raising_platform_does_not_stop_the_next_one(rig):
    """A YouTube exception must not silently cost the Instagram upload."""
    calls = []

    class Boom:
        def upload(self, platform, path, **kw):
            calls.append(platform)
            if platform == "youtube":
                raise RuntimeError("connection reset")
            return _Result(upload_id="tk1", url="https://tiktok/tk1")

    sys.modules["uploader"].UploadManager = Boom

    out = rig.main.upload_video(rig.video, "quiz", SCRIPT, ["youtube", "tiktok"])

    assert calls == ["youtube", "tiktok"]
    assert out["uploaded"] == ["tiktok"]
    assert out["errors"][0]["platform"] == "youtube"
    assert "connection reset" in out["errors"][0]["error"]


def test_a_live_upload_that_cannot_be_recorded_is_reported_as_unrecorded(rig,
                                                                        monkeypatch):
    """The worst case: the video IS live and the record failed. Headless there
    is no operator to show a banner to, so it has to come back in the outcome
    or it is lost entirely."""
    def boom(**kw):
        raise PL.PublicationRecordError("disk full")

    monkeypatch.setattr(PL, "record_upload_result", boom)

    out = rig.main.upload_video(rig.video, "quiz", SCRIPT, ["youtube"])

    assert out["uploaded"] == ["youtube"], "the upload did happen"
    assert out["unrecorded"] == ["youtube"]
    assert any(e["stage"] == "record" for e in out["errors"])


def test_no_configured_platforms_is_not_an_error(rig):
    out = rig.main.upload_video(rig.video, "quiz", SCRIPT, [])

    assert out["errors"] == []
    assert _rows(rig.ledger) == []


# ── one resolver, three paths ────────────────────────────────────────

def test_main_uses_the_shared_resolver_not_its_own_copy():
    """It used to call generate_metadata + adapt_for_platform inline — a third
    copy of the resolver, on the one path with no operator watching."""
    src = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "resolve_upload_metadata(" in src
    assert "NO_OPERATOR_EDITS" in src, (
        "headless callers must declare that there are no operator edits")
    assert "adapt_for_platform(meta, platform_key)" not in src, (
        "main.py is adapting generated metadata inline again")


def test_there_is_exactly_one_recorder():
    """Two recorders drift. admin.py and main.py must both go through
    publication_log.record_upload_result."""
    import ast
    defs = 0
    for f in ("src/publication_log.py", "src/admin.py", "main.py"):
        tree = ast.parse((ROOT / f).read_text(encoding="utf-8"))
        defs += sum(1 for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef)
                    and n.name == "record_upload_result")
    assert defs == 1, f"expected one definition, found {defs}"

    for f in ("src/admin.py", "main.py"):
        assert "record_upload_result(" in (ROOT / f).read_text(encoding="utf-8"), (
            f"{f} does not use the shared recorder")


def test_main_no_longer_swallows_every_exception():
    """main.py:200-203 used to wrap the entire function body."""
    import ast
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "upload_video")

    # No handler may both catch bare Exception and end the function silently.
    for handler in [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]:
        if isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
            names = {n.id for n in ast.walk(handler) if isinstance(n, ast.Name)}
            assert "logger" in names, "bare except with no logging"
            assert not any(isinstance(n, ast.Return) and n.value is None
                           for n in ast.walk(handler)), (
                "bare except returns None — the failure is lost")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

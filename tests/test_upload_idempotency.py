#!/usr/bin/env python3
"""The same video must not be published twice — and retries must still work.

    python3 -m pytest tests/test_upload_idempotency.py

THE DEFECT. hPdSoqjvu3E and IvO969ZeQsM are the same video published three
minutes apart, first private then public: a retry that left the first live.
The window is structural. Every path does

    result = manager.upload(...)      # the video is now LIVE
    if result.success:
        record_publication(...)       # may fail; may never be reached

and between those two statements nothing on disk says the video exists.

The HTTP layer is stubbed. Nothing here uploads.
"""

import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import uploader as _real_uploader  # noqa: E402
sys.path.insert(0, str(ROOT))

import publication_log as PL  # noqa: E402
import upload_guard as G  # noqa: E402

SCRIPT = {"question": "¿Qué significa 'fabric'?", "full_script": "x" * 20,
          "video_title": "Título", "hashtags": ["#LearnEnglish"],
          "_meta": {"category": "vocabulary"}}


class Rig:
    """main.upload_video with the uploader, ledger and attempts redirected."""

    def __init__(self, tmp_path, monkeypatch):
        import main
        self.main = main
        self.tmp = tmp_path
        self.ledger = tmp_path / "ledger.jsonl"
        self.attempts = tmp_path / "attempts.jsonl"
        monkeypatch.setattr(PL, "LEDGER_PATH", self.ledger)
        monkeypatch.setattr(PL, "LEDGER_DIR", tmp_path)
        monkeypatch.setattr(PL, "ATTEMPTS_PATH", self.attempts)

        self.calls = []          # every manager.upload() that reached HTTP
        self.session_queries = []
        self.init_fails = False
        self.record_raises = False
        self.session_state = "published"   # what a session query replies

        rig = self

        class FakeYouTube:
            """Stands in for YouTubeUploader."""
            def authenticate(self):
                return True

            def query_session(self, uri, size):
                rig.session_queries.append((uri, size))
                if rig.session_state == "published":
                    return {"state": "published", "upload_id": "vid_recovered",
                            "detail": "201 replay"}
                return {"state": rig.session_state, "upload_id": None,
                        "detail": "stub"}

        class FakeManager:
            uploaders = {"youtube": FakeYouTube()}

            def upload(self, platform, path, title=None, description=None,
                       hashtags=None, on_session=None):
                rig.calls.append({"platform": platform, "title": title})
                if rig.init_fails:
                    # Init 500: no session was ever created, nothing is live.
                    return {"success": False, "error": "init 500",
                            "upload_id": None, "url": None, "session_uri": None}
                if on_session:
                    on_session("https://upload.example/session/abc", 1234)
                return {"success": True, "upload_id": "vid123",
                        "url": "https://youtu.be/vid123",
                        "error": None,
                        "session_uri": "https://upload.example/session/abc"}

        fake = types.ModuleType("uploader")
        fake.UploadManager = FakeManager

        class VideoMetadata:
            def __init__(self, title, description, hashtags):
                self.title, self.description = title, description
                self.hashtags = hashtags

            @property
            def full_description(self):
                return self.description

        fake.VideoMetadata = VideoMetadata
        # The REAL resolver, not a stand-in. A fake privacy table here would
        # be a second place the answer is decided, which is the whole defect
        # this stub is standing in front of.
        fake.resolve_privacy = _real_uploader.resolve_privacy
        monkeypatch.setitem(sys.modules, "uploader", fake)

        vdir = tmp_path / "video" / "quiz"
        vdir.mkdir(parents=True)
        self.video = vdir / "fabric_20260806_101010.mp4"
        self.video.write_bytes(b"x" * 1234)
        monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)

        real_record = PL.record_upload_result

        def maybe_raise(**kw):
            if rig.record_raises:
                raise PL.PublicationRecordError("disk full")
            return real_record(**kw)

        monkeypatch.setattr(PL, "record_upload_result", maybe_raise)

    def run(self, **kw):
        return self.main.upload_video(self.video, "quiz", SCRIPT, ["youtube"], **kw)

    @property
    def rows(self):
        if not self.ledger.exists():
            return []
        return [json.loads(l) for l in self.ledger.read_text().splitlines() if l.strip()]

    @property
    def attempt_rows(self):
        if not self.attempts.exists():
            return []
        return [json.loads(l) for l in self.attempts.read_text().splitlines() if l.strip()]


@pytest.fixture
def rig(tmp_path, monkeypatch):
    return Rig(tmp_path, monkeypatch)


# ── T1: uploaded twice -> exactly one publication ────────────────────

def test_T1_the_same_artifact_uploaded_twice_publishes_once(rig):
    first = rig.run()
    second = rig.run()

    assert len(rig.rows) == 1, f"published {len(rig.rows)} times"
    assert len(rig.calls) == 1, (
        f"the second run reached the upload API {len(rig.calls)} times")
    assert first["recorded"] == ["youtube"]
    assert second["skipped"] == ["youtube"]


def test_T1_the_skip_is_reported_not_silent(rig):
    rig.run()
    out = rig.run()

    assert out["skipped"] == ["youtube"]
    assert out["uploaded"] == []


# ── T2: the case that produced the live duplicate ────────────────────

def test_T2_upload_succeeds_record_dies_next_run_does_NOT_republish(rig):
    """THE ONE THAT MATTERS. The upload lands, recording raises, the process
    dies before any ledger row exists. On the next run the ledger says
    "never published" — because the row is exactly what did not get written.
    Only the attempt log can tell the difference."""
    rig.record_raises = True
    first = rig.run()

    assert first["uploaded"] == ["youtube"], "the upload did happen"
    assert rig.rows == [], "no ledger row was written, as in the real failure"

    # process dies here. next run:
    rig.record_raises = False
    second = rig.run()

    assert len(rig.calls) == 1, (
        "SECOND UPLOAD ISSUED — this is the hPdSoqjvu3E duplicate")
    assert second["skipped"] == ["youtube"]
    assert rig.session_queries, "did not reconcile against the session URI"


def test_T2_the_recovered_publication_is_backfilled(rig):
    """Having discovered the video is live, the guard must write the row that
    was lost. Otherwise every future run pays the reconcile round-trip and
    the repo still cannot name the video."""
    rig.record_raises = True
    rig.run()
    rig.record_raises = False
    rig.run()

    assert len(rig.rows) == 1
    assert rig.rows[0]["upload_id"] == "vid_recovered"


def test_T2_a_third_run_takes_the_cheap_path(rig):
    rig.record_raises = True
    rig.run()
    rig.record_raises = False
    rig.run()
    n_queries = len(rig.session_queries)
    rig.run()

    assert len(rig.session_queries) == n_queries, (
        "re-queried the platform when the ledger already had the answer")
    assert len(rig.rows) == 1


# ── T3: a legitimate retry must still publish ────────────────────────

def test_T3_a_genuinely_failed_upload_is_retried(rig):
    """An idempotency guard that blocks real retries is worse than the
    duplicate: it fails silently and forever."""
    rig.init_fails = True
    first = rig.run()

    assert first["uploaded"] == []
    assert rig.rows == []

    rig.init_fails = False
    second = rig.run()

    assert len(rig.calls) == 2, "the retry was blocked"
    assert second["recorded"] == ["youtube"]
    assert len(rig.rows) == 1


def test_T3_no_session_means_no_reconcile_round_trip(rig):
    """Init failed, so no session exists and nothing can be live. The guard
    must not hold the retry waiting for a human."""
    rig.init_fails = True
    rig.run()
    rig.init_fails = False
    out = rig.run()

    assert rig.session_queries == []
    assert out["held"] == []


# ── the ambiguous case is held, not guessed ──────────────────────────

def test_an_undeterminable_session_holds_instead_of_guessing(rig):
    """404 = the session URI expired. That says nothing about whether the
    upload completed first, so neither retrying nor skipping is safe."""
    rig.record_raises = True
    rig.run()
    rig.record_raises = False
    rig.session_state = "unknown"

    out = rig.run()

    assert out["held"] == ["youtube"]
    assert len(rig.calls) == 1, "uploaded despite an undetermined state"
    assert rig.rows == []


def test_an_incomplete_session_is_safe_to_retry(rig):
    """308 = bytes still missing, so YouTube never created the video."""
    rig.record_raises = True
    rig.run()
    rig.record_raises = False
    rig.session_state = "incomplete"

    out = rig.run()

    assert len(rig.calls) == 2
    assert out["recorded"] == ["youtube"]


# ── the attempt record itself ────────────────────────────────────────

def test_the_attempt_is_written_before_any_upload_call(rig):
    order = []
    real = PL.record_attempt
    import main as M

    def spy(**kw):
        order.append(("attempt", kw["status"]))
        return real(**kw)

    orig_upload = sys.modules["uploader"].UploadManager.upload

    def spy_upload(self, *a, **k):
        order.append(("upload", None))
        return orig_upload(self, *a, **k)

    PL.record_attempt = spy
    sys.modules["uploader"].UploadManager.upload = spy_upload
    try:
        rig.run()
    finally:
        PL.record_attempt = real
        sys.modules["uploader"].UploadManager.upload = orig_upload

    assert order[0] == ("attempt", "started"), order
    assert order.index(("upload", None)) > 0


def test_the_attempt_carries_the_resumable_session_uri(rig):
    rig.run()

    uris = [r["session_uri"] for r in rig.attempt_rows if r.get("session_uri")]
    assert uris, "no attempt row carried the session URI"
    assert uris[0] == "https://upload.example/session/abc"


def test_attempts_are_not_written_to_the_ledger(rig):
    """They live in their own file. A status row in the ledger would change
    what unrecorded_platforms returns for every existing caller."""
    rig.record_raises = True
    rig.run()

    assert rig.rows == []
    assert rig.attempt_rows, "attempts went nowhere"
    assert PL.unrecorded_platforms(
        "fabric_20260806_101010", ["youtube"], self_path(rig)) == ["youtube"]


def self_path(rig):
    return rig.ledger


# ── the second vector: the file left in the upload queue ─────────────

def test_a_published_video_is_moved_out_of_the_queue(rig):
    rig.run()

    assert not rig.video.exists(), "published video left where it can be re-uploaded"
    assert (rig.tmp / "uploaded" / "quiz" / rig.video.name).exists()


def test_a_failed_upload_leaves_the_file_alone(rig):
    rig.init_fails = True
    rig.run()

    assert rig.video.exists(), "moved a video that was never published"


def test_the_dashboard_list_consults_the_ledger():
    """Moving the file is not enough on its own — a move can fail and a
    re-render puts it back. The list itself must know."""
    import ast
    src = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "get_approved_videos")
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}

    assert "find_by_artifact" in names, (
        "get_approved_videos does not consult the ledger; a published video "
        "still sitting in approved/ would be offered for upload again")


# ── every call site is guarded ───────────────────────────────────────

def test_all_three_upload_call_sites_go_through_the_guard():
    import ast
    admin = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    main_src = (ROOT / "main.py").read_text(encoding="utf-8")

    assert admin.count("_guard_decide(") >= 3, (
        "expected the helper plus both dashboard call sites")
    assert "decide(" in main_src and "upload_guard" in main_src

    # No dashboard path may reach manager.upload directly. AST, not a
    # substring: _guarded_upload's OWN call is the one legitimate site, and a
    # text search cannot tell it apart from an unguarded one.
    tree = ast.parse(admin)
    offenders = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        if fn.name == "_guarded_upload":
            continue
        for call in ast.walk(fn):
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "upload"
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "manager"):
                offenders.append(f"{fn.name}:{call.lineno}")

    # module-level code (the Streamlit page bodies) too
    for call in ast.walk(tree):
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "upload"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "manager"
                and not any(call.lineno == int(o.split(":")[1]) for o in offenders)):
            src_line = admin.splitlines()[call.lineno - 1]
            if "_guarded_upload" not in src_line:
                offenders.append(f"<module>:{call.lineno}")

    guarded_lineno = next(
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_guarded_upload")
    offenders = [o for o in offenders
                 if not (guarded_lineno <= int(o.split(":")[1]) <= guarded_lineno + 40)]

    assert not offenders, (
        f"unguarded manager.upload call(s) in admin.py at {offenders}")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

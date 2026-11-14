"""Instagram and Facebook Reels publishers, against a fake Graph API.

No network: requests.get/post are replaced by a router that answers by URL
fragment, in order, and records every call.
"""
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta

import pytest
import requests

import publication_log as PL
import uploader
from publishers import FacebookReelsPublisher, InstagramReelsPublisher, common, schedule
from publishers import meta_instagram as IG
from publishers.common import ReelSpecError, validate_reel

# One token since STEP 72: Instagram publishes through the Page with the Page token.
TOKEN = PAGE_TOKEN = "PAGEtoken-SECRET-987654321"
IG_ID = "17841400000000000"

GOOD_PROBE = {"format": {"duration": "30.0"},
              "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080,
                           "height": 1920, "avg_frame_rate": "30/1"},
                          {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"}]}


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body if body is not None else {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class Router:
    """routes: list of (method, url fragment, response or exception). First match is consumed."""

    def __init__(self, monkeypatch, routes):
        self.routes, self.calls = list(routes), []
        monkeypatch.setattr(requests, "get", lambda url, **kw: self("get", url, kw))
        monkeypatch.setattr(requests, "post", lambda url, **kw: self("post", url, kw))

    def __call__(self, method, url, kw):
        if hasattr(kw.get("data"), "read"):              # a streamed body: keep its bytes
            kw = {**kw, "body": kw["data"].read()}
        self.calls.append((method, url, kw))
        for i, (m, frag, resp) in enumerate(self.routes):
            if m == method and frag in url:
                del self.routes[i]
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"unexpected {method} {url}")

    def hit(self, frag):
        return [c for c in self.calls if frag in c[1]]


def err(code, sub=None, status=400, msg="boom"):
    return Resp(status, {"error": {"code": code, "error_subcode": sub, "message": msg}})


@pytest.fixture
def video(tmp_path, monkeypatch):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\0" * 1024)
    monkeypatch.setattr(common, "probe", lambda p: GOOD_PROBE)
    return str(path)


@pytest.fixture
def fb_env(monkeypatch):
    monkeypatch.setenv("FB_PAGE_ID", "1234567890")
    monkeypatch.setenv("FB_PAGE_TOKEN", PAGE_TOKEN)


@pytest.fixture
def ig_env(fb_env, monkeypatch):
    """The Page's credentials, and its Instagram id already cached (no lookup unless a test wants one)."""
    monkeypatch.delenv("IG_USER_ID", raising=False)
    monkeypatch.setattr(IG.time, "sleep", lambda s: None)
    uploader._ensure_token_dir()
    (uploader.TOKEN_DIR / IG.IDS_FILE).write_text(json.dumps(
        {"page_id": "1234567890", "id": IG_ID, "username": "eu"}))


def linked(ig_id=IG_ID):
    return ("get", "/1234567890", Resp(body={"name": "Page", "id": "1234567890",
                                             "instagram_business_account": {"id": ig_id, "username": "eu"}}))


def quota(used=1, total=50):
    return ("get", "content_publishing_limit",
            Resp(body={"data": [{"quota_usage": used, "config": {"quota_total": total}}]}))


# ── Instagram ───────────────────────────────────────────────────────────

def test_instagram_publishes_after_the_container_is_ready(ig_env, video, monkeypatch):
    sessions = []
    r = Router(monkeypatch, [
        quota(),
        ("post", "/media", Resp(body={"id": "C1", "uri": "https://rupload.facebook.com/ig-api-upload/v26.0/C1"})),
        ("post", "rupload.facebook.com/ig-api-upload/v26.0/C1", Resp(body={"success": True})),
        ("get", "/C1", Resp(body={"status_code": "IN_PROGRESS"})),
        ("get", "/C1", Resp(body={"status_code": "FINISHED"})),
        ("post", "/media_publish", Resp(body={"id": "M9"})),
        ("get", "/M9", Resp(body={"permalink": "https://www.instagram.com/reel/abc/"})),
    ])
    res = InstagramReelsPublisher().publish(video, "Hola", ["AprendeInglés"],
                                            on_session=lambda h, s: sessions.append((h, len(r.calls))))
    assert res.success and res.upload_id == "M9"
    assert res.url == "https://www.instagram.com/reel/abc/"
    assert sessions == [("C1", 2)]                       # before the bytes went
    method, url, kw = r.hit("/media")[0]
    assert url == f"https://graph.facebook.com/v26.0/{IG_ID}/media"
    created = kw["data"]
    assert created["media_type"] == "REELS" and created["upload_type"] == "resumable"
    assert "video_url" not in created and created["share_to_feed"] == "true"
    assert created["caption"] == "Hola\n\n#AprendeInglés"
    up = r.hit("rupload")[0][2]
    assert up["headers"] == {"Authorization": f"OAuth {TOKEN}", "offset": "0", "file_size": "1024"}
    assert up["body"] == b"\0" * 1024                     # the raw file, nothing around it
    assert all(c[1].startswith(("https://graph.facebook.com/", "https://rupload.facebook.com/")) for c in r.calls)


def test_instagram_builds_the_upload_uri_when_the_container_has_none(ig_env, video, monkeypatch):
    r = Router(monkeypatch, [quota(), ("post", "/media", Resp(body={"id": "C7"})),
                             ("post", "rupload", Resp(body={"success": True})),
                             ("get", "/C7", Resp(body={"status_code": "FINISHED"})),
                             ("post", "/media_publish", Resp(body={"id": "M7"})),
                             ("get", "/M7", Resp(body={"permalink": "p"}))])
    assert InstagramReelsPublisher().publish(video, "x", []).success
    assert r.hit("rupload")[0][1] == "https://rupload.facebook.com/ig-api-upload/v26.0/C7"


def test_instagram_container_never_ready_does_not_publish(ig_env, video, monkeypatch):
    r = Router(monkeypatch, [quota(),
                             ("post", "/media", Resp(body={"id": "C2"})),
                             ("post", "rupload", Resp(body={"success": True}))]
               + [("get", "/C2", Resp(body={"status_code": "IN_PROGRESS"}))] * IG.POLL_ATTEMPTS)
    res = InstagramReelsPublisher().publish(video, "x", [])
    assert not res.success and "IN_PROGRESS" in res.error and res.session_uri == "C2"
    assert not r.hit("media_publish") and not res.in_doubt


def test_instagram_quota_used_up_stops_before_any_upload(ig_env, video, monkeypatch):
    r = Router(monkeypatch, [quota(used=50, total=50)])
    res = InstagramReelsPublisher().publish(video, "x", [])
    assert not res.success and "publishing limit" in res.error
    assert len(r.calls) == 1


def test_instagram_rate_limit_error_on_publish_is_a_plain_failure(ig_env, video, monkeypatch):
    Router(monkeypatch, [quota(), ("post", "/media", Resp(body={"id": "C3"})),
                         ("post", "rupload", Resp(body={"success": True})),
                         ("get", "/C3", Resp(body={"status_code": "FINISHED"})),
                         ("post", "media_publish", err(9, 2207042, 403, "max posts"))])
    res = InstagramReelsPublisher().publish(video, "x", [])
    assert not res.success and not res.in_doubt and "2207042" in res.error


def test_instagram_expired_token_never_leaks_it(ig_env, video, monkeypatch):
    Router(monkeypatch, [("get", "content_publishing_limit", err(190, 463, 400, f"bad {TOKEN}"))])
    res = InstagramReelsPublisher().publish(video, "x", [])
    assert not res.success and "code=190" in res.error and TOKEN not in res.error


def test_network_errors_are_redacted(ig_env, video, monkeypatch):
    Router(monkeypatch, [("get", "content_publishing_limit",
                          requests.ConnectionError(f"Max retries with url: /x?access_token={TOKEN}"))])
    res = InstagramReelsPublisher().publish(video, "x", [])
    assert not res.success and TOKEN not in res.error and "***" in res.error


def test_the_instagram_id_is_the_pages_looked_up_once_and_cached_privately(ig_env, monkeypatch):
    (uploader.TOKEN_DIR / IG.IDS_FILE).unlink()
    monkeypatch.setenv("IG_USER_ID", "999")                 # the old Instagram-Login id: never used
    r = Router(monkeypatch, [linked()])
    assert InstagramReelsPublisher().user_id == IG_ID
    assert r.calls[0][2]["params"]["fields"] == "instagram_business_account{id,username}"
    path = uploader.TOKEN_DIR / IG.IDS_FILE
    assert json.loads(path.read_text())["id"] == IG_ID and oct(path.stat().st_mode & 0o777) == "0o600"
    assert InstagramReelsPublisher().user_id == IG_ID and len(r.calls) == 1


def test_a_page_without_instagram_says_so(ig_env, video, monkeypatch):
    (uploader.TOKEN_DIR / IG.IDS_FILE).unlink()
    Router(monkeypatch, [("get", "/1234567890", Resp(body={"id": "1234567890"}))])
    res = InstagramReelsPublisher().publish(video, "x", [])
    assert not res.success and IG.NOT_LINKED in res.error
    assert not (uploader.TOKEN_DIR / IG.IDS_FILE).exists()


def test_instagram_lost_publish_answer_checks_the_container(ig_env, video, monkeypatch):
    base = [quota(), ("post", "/media", Resp(body={"id": "C4"})), ("post", "rupload", Resp()),
            ("get", "/C4", Resp(body={"status_code": "FINISHED"})),
            ("post", "media_publish", requests.Timeout("read timed out"))]
    Router(monkeypatch, base + [("get", "/C4", Resp(body={"status_code": "PUBLISHED"}))])
    assert InstagramReelsPublisher().publish(video, "x", []).success
    Router(monkeypatch, base + [("get", "/C4", requests.ConnectionError("down"))])
    res = InstagramReelsPublisher().publish(video, "x", [])
    assert not res.success and res.in_doubt and res.session_uri == "C4"


def test_instagram_unexpected_error_after_upload_is_in_doubt(ig_env, video, monkeypatch):
    Router(monkeypatch, [quota(), ("post", "/media", Resp(body={"id": "C5"})), ("post", "rupload", Resp()),
                         ("get", "/C5", Resp(body={"status_code": "FINISHED"})),
                         ("post", "media_publish", Resp(body={}))])          # 200 with no id
    res = InstagramReelsPublisher().publish(video, "x", [])
    assert not res.success and res.in_doubt and res.session_uri == "C5"


def test_a_finished_unpublished_container_is_held_not_replaced(ig_env, monkeypatch):
    from upload_guard import SKIP_HOLD, decide
    PL.record_attempt(artifact="v3", platform="instagram", status=PL.ATTEMPT_UNKNOWN, session_uri="C6")
    Router(monkeypatch, [("get", "/C6", Resp(body={"status_code": "FINISHED"}))])
    assert decide("v3", "instagram", manager=uploader.UploadManager()).action == SKIP_HOLD


def test_facebook_finish_success_false_is_not_recorded_as_published(fb_env, video, monkeypatch):
    Router(monkeypatch, fb_start() + [("post", "video_reels", Resp(body={"success": False}))])
    res = FacebookReelsPublisher().publish(video, "x", [])
    assert not res.success and "success=false" in res.error


# ── Facebook ────────────────────────────────────────────────────────────

def fb_start():
    return [("post", "video_reels", Resp(body={"video_id": "V1",
                                               "upload_url": "https://rupload.facebook.com/video-upload/v26.0/V1"})),
            ("post", "rupload.facebook.com/video-upload/v26.0/V1", Resp(body={"success": True}))]


def test_facebook_publishes_a_reel(fb_env, video, monkeypatch):
    r = Router(monkeypatch, fb_start() + [
        ("post", "video_reels", Resp(body={"success": True})),
        ("get", "/V1", Resp(body={"permalink_url": "/reel/V1"}))])
    res = FacebookReelsPublisher().publish(video, "Hola", ["Inglés"])
    assert res.success and res.upload_id == "V1" and res.url == "https://www.facebook.com/reel/V1"
    finish = r.hit("video_reels")[1][2]["data"]
    assert finish["upload_phase"] == "finish" and finish["video_state"] == "PUBLISHED"
    assert finish["description"] == "Hola\n\n#Inglés"


@pytest.mark.parametrize("status,ok,doubt", [
    ({"video_status": "processing", "uploading_phase": {"status": "complete"},
      "publishing_phase": {"status": "complete", "publish_status": "published"}}, True, False),
    ({"video_status": "upload_complete", "uploading_phase": {"status": "complete"},
      "publishing_phase": {"status": "not_started"}}, False, True),   # may not be processed yet
    (None, False, True),
])
def test_facebook_lost_finish_answer_checks_status_and_never_finishes_twice(
        fb_env, video, monkeypatch, status, ok, doubt):
    r = Router(monkeypatch, fb_start() + [
        ("post", "video_reels", requests.Timeout("read timed out")),
        ("get", "/V1", Resp(body={"status": status}) if status else requests.ConnectionError("down")),
        ("get", "/V1", Resp(body={}))])
    res = FacebookReelsPublisher().publish(video, "x", [])
    assert (res.success, res.in_doubt) == (ok, doubt)
    assert len([c for c in r.hit("video_reels") if c[2]["data"]["upload_phase"] == "finish"]) == 1


def test_facebook_daily_limit_comes_from_the_attempt_log(fb_env, video, monkeypatch):
    for i in range(30):
        PL.record_attempt(artifact=f"a{i}", platform="facebook", status=PL.ATTEMPT_PUBLISHED)
    r = Router(monkeypatch, [])
    res = FacebookReelsPublisher().publish(video, "x", [])
    assert not res.success and "30/30" in res.error and not r.calls


def test_facebook_expired_page_token(fb_env, video, monkeypatch):
    Router(monkeypatch, [("post", "video_reels", err(190, 463, 400, "Session has expired"))])
    res = FacebookReelsPublisher().publish(video, "x", [])
    assert not res.success and "code=190" in res.error and PAGE_TOKEN not in res.error


# ── spec validation ─────────────────────────────────────────────────────

def test_validation_lists_every_problem(tmp_path):
    path = tmp_path / "v.mp4"
    path.write_bytes(b"x")
    bad = {"format": {"duration": "120"},
           "streams": [{"codec_type": "video", "codec_name": "vp9", "width": 1920, "height": 1080,
                        "avg_frame_rate": "15/1"},
                       {"codec_type": "audio", "codec_name": "mp3", "sample_rate": "96000"}]}
    with pytest.raises(ReelSpecError) as exc:
        validate_reel(str(path), "facebook", bad)
    for part in ("vp9", "9:16", "120.0s", "15.00 fps", "mp3", "96000"):
        assert part in str(exc.value)
    assert validate_reel(str(path), "instagram", GOOD_PROBE)
    mkv = tmp_path / "v.mkv"
    mkv.write_bytes(b"x")
    with pytest.raises(ReelSpecError, match="mp4 or .mov"):
        validate_reel(str(mkv), "instagram", GOOD_PROBE)


def test_a_bad_file_fails_before_any_request(ig_env, tmp_path, monkeypatch):
    path = tmp_path / "wide.mp4"
    path.write_bytes(b"x")
    monkeypatch.setattr(common, "probe", lambda p: {**GOOD_PROBE, "streams": [
        {**GOOD_PROBE["streams"][0], "width": 1920, "height": 1080}]})
    r = Router(monkeypatch, [])
    res = InstagramReelsPublisher().publish(str(path), "x", [])
    assert not res.success and "9:16" in res.error and not r.calls


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_validation_on_a_real_encoded_file(tmp_path):
    path = tmp_path / "real.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=540x960:r=30:d=3.5",
                    "-f", "lavfi", "-i", "sine=f=440:sample_rate=48000:d=3.5", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    validate_reel(str(path), "facebook")
    validate_reel(str(path), "instagram")


# ── idempotency through the guard ───────────────────────────────────────

def test_an_in_doubt_attempt_is_reconciled_not_republished(fb_env, monkeypatch):
    from upload_guard import SKIP_DONE, decide
    PL.record_attempt(artifact="v1", platform="facebook", status=PL.ATTEMPT_UNKNOWN, session_uri="V7")
    Router(monkeypatch, [("get", "/V7", Resp(body={"status": {
        "publishing_phase": {"status": "complete", "publish_status": "published"}}}))])
    verdict = decide("v1", "facebook", manager=uploader.UploadManager())
    assert verdict.action == SKIP_DONE and verdict.upload_id == "V7"
    assert PL.find_by_artifact("v1")[0]["url"] == "https://www.facebook.com/reel/V7"


def test_main_keeps_an_in_doubt_attempt_open(fb_env, tmp_path, monkeypatch):
    import main
    path = tmp_path / "v2.mp4"
    path.write_bytes(b"x")
    monkeypatch.setattr(uploader.UploadManager, "upload", lambda self, *a, **k: {
        "success": False, "error": "lost", "session_uri": "V8", "in_doubt": True})
    monkeypatch.setattr("upload_metadata.resolve_upload_metadata", lambda *a, **k: {
        "title": "t", "description": "d", "hashtags": [], "source": "generated"})
    main.upload_video(path, "quiz", {}, platforms=["facebook"], artifact="v2")
    assert PL.open_attempt("v2", "facebook")["status"] == PL.ATTEMPT_UNKNOWN


# ── queue and slots ─────────────────────────────────────────────────────

@pytest.fixture
def approved(tmp_path):
    out = PL.LEDGER_DIR.parent
    path = out / "approved" / "quiz" / "q1.mp4"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x")
    return path


CFG = {"platforms": ["instagram", "facebook"], "slots": ["10:00", "19:00"], "auto_enqueue_on_approve": False}


def test_only_approved_videos_can_be_queued(approved):
    pending = approved.parents[2] / "pending" / "quiz" / "p.mp4"
    pending.parent.mkdir(parents=True)
    pending.write_bytes(b"x")
    with pytest.raises(ValueError, match="owner approval"):
        schedule.enqueue(pending)
    assert schedule.enqueue(approved) == schedule.enqueue(approved)
    assert len(schedule.load_queue()) == 1


def test_slots_fire_once_each():
    day = datetime(2026, 10, 19)
    assert schedule.due_slot(day.replace(hour=9), CFG["slots"], CFG["platforms"], []) is None
    at10 = day.replace(hour=10, minute=5)
    assert schedule.due_slot(at10, CFG["slots"], CFG["platforms"], []) == day.replace(hour=10)
    used = [{"platform": "instagram", "status": "started", "at": day.replace(hour=10, minute=1).isoformat()}]
    assert schedule.due_slot(at10, CFG["slots"], CFG["platforms"], used) is None
    assert schedule.due_slot(day.replace(hour=19, minute=1), CFG["slots"], CFG["platforms"], used)


def test_tick_publishes_the_queue_head_to_what_is_left(approved, monkeypatch):
    schedule.enqueue(approved)
    PL.record_publication(artifact="q1", video_path=str(approved), platform="instagram",
                          upload_id="M1", url="https://www.instagram.com/reel/m1/",
                          published_title="", published_description="")
    sent = []
    monkeypatch.setattr(schedule, "publish", lambda item: sent.append(item["todo"]) or {"uploaded": item["todo"]})
    assert schedule.tick(datetime(2026, 10, 19, 8), cfg=CFG)["action"] == "wait"
    assert schedule.tick(datetime(2026, 10, 19, 10, 1), cfg=CFG)["action"] == "published"
    assert sent == [["facebook"]]
    row = schedule.status_rows(CFG)[0]
    assert row["instagram"] == {"status": "published", "url": "https://www.instagram.com/reel/m1/", "id": "M1"}
    assert row["facebook"]["status"] == "queued"


def test_dry_run_sends_nothing(approved, monkeypatch):
    schedule.enqueue(approved)
    monkeypatch.setattr(common, "probe", lambda p: GOOD_PROBE)
    monkeypatch.setattr("upload_metadata.resolve_upload_metadata", lambda *a, **k: {
        "title": "", "description": "caption", "hashtags": [], "source": "generated"})
    monkeypatch.delenv("IG_USER_ID", raising=False)
    monkeypatch.delenv("FB_PAGE_ID", raising=False)
    r = Router(monkeypatch, [])
    out = schedule.tick(datetime(2026, 10, 19, 10, 1), dry=True, cfg=CFG)
    assert out["action"] == "dry_run" and not r.calls
    assert out["platforms"]["instagram"] == {"spec": "ok", "caption": "caption",
                                             "api": "not configured (env vars missing)"}
    assert not PL.read_attempts()


def test_a_dry_run_writes_nothing_and_sends_only_gets(approved, ig_env, monkeypatch):
    """STEP 70 §2, kept through STEP 72: .tokens untouched (the IG id is not cached from a dry run)."""
    (uploader.TOKEN_DIR / IG.IDS_FILE).unlink()
    schedule.enqueue(approved)
    monkeypatch.setattr(common, "probe", lambda p: GOOD_PROBE)
    monkeypatch.setattr("upload_metadata.resolve_upload_metadata", lambda *a, **k: {
        "title": "", "description": "caption", "hashtags": [], "source": "generated"})
    before = sorted((p.name, p.read_bytes(), p.stat().st_mtime_ns) for p in uploader.TOKEN_DIR.iterdir())
    r = Router(monkeypatch, [linked(), quota(), linked()])
    out = schedule.tick(datetime(2026, 10, 19, 10, 1), dry=True, cfg=CFG)
    assert out["action"] == "dry_run"
    assert out["platforms"]["instagram"]["api"]["account"] == "eu"
    assert all(m == "get" for m, _u, _k in r.calls)
    assert sorted((p.name, p.read_bytes(), p.stat().st_mtime_ns) for p in uploader.TOKEN_DIR.iterdir()) == before
    assert not PL.read_attempts()


# ── STEP 70 §3: one lock for every Meta publish ─────────────────────────

import threading  # noqa: E402


class _SlowManager:
    """A manager whose upload holds until released, counting calls to the publish endpoint."""

    def __init__(self):
        self.calls, self.inside, self.go = [], threading.Event(), threading.Event()

    def upload(self, platform, video_path, on_session=None, **kw):
        self.calls.append(platform)
        self.inside.set()
        assert self.go.wait(5)
        return {"success": True, "upload_id": "R1", "url": "https://x/r1"}


def test_the_panel_and_the_tick_never_publish_the_same_reel_twice(approved, monkeypatch):
    """Panel click holding the lock while the slot tick fires: one publish, the tick waits."""
    import admin
    schedule.enqueue(approved)
    manager = _SlowManager()
    monkeypatch.setattr(schedule, "publish", lambda item: manager.upload("tick", item["path"]))
    out = {}
    panel = threading.Thread(target=lambda: out.setdefault("panel", admin._guarded_upload(
        manager, "q1", "instagram", str(approved), title="t", description="d", hashtags=[])))
    panel.start()
    assert manager.inside.wait(5)
    # The click's open attempt already uses today's slot, so a slot tick waits; `now` ignores
    # the slots and must be stopped by the lock itself.
    tick = schedule.tick(datetime.now(), cfg=CFG)
    now = schedule.tick(datetime.now(), force=True, cfg=CFG)
    manager.go.set()
    panel.join(5)
    assert manager.calls == ["instagram"]
    assert tick["action"] == "wait"
    assert now["action"] == "wait" and "locked" in now["reason"]
    assert out["panel"]["success"]


def test_a_click_during_the_slot_publish_does_nothing(approved, monkeypatch):
    """The tick holding the lock: the panel button says so and sends nothing."""
    import admin
    schedule.enqueue(approved)
    manager = _SlowManager()
    monkeypatch.setattr(schedule, "publish", lambda item: manager.upload("tick", item["path"]))
    ticker = threading.Thread(target=lambda: schedule.tick(datetime(2026, 10, 19, 10, 1), cfg=CFG))
    ticker.start()
    assert manager.inside.wait(5)
    res = admin._guarded_upload(manager, "q1", "instagram", str(approved), title="t", description="d", hashtags=[])
    manager.go.set()
    ticker.join(5)
    assert manager.calls == ["tick"]
    assert res == {"success": False, "error": "publicando en la franja, espera", "locked": True}
    assert not [r for r in PL.read_attempts() if r.get("platform") == "instagram"]


def test_a_click_after_the_tick_published_is_refused_under_the_lock(approved):
    import admin
    PL.record_publication(artifact="q1", video_path=str(approved), platform="instagram",
                          upload_id="M1", url="https://www.instagram.com/reel/m1/",
                          published_title="", published_description="")
    manager = _SlowManager()
    res = admin._guarded_upload(manager, "q1", "instagram", str(approved), title="t")
    assert not manager.calls and res["locked"] and "ya publicado" in res["error"]


# ── STEP 72 §2: setup-check ─────────────────────────────────────────────

ALL_SCOPES = ["pages_show_list", "pages_read_engagement", "pages_manage_posts",
              "instagram_basic", "instagram_content_publish", "public_profile"]


def debug(type_="PAGE", expires=0, scopes=ALL_SCOPES, valid=True):
    return ("get", "debug_token", Resp(body={"data": {"type": type_, "expires_at": expires,
                                                      "scopes": scopes, "is_valid": valid}}))


def _setup_check(capsys, monkeypatch):
    import importlib.util
    import env_setup
    monkeypatch.setattr(env_setup, "_loaded", True)        # never read the real .env here
    spec = importlib.util.spec_from_file_location("meta_publish_cli", ROOT_DIR / "tools" / "meta_publish.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    code = cli.main(["setup-check"])
    out = capsys.readouterr().out
    assert TOKEN not in out
    return code, out


from pathlib import Path  # noqa: E402
ROOT_DIR = Path(__file__).resolve().parent.parent


def test_setup_check_is_green_when_everything_is_there(fb_env, monkeypatch, capsys):
    r = Router(monkeypatch, [debug(), linked()])
    code, out = _setup_check(capsys, monkeypatch)
    assert code == 0 and "✓ Todo listo" in out
    assert "Página: Page (1234567890)" in out and f"Instagram: @eu ({IG_ID})" in out
    assert "Token: PAGE, caduca: nunca" in out and "Permisos: los 5 necesarios" in out
    assert all(m == "get" for m, _u, _k in r.calls)


def test_setup_check_today_reports_exactly_the_missing_instagram_link(fb_env, monkeypatch, capsys):
    Router(monkeypatch, [debug(), ("get", "/1234567890", Resp(body={"name": "Page", "id": "1234567890"}))])
    code, out = _setup_check(capsys, monkeypatch)
    problems = [l for l in out.splitlines() if l.startswith("✗")]
    assert code == 1 and len(problems) == 1 and "Instagram no está vinculado a la Página" in problems[0]


def test_setup_check_names_each_problem_with_its_fix(fb_env, monkeypatch, capsys):
    monkeypatch.setenv("IG_USER_ID", "999")
    Router(monkeypatch, [debug("USER", 1_900_000_000, ["pages_show_list"]), linked()])
    code, out = _setup_check(capsys, monkeypatch)
    assert code == 1
    assert "tipo USER, no de Página" in out and "El token caduca" in out
    assert "Faltan permisos: pages_read_engagement, pages_manage_posts, instagram_basic, " \
           "instagram_content_publish" in out
    assert f"IG_USER_ID en .env (999) no es el de la Página ({IG_ID})" in out


def test_setup_check_without_credentials(monkeypatch, capsys):
    monkeypatch.delenv("FB_PAGE_ID", raising=False)
    monkeypatch.delenv("FB_PAGE_TOKEN", raising=False)
    r = Router(monkeypatch, [])
    code, out = _setup_check(capsys, monkeypatch)
    assert code == 1 and "Falta FB_PAGE_ID o FB_PAGE_TOKEN" in out and not r.calls


# ── STEP 72 §3: a setup error stops that platform for the rest of the batch ──

def test_a_setup_error_skips_the_platform_for_the_batch_and_facebook_goes_on(ig_env, tmp_path, monkeypatch):
    """The 16:35 batch, replayed: Instagram not linked, Facebook fine. Instagram is tried once,
    marked «configuración pendiente», and Facebook publishes all four."""
    import admin
    (uploader.TOKEN_DIR / IG.IDS_FILE).unlink()
    monkeypatch.setattr(common, "probe", lambda p: GOOD_PROBE)
    videos = []
    for name in ("desayuno", "postres", "bano", "dormitorio"):
        path = tmp_path / f"{name}.mp4"
        path.write_bytes(b"\0" * 1024)
        videos.append(path)
    fb = []
    for n in range(4):
        fb += [("post", "video_reels", Resp(body={"video_id": f"V{n}"})),
               ("post", f"video-upload/v26.0/V{n}", Resp(body={"success": True})),
               ("post", "video_reels", Resp(body={"success": True})),
               ("get", f"/V{n}", Resp(body={"permalink_url": f"/reel/V{n}"}))]
    r = Router(monkeypatch, [("get", "/1234567890", Resp(body={"id": "1234567890"}))] + fb)
    manager = uploader.UploadManager()
    pending, messages, done = set(), [], []
    for path in videos:                                     # the panel's bulk loop, without Streamlit
        for platform in ("instagram", "facebook"):
            if platform in pending:
                continue
            result = admin._guarded_upload(manager, path.stem, platform, str(path), title="t", description="d")
            msg = admin.note_setup_failure(pending, platform, result)
            messages += [msg] if msg else []
            done += [(path.stem, platform)] if result.get("success") else []
    assert pending == {"instagram"} and len(messages) == 1
    assert "configuración pendiente" in messages[0] and "setup-check" in messages[0] and TOKEN not in messages[0]
    assert len([c for c in r.calls if c[1].endswith("/1234567890")]) == 1   # Instagram tried once, not 4 times
    assert done == [(p.stem, "facebook") for p in videos]


@pytest.mark.parametrize("error,setup", [
    ("instagram: HTTP 400 code=100 subcode=None: The parameter video_url is required", True),
    ("facebook: HTTP 403 code=200 subcode=None: lack of pages_manage_posts permission", True),
    ("facebook: HTTP 400 code=190 subcode=463: Session has expired", True),
    ("instagram: HTTP 403 code=10 subcode=None: Application does not have permission", True),
    ("instagram: Instagram no está vinculado a la Página: vincúlalo", True),
    ("facebook: HTTP 500 code=1 subcode=None: An unknown error occurred", False),
    ("instagram: HTTP 400 code=9 subcode=2207042: max posts", False),
])
def test_what_counts_as_a_setup_error(error, setup):
    from publishers.setup import is_setup_error
    assert is_setup_error(error) is setup


def test_the_bulk_loop_uses_the_setup_stop():
    src = (ROOT_DIR / "src" / "admin.py").read_text(encoding="utf-8")
    assert "if pkey in setup_pending:" in src and "note_setup_failure(setup_pending, pkey, result)" in src


def test_a_dry_run_of_one_approved_video_for_one_platform_writes_nothing(approved, fb_env, monkeypatch, capsys):
    """STEP 72 §5: `now q1 --dry-run --platform facebook` on a video that is not queued:
    it is checked, the queue file is not created and only GETs reach Meta."""
    import importlib.util
    import env_setup
    monkeypatch.setattr(env_setup, "_loaded", True)
    monkeypatch.setattr(common, "probe", lambda p: GOOD_PROBE)
    monkeypatch.setattr("upload_metadata.resolve_upload_metadata", lambda *a, **k: {
        "title": "", "description": "caption", "hashtags": [], "source": "generated"})
    r = Router(monkeypatch, [("get", "/1234567890", Resp(body={"name": "Page"}))])
    spec = importlib.util.spec_from_file_location("meta_publish_cli2", ROOT_DIR / "tools" / "meta_publish.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["now", "q1", "--dry-run", "--platform", "facebook"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "dry_run" and list(out["platforms"]) == ["facebook"]
    assert out["platforms"]["facebook"]["spec"] == "ok" and out["platforms"]["facebook"]["api"]["account"] == "Page"
    assert all(m == "get" for m, _u, _k in r.calls) and not schedule.queue_path().exists()
    assert not PL.read_attempts()

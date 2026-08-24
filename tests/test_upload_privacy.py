#!/usr/bin/env python3
"""Privacy is decided in one place, and these are the answers.

    python3 -m pytest tests/test_upload_privacy.py

THE DEFECT THIS PINS. VideoMetadata carried a `privacy` field defaulting to
"private". main.py built one with privacy="public" — and then decomposed it
into title, description and hashtags for the manager.upload() call and threw
the object away. Every backend rebuilt its own VideoMetadata from those three
strings, so the default won and BOTH entry points published private. The
"public" in main.py had never once reached a request body; measured against
the YouTube API, every video the repo published on 2026-08-24 came back
privacyStatus=private.

It regressed silently because nothing asserted the value that ends up in the
body. These tests assert the body.

YouTube must be public: publishing to an audience of zero is not publishing.
TikTok must be SELF_ONLY: an unaudited client may only post to the poster
themselves, and changing that is a policy decision, not a code one.
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import uploader  # noqa: E402
from uploader import PLATFORM_PRIVACY, privacy_label, resolve_privacy  # noqa: E402


# ── the answers ──────────────────────────────────────────────────────

def test_youtube_publishes_public():
    assert resolve_privacy("youtube") == "public"


def test_tiktok_stays_private_because_the_client_is_unaudited():
    assert resolve_privacy("tiktok") == "private"


def test_an_unknown_platform_gets_the_quiet_answer():
    """A wrong 'private' is a support ticket; a wrong 'public' is not."""
    assert resolve_privacy("mastodon") == "private"
    assert resolve_privacy("") == "private"
    assert resolve_privacy(None) == "private"


def test_the_platform_name_is_not_case_sensitive():
    assert resolve_privacy("YouTube") == resolve_privacy("youtube")


# ── what actually reaches the API ────────────────────────────────────

def test_the_youtube_request_body_carries_public(monkeypatch, tmp_path):
    """Not the resolver — the dict handed to the YouTube API."""
    sent = {}

    class Resp:
        status_code = 200
        headers = {"Location": "https://upload.example/session"}

        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return {"id": "vid123"}

    def fake_post(url, **kw):
        sent.update(kw.get("json") or {})
        return Resp()

    monkeypatch.setattr(uploader.requests, "post", fake_post)
    monkeypatch.setattr(uploader.requests, "put", lambda *a, **k: Resp())

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 16)

    yt = uploader.YouTubeUploader()
    yt._token_data = {"access_token": "tok"}
    yt.upload_video(str(video), "T", "D", ["Alpha"])

    assert sent["status"]["privacyStatus"] == "public", (
        "the body YouTube receives is what decides who can watch it")


def test_the_tiktok_request_body_carries_self_only(monkeypatch, tmp_path):
    """Not the resolver — the post_info handed to the TikTok API."""
    sent = {}

    def fake_api_post(self, path, token, json=None, **kw):
        if json and "post_info" in json:
            sent.update(json["post_info"])
            return {"data": {"publish_id": "p1"}}
        return {"data": {"upload_url": "https://upload.example/tt",
                         "publish_id": "p1"}}

    class Resp:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(uploader.TikTokUploader, "_api_post", fake_api_post)
    monkeypatch.setattr(uploader.requests, "put", lambda *a, **k: Resp())

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 16)

    tt = uploader.TikTokUploader()
    tt._token_data = {"access_token": "tok"}
    tt.upload_video(str(video), "T", "D", ["Alpha"])

    assert sent.get("privacy_level") == "SELF_ONLY", (
        "an unaudited TikTok client may only post to the poster themselves")


# ── one place ────────────────────────────────────────────────────────

def _privacy_literals(path: Path):
    """Every string literal that names a privacy level, outside the table."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    words = {"public", "private", "unlisted", "SELF_ONLY", "PUBLIC_TO_EVERYONE"}
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and n.value in words]


def test_main_no_longer_holds_its_own_privacy_literal():
    """main.py's privacy="public" was the second (dead) resolution site."""
    assert _privacy_literals(ROOT / "main.py") == [], (
        "main.py names a privacy level again — it must come from "
        "uploader.resolve_privacy")


def test_the_dashboard_decides_nothing_about_privacy():
    assert _privacy_literals(ROOT / "src" / "admin.py") == [], (
        "admin.py names a privacy level — the dashboard reads the resolver, "
        "it does not decide")


def test_video_metadata_no_longer_carries_a_privacy_field():
    """The trap: a container that looks like it carries the setting."""
    assert not hasattr(uploader.VideoMetadata("t", "d"), "privacy")


def test_every_configured_platform_has_an_answer():
    manager = uploader.UploadManager()
    for name in manager.uploaders:
        assert name in PLATFORM_PRIVACY, (
            f"{name} can be uploaded to and has no entry in PLATFORM_PRIVACY")


# ── what the operator reads ──────────────────────────────────────────

def test_the_label_uses_the_platform_s_own_vocabulary():
    """TikTok's API does not say "private", it says SELF_ONLY."""
    assert "SELF_ONLY" in privacy_label("tiktok")
    assert privacy_label("youtube") == "public"


def test_the_label_never_comes_back_empty():
    for name in list(PLATFORM_PRIVACY) + ["mastodon", ""]:
        assert privacy_label(name).strip(), f"{name!r} rendered as a blank"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

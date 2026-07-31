#!/usr/bin/env python3
"""Tests for the uploader auth/status CLI. No network, no API spend.

    python3 -m pytest tests/test_uploader_cli.py

Only the CLI surface is covered — token inspection and exit codes. The upload
path is untouched by this work and untested here.
"""

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import uploader as U  # noqa: E402


@pytest.fixture
def token_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(U, "TOKEN_DIR", tmp_path)
    return tmp_path


def write(token_dir, platform, data):
    (token_dir / f"{platform}_token.json").write_text(json.dumps(data))


# ── token inspection ─────────────────────────────────────────────────

def test_missing_token_is_absent_not_valid(token_dir):
    info = U._describe_token("youtube")

    assert info["present"] is False
    assert not info.get("valid")


def test_live_token_is_valid_and_reports_refresh(token_dir):
    write(token_dir, "youtube", {"access_token": "a", "refresh_token": "r",
                                 "expires_at": time.time() + 3600})
    info = U._describe_token("youtube")

    assert info["present"] and info["valid"]
    assert info["has_refresh_token"] is True


def test_expired_token_is_present_but_invalid(token_dir):
    write(token_dir, "youtube", {"access_token": "a", "refresh_token": "r",
                                 "expires_at": time.time() - 10})
    info = U._describe_token("youtube")

    assert info["present"] is True
    assert info["valid"] is False


def test_token_inside_the_60s_slack_is_already_invalid(token_dir):
    """Matches the uploaders' own _token_expired, which treats the last
    minute as expired so an upload cannot start against a dying token."""
    write(token_dir, "youtube", {"access_token": "a", "expires_at": time.time() + 30})

    assert U._describe_token("youtube")["valid"] is False


def test_error_payload_is_never_reported_as_valid(token_dir):
    """The regression that motivated the check.

    TikTok answers a bad token request with HTTP 200 and an error BODY, so
    raise_for_status() does not fire and _exchange_code persists the error
    verbatim — stamped with expires_at = now + 24h. It looks exactly like a
    fresh token. Reporting it as valid would make `status` confidently wrong
    about the only thing it exists to answer.
    """
    write(token_dir, "tiktok", {
        "error": "invalid_request",
        "error_description": "Only `application/x-www-form-urlencoded` is accepted.",
        "expires_at": time.time() + 86400,
    })
    info = U._describe_token("tiktok")

    assert info["present"] is True
    assert info["has_access_token"] is False
    assert info["valid"] is False, "an error payload must never read as valid"
    assert info["error"] == "invalid_request"


def test_token_without_expires_at_is_not_assumed_live(token_dir):
    write(token_dir, "youtube", {"access_token": "a"})

    assert U._describe_token("youtube")["valid"] is False


# ── the write guard ──────────────────────────────────────────────────

def test_payload_without_access_token_is_refused_not_written(token_dir):
    """The write is refused, not merely reported afterwards.

    TikTok returns HTTP 200 with an error body, so raise_for_status() never
    fires and _exchange_code hands the error JSON to the store. Before this
    guard it was persisted with expires_at = now + 24h, looked like a fresh
    token, and authenticate() reused it — the failure perpetuated itself.
    """
    with pytest.raises(U.TokenPersistError, match="access_token"):
        U._save_token("tiktok", {"error": "invalid_request",
                                 "expires_at": time.time() + 86400})

    assert not (token_dir / "tiktok_token.json").exists(), "the file was written"


def test_the_refusal_names_the_provider_error(token_dir):
    with pytest.raises(U.TokenPersistError, match="invalid_request"):
        U._save_token("tiktok", {"error": "invalid_request"})


@pytest.mark.parametrize("payload", [
    {}, {"access_token": ""}, {"refresh_token": "r"}, {"expires_at": 1}, None,
])
def test_every_shape_without_a_usable_access_token_is_refused(token_dir, payload):
    with pytest.raises(U.TokenPersistError):
        U._save_token("youtube", payload)

    assert not (token_dir / "youtube_token.json").exists()


def test_a_real_token_is_still_written(token_dir):
    U._save_token("youtube", {"access_token": "a", "refresh_token": "r",
                              "expires_at": time.time() + 3600})

    assert json.loads((token_dir / "youtube_token.json").read_text())["access_token"] == "a"


def test_the_guard_covers_every_platform(token_dir):
    """_save_token is the single choke point both platforms funnel through."""
    for platform in ("youtube", "tiktok", "instagram"):
        with pytest.raises(U.TokenPersistError):
            U._save_token(platform, {"error": "nope"})


def test_a_refused_write_leaves_the_previous_token_intact(token_dir):
    good = {"access_token": "keep-me", "refresh_token": "r",
            "expires_at": time.time() + 3600}
    U._save_token("youtube", good)

    with pytest.raises(U.TokenPersistError):
        U._save_token("youtube", {"error": "invalid_request"})

    assert json.loads((token_dir / "youtube_token.json").read_text()) == good


def test_cmd_auth_reports_a_refused_write_as_auth_failure(token_dir, monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "k")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "s")

    def fake_auth(self):
        U._save_token("tiktok", {"error": "invalid_request"})
        return True
    monkeypatch.setattr(U.TikTokUploader, "authenticate", fake_auth)

    assert U.cmd_auth("tiktok") == 1


# ── formatting ───────────────────────────────────────────────────────

def test_expiry_marks_expired_tokens(token_dir):
    write(token_dir, "youtube", {"access_token": "a", "expires_at": time.time() - 7200})

    assert "EXPIRED" in U._fmt_expiry(U._describe_token("youtube"))


@pytest.mark.parametrize("seconds,expected", [
    (90, "1m"), (3700, "1h"), (200000, "2d"),
])
def test_duration_formatting(seconds, expected):
    assert expected in U._fmt_duration(seconds)


def test_duration_never_negative():
    assert U._fmt_duration(-500) == "0m"


# ── CLI wiring ───────────────────────────────────────────────────────

def test_status_is_local_only_and_always_succeeds(token_dir, monkeypatch, capsys):
    """status must not make network calls. Any attempt fails the test."""
    def boom(*a, **k):
        raise AssertionError("status made a network call")
    for verb in ("get", "post", "put"):
        monkeypatch.setattr(U.requests, verb, boom)

    write(token_dir, "youtube", {"access_token": "a", "refresh_token": "r",
                                 "expires_at": time.time() + 3600})

    assert U.cmd_status() == 0
    out = capsys.readouterr().out
    assert "youtube" in out and "tiktok" in out and "instagram" in out


def test_auth_rejects_an_unconfigured_platform(token_dir, monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "")

    assert U.cmd_auth("tiktok") == 2


def test_auth_exits_nonzero_when_no_refresh_token_comes_back(token_dir, monkeypatch):
    """The explicit requirement. A usable access_token is NOT success if
    nothing can renew it — every future run would need a human."""
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")

    def fake_auth(self):
        write(token_dir, "youtube", {"access_token": "a",
                                     "expires_at": time.time() + 3600})
        return True
    monkeypatch.setattr(U.YouTubeUploader, "authenticate", fake_auth)

    assert U.cmd_auth("youtube") == 4


def test_auth_succeeds_only_with_a_refresh_token(token_dir, monkeypatch):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")

    def fake_auth(self):
        write(token_dir, "youtube", {"access_token": "a", "refresh_token": "r",
                                     "expires_at": time.time() + 3600})
        return True
    monkeypatch.setattr(U.YouTubeUploader, "authenticate", fake_auth)

    assert U.cmd_auth("youtube") == 0


def test_auth_fails_when_the_provider_returned_an_error_payload(token_dir, monkeypatch):
    """authenticate() returning True is not proof of a token."""
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "k")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "s")

    def fake_auth(self):
        write(token_dir, "tiktok", {"error": "invalid_request",
                                    "expires_at": time.time() + 86400})
        return True          # exactly what _exchange_code does today
    monkeypatch.setattr(U.TikTokUploader, "authenticate", fake_auth)

    assert U.cmd_auth("tiktok") == 1


def test_auth_reports_missing_stdin_rather_than_tracebacking(token_dir, monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "k")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "s")
    monkeypatch.setattr(U.TikTokUploader, "authenticate",
                        lambda self: (_ for _ in ()).throw(EOFError()))

    assert U.cmd_auth("tiktok") == 3


def test_auth_only_offers_platforms_with_an_oauth_code_flow():
    """Instagram authenticates from a static env token and has no code to
    exchange, so `auth --platform instagram` would have nothing to do."""
    assert set(U.OAUTH_PLATFORMS) == {"youtube", "tiktok"}

    with pytest.raises(SystemExit):
        U.main(["auth", "--platform", "instagram"])


def test_cli_requires_a_subcommand():
    with pytest.raises(SystemExit):
        U.main([])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

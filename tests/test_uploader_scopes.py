#!/usr/bin/env python3
"""authenticate() must not reuse a token that lacks a required scope.

    python3 -m pytest tests/test_uploader_scopes.py

This is why widening YOUTUBE_SCOPES silently did nothing. Both reuse paths
tested only whether the stored token was UNEXPIRED:

  reuse    an unexpired narrow token returns True, and the first call to a
           newly-needed endpoint 403s with ACCESS_TOKEN_SCOPE_INSUFFICIENT,
           far from the cause
  refresh  worse, because it looks like the fix. A refresh returns a new
           access_token with THE SAME SCOPES the original grant had — Google
           never widens scope on refresh, only a fresh consent does

So editing the constant produced a token that was valid, unexpired,
refreshable, and still missing the scope, with no error until an API call
failed.
"""

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import uploader as U  # noqa: E402

UPLOAD = "https://www.googleapis.com/auth/youtube.upload"
READONLY = "https://www.googleapis.com/auth/youtube.readonly"
ANALYTICS = "https://www.googleapis.com/auth/yt-analytics.readonly"


def _uploader(scope: str, monkeypatch, expires_in=3600, refresh="r"):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(U, "_load_token", lambda p: {
        "access_token": "tok", "refresh_token": refresh,
        "expires_at": time.time() + expires_in, "scope": scope})
    return U.YouTubeUploader()


# ── the detection ────────────────────────────────────────────────────

def test_a_narrow_token_reports_the_missing_scopes(monkeypatch):
    yt = _uploader(UPLOAD, monkeypatch)

    missing = yt._missing_scopes()

    assert READONLY in missing
    assert ANALYTICS in missing
    assert UPLOAD not in missing


def test_a_complete_token_reports_nothing_missing(monkeypatch):
    yt = _uploader(f"{UPLOAD} {READONLY} {ANALYTICS}", monkeypatch)

    assert yt._missing_scopes() == []


def test_scope_order_does_not_matter(monkeypatch):
    yt = _uploader(f"{ANALYTICS} {UPLOAD} {READONLY}", monkeypatch)

    assert yt._missing_scopes() == []


def test_a_token_with_no_scope_field_satisfies_nothing(monkeypatch):
    """It predates this check. Assuming it is adequate is the failure mode
    being fixed, so it is treated as satisfying nothing."""
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(U, "_load_token", lambda p: {
        "access_token": "tok", "expires_at": time.time() + 3600})

    assert U.YouTubeUploader()._missing_scopes() == list(U.YOUTUBE_SCOPES)


# ── today's failure, reproduced ──────────────────────────────────────

def test_a_valid_narrow_token_is_NOT_reused(monkeypatch):
    """The exact situation today: token present, unexpired, refreshable, and
    missing two scopes. It must not short-circuit to True."""
    yt = _uploader(UPLOAD, monkeypatch)
    monkeypatch.setattr(yt, "_refresh_token",
                        lambda: pytest.fail("refresh cannot widen scope"))
    reconsented = []
    monkeypatch.setattr(U, "run_loopback_auth",
                        lambda build, timeout=None: reconsented.append(1) or {"error": "stub"})

    assert yt.authenticate() is False        # stubbed consent, so False
    assert reconsented, "did not reach re-consent; the narrow token was reused"


def test_refresh_is_skipped_when_a_scope_is_missing(monkeypatch):
    """A refresh returns the SAME scopes the grant had. Taking that path on a
    missing scope burns a request and returns a token that still 403s."""
    yt = _uploader(UPLOAD, monkeypatch, expires_in=-10)   # expired too
    monkeypatch.setattr(yt, "_refresh_token",
                        lambda: pytest.fail("refresh must be skipped"))
    monkeypatch.setattr(U, "run_loopback_auth",
                        lambda build, timeout=None: {"error": "stub"})

    yt.authenticate()


def test_a_complete_token_is_still_reused(monkeypatch):
    """The check must not force re-consent on every run."""
    yt = _uploader(f"{UPLOAD} {READONLY} {ANALYTICS}", monkeypatch)
    monkeypatch.setattr(U, "run_loopback_auth",
                        lambda build, timeout=None: pytest.fail(
                            "re-consented despite a complete, valid token"))

    assert yt.authenticate() is True


def test_a_complete_but_expired_token_still_refreshes(monkeypatch):
    """Expiry and scope are independent: an expired token with the right
    scopes should refresh, not re-consent."""
    yt = _uploader(f"{UPLOAD} {READONLY} {ANALYTICS}", monkeypatch, expires_in=-10)
    monkeypatch.setattr(yt, "_refresh_token", lambda: True)
    monkeypatch.setattr(U, "run_loopback_auth",
                        lambda build, timeout=None: pytest.fail(
                            "re-consented when a refresh would have done"))

    assert yt.authenticate() is True


# ── visibility ───────────────────────────────────────────────────────

def test_status_surfaces_a_narrow_token_without_an_api_call(monkeypatch, tmp_path):
    """A token can be present, valid and refreshable while missing a scope.
    `status` must say so locally rather than waiting for a 403."""
    import json
    monkeypatch.setattr(U, "TOKEN_DIR", tmp_path)
    (tmp_path / "youtube_token.json").write_text(json.dumps({
        "access_token": "tok", "refresh_token": "r",
        "expires_at": time.time() + 3600, "scope": UPLOAD}))

    info = U._describe_token("youtube")

    assert info["valid"] is True
    assert READONLY in info["missing_scopes"]


def test_the_scope_list_the_code_requires_is_the_one_it_asks_for():
    """The authorize URL is built from YOUTUBE_SCOPES, and _missing_scopes
    checks against the same constant, so they cannot drift."""
    assert UPLOAD in U.YOUTUBE_SCOPES
    assert READONLY in U.YOUTUBE_SCOPES
    assert ANALYTICS in U.YOUTUBE_SCOPES


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

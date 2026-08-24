#!/usr/bin/env python3
"""
Video Uploader Module for English AI Video Generator

Handles uploading generated videos to TikTok, YouTube Shorts, and Instagram Reels.
Each platform uses its own API with OAuth2 authentication where required.
Tokens are persisted in .tokens/ for reuse across sessions.

Environment variables:
    TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET
    YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET
    INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID
"""

import argparse
import hmac
import json
import logging
import os
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, quote, urlparse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOKEN_DIR = Path(__file__).resolve().parent.parent / ".tokens"

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = f"{TIKTOK_API_BASE}/oauth/token/"

YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
INSTAGRAM_GRAPH_URL = "https://graph.facebook.com/v19.0"

# Retry / polling settings
MAX_POLL_ATTEMPTS = 30
POLL_INTERVAL_SECONDS = 10
UPLOAD_TIMEOUT_SECONDS = 300


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

#: What each platform publishes AT. ONE table, consulted by every entry
#: point — main.py --batch, the dashboard, and the request bodies themselves.
#:
#: Before this existed, privacy had no reachable resolution site at all.
#: VideoMetadata carried a `privacy` field defaulting to "private", main.py
#: built one with privacy="public" — and then decomposed it into title,
#: description and hashtags for the manager.upload() call and threw the object
#: away. Every backend rebuilt its own VideoMetadata from those three strings,
#: so the default won every time and BOTH entry points published private. The
#: "public" at main.py:362 had never once reached the API.
#:
#: Per platform, because the correct answer differs per platform:
#:
#:   youtube    public. Publishing to an audience of zero is not publishing.
#:   tiktok     private -> SELF_ONLY, REQUIRED while the client is unaudited.
#:              An unaudited client may only post to the poster themselves.
#:              Do not change this without the audit.
#:   instagram  public — descriptive, not a control. The Graph API's
#:              media_publish takes no privacy parameter; a Reel's visibility
#:              follows the connected professional account. Recorded here so
#:              the operator sees the truth on the page rather than a blank.
PLATFORM_PRIVACY = {
    "youtube": "public",
    "tiktok": "private",
    "instagram": "public",
}

#: An unknown platform gets the quiet answer. A wrong "private" is a support
#: ticket; a wrong "public" is unpublishable.
UNKNOWN_PLATFORM_PRIVACY = "private"

#: What to show the operator, in each platform's own vocabulary. TikTok does
#: not say "private" in its API, it says SELF_ONLY, and the page should not
#: make the operator translate.
_PRIVACY_LABELS = {
    ("tiktok", "private"): "SELF_ONLY (only you)",
    ("instagram", "public"): "public (follows the account)",
}


def resolve_privacy(platform: str) -> str:
    """The privacy `platform` publishes at. The only place this is decided."""
    return PLATFORM_PRIVACY.get((platform or "").lower(),
                                UNKNOWN_PLATFORM_PRIVACY)


def privacy_label(platform: str) -> str:
    """`resolve_privacy`, phrased for the operator reading the Upload page."""
    key = (platform or "").lower()
    value = resolve_privacy(key)
    return _PRIVACY_LABELS.get((key, value), value)


@dataclass
class VideoMetadata:
    """Container for video metadata shared across platforms.

    No `privacy` field. It used to have one, and it was the trap: a container
    that LOOKS like it carries the setting, whose value was discarded by every
    caller before the request was built. Privacy is resolved from the platform
    at the point the body is composed — see PLATFORM_PRIVACY.
    """
    title: str
    description: str
    hashtags: list[str] = field(default_factory=list)

    @property
    def hashtag_string(self) -> str:
        return " ".join(f"#{tag.lstrip('#')}" for tag in self.hashtags)

    @property
    def full_description(self) -> str:
        """The description, as given. THE UPLOADER DOES NOT COMPOSE.

        LIVE DEFECT this resolves: every video published so far carried its
        hashtag block TWICE. metadata_generator.adapt_for_platform appended
        the tags, and this appended them again, so YouTube received:

            <description>

            #CompletaLaFrase #AprendeIngles ...

            #CompletaLaFrase #AprendeIngles ...

        OWNERSHIP: composition belongs to metadata_generator.compose_description,
        upstream, and the uploader is a transport. That direction rather than
        the reverse because composition is PLATFORM-SPECIFIC — YouTube puts
        hashtags in the description while Instagram and TikTok build a single
        caption from title + body + tags — and this dataclass has no platform
        knowledge. It cannot tell an already-composed description from a raw
        one, which is exactly how the duplicate arose.

        An earlier pass fixed this by checking whether the first tag was
        already present and skipping. That worked but left BOTH sides
        composing, so the invariant depended on a substring test rather than
        on one side simply not doing it.

        `hashtags` stays on the dataclass: YouTube takes a SEPARATE `tags`
        array in the API body, which is not the same thing as hashtags in the
        description text.
        """
        return self.description or ""


@dataclass
class UploadResult:
    """Standardised result returned by every uploader."""
    platform: str
    success: bool
    upload_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[dict] = None
    #: YouTube resumable session URI. Carried on FAILURE results too -- it is
    #: the only thing that can later answer "did that upload actually land?",
    #: and every failure path below used to discard it.
    session_uri: Optional[str] = None


# ---------------------------------------------------------------------------
# Token persistence helpers
# ---------------------------------------------------------------------------

def _ensure_token_dir() -> Path:
    """Create the .tokens directory if it does not exist."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    gitignore = TOKEN_DIR / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n")
    return TOKEN_DIR


class TokenPersistError(RuntimeError):
    """Raised when a payload that is not a token is offered to the store."""


def _save_token(platform: str, data: dict) -> None:
    # A payload without access_token is not a token, and writing it is worse
    # than dropping it.
    #
    # TikTok answers a malformed token request with HTTP 200 and an error
    # BODY, so raise_for_status() never fires, _exchange_code returns True,
    # and the error JSON was persisted as the token — stamped with
    # expires_at = now + 24h by _persist_token. The file then looked like a
    # fresh valid token, so authenticate() REUSED it rather than
    # re-authorizing, and the failure perpetuated itself for a day.
    #
    # This is the single choke point: both platforms' _persist_token funnel
    # through here, so the guard covers every platform at once. It raises
    # rather than returning False because a silent no-op write is how the
    # original bug stayed invisible.
    if not isinstance(data, dict) or not data.get("access_token"):
        detail = ""
        if isinstance(data, dict) and data.get("error"):
            detail = f" (provider error: {data['error']})"
        raise TokenPersistError(
            f"refusing to store a {platform} token with no access_token{detail}"
        )

    token_path = _ensure_token_dir() / f"{platform}_token.json"
    token_path.write_text(json.dumps(data, indent=2))
    logger.debug("Saved %s token to %s", platform, token_path)


def _load_token(platform: str) -> Optional[dict]:
    token_path = TOKEN_DIR / f"{platform}_token.json"
    if token_path.exists():
        try:
            return json.loads(token_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read %s token: %s", platform, exc)
    return None


# ---------------------------------------------------------------------------
# Loopback OAuth listener
# ---------------------------------------------------------------------------
#
# Replaces redirect_uri=urn:ietf:wg:oauth:2.0:oob, which Google shut down: the
# authorize URL no longer shows a code, so the exchange failed with 400 every
# time and the old input() prompt sat waiting for something that could never
# arrive.
#
# The OAuth client is a Desktop app, and Desktop clients accept
# http://127.0.0.1:<any port> without the URI being registered in the console.
# No console change is needed.

#: Hard ceiling on waiting for the browser callback. A hang in an unattended
#: run is the failure class already removed from the render path, so this is
#: never allowed to block forever.
LOOPBACK_TIMEOUT_S = 180


class _LoopbackHandler(BaseHTTPRequestHandler):
    """One-shot handler: capture ?code=, verify ?state=, tell the user to close
    the tab."""

    # Set by the server factory below.
    expected_state: str = ""
    result: dict = {}
    done: Optional[threading.Event] = None

    def do_GET(self) -> None:                      # noqa: N802 - stdlib name
        query = parse_qs(urlparse(self.path).query)
        code = (query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        error = (query.get("error") or [""])[0]

        if error:
            outcome = {"error": error}
            title, body = "Authorization denied", f"Google returned: {error}"
        elif not hmac.compare_digest(state, self.expected_state):
            # CSRF guard. A callback whose state does not match ours was not
            # started by us, so the code in it is not ours to exchange.
            outcome = {"error": "state_mismatch"}
            title, body = "Rejected", "state parameter did not match."
        elif not code:
            outcome = {"error": "no_code"}
            title, body = "No code", "The callback carried no authorization code."
        else:
            outcome = {"code": code}
            title, body = "Authorized", "You can close this tab and return to the terminal."

        self.send_response(200 if "code" in outcome else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            f"<!doctype html><meta charset=utf-8><title>{title}</title>"
            f"<body style='font:16px system-ui;padding:3rem;max-width:34rem'>"
            f"<h2>{title}</h2><p>{body}</p></body>".encode("utf-8")
        )

        # Only the FIRST callback counts. A browser prefetch or a reload must
        # not overwrite a code we already captured.
        if not type(self).result:
            type(self).result = outcome
        if type(self).done is not None:
            type(self).done.set()

    def log_message(self, fmt: str, *args) -> None:
        # BaseHTTPRequestHandler logs to stderr by default, which would splice
        # request lines into the middle of the CLI's own output.
        logger.debug("loopback: " + fmt, *args)


def run_loopback_auth(build_auth_url, timeout: Optional[int] = None) -> dict:
    """Serve one OAuth callback on 127.0.0.1 and return {"code"} or {"error"}.

    `build_auth_url(redirect_uri, state)` returns the provider's authorize URL.
    The port is chosen by the OS (bind to 0, then read it back) — hardcoding a
    port guarantees an eventual collision with something else on the machine.

    Always returns; never raises for a protocol-level failure, and never
    blocks past `timeout`.

    The timeout resolves HERE, not as a default argument. A default is bound
    at def time, so `LOOPBACK_TIMEOUT_S` could never be overridden — including
    by a test trying to prove the timeout works, which then waited the full
    180 s and looked exactly like the hang it was written to rule out.
    """
    timeout = LOOPBACK_TIMEOUT_S if timeout is None else timeout
    state = secrets.token_urlsafe(32)

    # Port 0 => the OS picks a free one; server_address reports which.
    server = HTTPServer(("127.0.0.1", 0), _LoopbackHandler)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/"

    done = threading.Event()
    _LoopbackHandler.expected_state = state
    _LoopbackHandler.result = {}
    _LoopbackHandler.done = done

    url = build_auth_url(redirect_uri, state)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        print(f"listening on {redirect_uri} (timeout {timeout}s)\n")
        print("If your browser does not open, paste this URL into it:\n")
        print(f"  {url}\n")
        try:
            webbrowser.open(url)
        except Exception:                          # noqa: BLE001
            # Headless, no DISPLAY, no handler — the printed URL above is the
            # fallback, so this must never be fatal.
            logger.debug("webbrowser.open failed", exc_info=True)

        if not done.wait(timeout):
            return {"error": "timeout", "redirect_uri": redirect_uri}
        return dict(_LoopbackHandler.result, redirect_uri=redirect_uri)
    finally:
        server.shutdown()
        server.server_close()
        _LoopbackHandler.done = None


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseUploader(ABC):
    """Interface that every platform uploader must implement."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the required env vars / credentials are present."""

    @abstractmethod
    def authenticate(self) -> bool:
        """Run the auth flow and persist tokens.  Returns True on success."""

    @abstractmethod
    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        hashtags: Optional[list[str]] = None,
    ) -> UploadResult:
        """Upload a video file and return an UploadResult."""

    @abstractmethod
    def get_upload_status(self, upload_id: str) -> UploadResult:
        """Poll the platform for the status of a previous upload."""


# ---------------------------------------------------------------------------
# TikTok
# ---------------------------------------------------------------------------

class TikTokUploader(BaseUploader):
    """Upload videos via the TikTok Content Posting API v2.

    Flow:
        1. Authenticate (OAuth2 authorization-code flow).
        2. Initialise an upload session (POST /post/publish/inbox/video/init/).
        3. Upload the video binary via the returned upload URL.
        4. Publish the video (POST /post/publish/video/init/).
    """

    PLATFORM = "tiktok"

    def __init__(self) -> None:
        self.client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
        self.client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")
        self._token_data: Optional[dict] = _load_token(self.PLATFORM)
        #: Why the last authenticate() failed. Mirrors YouTubeUploader.
        self.last_auth_error: Optional[str] = None

    # -- public interface ----------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.client_key and self.client_secret)

    def authenticate(self) -> bool:
        if not self.is_configured():
            logger.error("TikTok client key/secret not set in environment.")
            return False

        # Try existing token first
        if self._token_data and not self._token_expired():
            logger.info("TikTok: reusing existing token.")
            return True

        if self._token_data and self._token_data.get("refresh_token"):
            if self._refresh_token():
                return True

        # NO PROMPT. This used to print an authorize URL and then block on
        # input() waiting for a pasted code.
        #
        # The dashboard reaches this path. A prompt there does not ask anyone
        # anything — it hangs the worker on a stdin that will never be
        # answered, and the request simply never returns. That is the last
        # instance of the hang class already removed from the render path and
        # from the YouTube auth path.
        #
        # It could not have succeeded in any case: _exchange_code posts with
        # json= while TikTok requires application/x-www-form-urlencoded, so
        # the exchange has never once worked (docs/recorded-debt.md item 9).
        # Even a correctly pasted code would fail.
        #
        # Interactive TikTok authorization belongs behind an explicit operator
        # command, not inside a code path a web request can enter.
        logger.error(
            "TikTok: no valid token and no non-interactive way to obtain one. "
            "Run `make auth-tiktok` from a terminal. "
            "NOTE: TikTok auth cannot currently succeed — the token exchange "
            "sends JSON where the API requires form encoding "
            "(docs/recorded-debt.md item 9)."
        )
        self.last_auth_error = "no_token_and_no_interactive_path"
        return False

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        hashtags: Optional[list[str]] = None,
    ) -> UploadResult:
        if not self._token_data:
            return UploadResult(self.PLATFORM, False, error="Not authenticated.")

        access_token = self._token_data["access_token"]
        file_size = os.path.getsize(video_path)

        # Step 1 – init upload
        init_resp = self._api_post(
            "/post/publish/inbox/video/init/",
            access_token,
            json={
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": file_size,
                    "chunk_size": file_size,
                    "total_chunk_count": 1,
                }
            },
        )
        if not init_resp or "data" not in init_resp:
            return UploadResult(self.PLATFORM, False, error="Init upload failed.",
                                raw_response=init_resp)

        upload_url = init_resp["data"]["upload_url"]
        publish_id = init_resp["data"].get("publish_id", "")

        # Step 2 – binary upload
        headers = {
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
        }
        try:
            with open(video_path, "rb") as fh:
                resp = requests.put(upload_url, data=fh, headers=headers,
                                    timeout=UPLOAD_TIMEOUT_SECONDS)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("TikTok binary upload failed: %s", exc)
            return UploadResult(self.PLATFORM, False, error=str(exc))

        # Step 3 – publish
        meta = VideoMetadata(title, description, hashtags or [])
        publish_resp = self._api_post(
            "/post/publish/video/init/",
            access_token,
            json={
                "post_info": {
                    "title": meta.title[:150],
                    "description": meta.full_description[:2200],
                    "privacy_level": "SELF_ONLY"
                                     if resolve_privacy(self.PLATFORM) == "private"
                                     else "PUBLIC_TO_EVERYONE",
                    "disable_comment": False,
                    "disable_duet": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": file_size,
                },
            },
        )
        if not publish_resp:
            return UploadResult(self.PLATFORM, False, error="Publish request failed.")

        upload_id = publish_resp.get("data", {}).get("publish_id", publish_id)
        logger.info("TikTok upload started – publish_id=%s", upload_id)
        return UploadResult(self.PLATFORM, True, upload_id=upload_id,
                            raw_response=publish_resp)

    def get_upload_status(self, upload_id: str) -> UploadResult:
        if not self._token_data:
            return UploadResult(self.PLATFORM, False, error="Not authenticated.")

        resp = self._api_post(
            "/post/publish/status/fetch/",
            self._token_data["access_token"],
            json={"publish_id": upload_id},
        )
        if not resp:
            return UploadResult(self.PLATFORM, False, upload_id=upload_id,
                                error="Status fetch failed.")

        status = resp.get("data", {}).get("status", "UNKNOWN")
        success = status == "PUBLISH_COMPLETE"
        return UploadResult(self.PLATFORM, success, upload_id=upload_id,
                            raw_response=resp,
                            error=None if success else f"Status: {status}")

    # -- private helpers -----------------------------------------------------

    def _token_expired(self) -> bool:
        if not self._token_data:
            return True
        expires_at = self._token_data.get("expires_at", 0)
        return time.time() >= expires_at - 60

    def _exchange_code(self, code: str) -> bool:
        try:
            resp = requests.post(TIKTOK_TOKEN_URL, json={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": "https://localhost/callback",
            }, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.error("TikTok token exchange failed: %s", exc)
            return False

        self._persist_token(data)
        return True

    def _refresh_token(self) -> bool:
        try:
            resp = requests.post(TIKTOK_TOKEN_URL, json={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self._token_data["refresh_token"],
            }, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.warning("TikTok token refresh failed: %s", exc)
            return False

        self._persist_token(data)
        return True

    def _persist_token(self, data: dict) -> None:
        data["expires_at"] = time.time() + data.get("expires_in", 86400)
        self._token_data = data
        _save_token(self.PLATFORM, data)

    def _api_post(self, path: str, token: str, **kwargs) -> Optional[dict]:
        url = f"{TIKTOK_API_BASE}{path}"
        headers = {"Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=UTF-8"}
        try:
            resp = requests.post(url, headers=headers, timeout=60, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("TikTok API %s failed: %s", path, exc)
            return None


# ---------------------------------------------------------------------------
# YouTube Shorts
# ---------------------------------------------------------------------------

class YouTubeUploader(BaseUploader):
    """Upload videos as YouTube Shorts via the Data API v3.

    Uses resumable uploads so large files survive flaky connections.
    Automatically adds #Shorts to the title to surface the video as a Short.
    """

    PLATFORM = "youtube"
    CATEGORY_EDUCATION = "27"
    CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB

    def __init__(self) -> None:
        self.client_id = os.getenv("YOUTUBE_CLIENT_ID", "")
        self.client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "")
        self._token_data: Optional[dict] = _load_token(self.PLATFORM)
        #: Why the last authenticate() failed, for callers that need to tell
        #: "the browser never came back" (no code) from "Google rejected the
        #: code we did get" (exchange failure). Those are different exit codes.
        self.last_auth_error: Optional[str] = None

    # -- public interface ----------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def authenticate(self) -> bool:
        if not self.is_configured():
            logger.error("YouTube client ID/secret not set in environment.")
            return False

        # SCOPE CHECK BEFORE ANY REUSE.
        #
        # This is why widening YOUTUBE_SCOPES did nothing. Both shortcuts below
        # test only whether the stored token is UNEXPIRED, never whether it
        # still covers what the code now asks for:
        #
        #   reuse    an unexpired narrow token returns True, and the first
        #            call to a newly-needed endpoint 403s with
        #            ACCESS_TOKEN_SCOPE_INSUFFICIENT — far from the cause
        #   refresh  worse, because it LOOKS like it should fix it. A refresh
        #            exchanges a refresh_token for a new access_token carrying
        #            THE SAME SCOPES THE ORIGINAL GRANT HAD. Google will never
        #            widen scope on refresh; only a fresh consent does that.
        #
        # So editing the constant produced a token that was valid, unexpired,
        # refreshable, and still missing the scope — with no error anywhere
        # until an API call failed. A missing scope now forces full re-consent
        # regardless of expiry.
        missing = self._missing_scopes()
        if missing:
            logger.warning(
                "YouTube: stored token is missing %d required scope(s): %s. "
                "A refresh cannot add them — forcing re-consent.",
                len(missing), ", ".join(s.rsplit("/", 1)[-1] for s in missing))
        else:
            if self._token_data and not self._token_expired():
                logger.info("YouTube: reusing existing token.")
                return True

            if self._token_data and self._token_data.get("refresh_token"):
                if self._refresh_token():
                    return True

        # OAuth2 authorization-code flow over a loopback listener.
        #
        # This used to build the URL with redirect_uri=urn:ietf:wg:oauth:2.0:oob
        # and then block on input() waiting for a pasted code. Google shut that
        # flow down: the authorize page no longer displays a code, so the
        # prompt waited for something that could never arrive and the exchange
        # failed with 400 every time.
        #
        # There is deliberately NO input() fallback. Any remaining input() in
        # an automatable path is a latent hang.
        def build_url(redirect_uri: str, state: str) -> str:
            return (
                f"{YOUTUBE_AUTH_URL}?client_id={self.client_id}"
                f"&redirect_uri={quote(redirect_uri, safe='')}"
                f"&response_type=code"
                f"&scope={quote(' '.join(YOUTUBE_SCOPES), safe='')}"
                f"&state={quote(state, safe='')}"
                # access_type=offline + prompt=consent is what makes Google
                # return a refresh_token; without both, re-authorizing an
                # already-approved app yields an access_token only.
                f"&access_type=offline&prompt=consent"
            )

        self.last_auth_error = None
        outcome = run_loopback_auth(build_url)

        if "code" not in outcome:
            reason = outcome.get("error", "unknown")
            if reason == "timeout":
                logger.error(
                    "YouTube: no callback within %ss. Authorization was not "
                    "completed in the browser.", LOOPBACK_TIMEOUT_S)
            elif reason == "state_mismatch":
                logger.error(
                    "YouTube: callback state did not match — rejected. The "
                    "response did not come from the request we started.")
            else:
                logger.error("YouTube: authorization failed (%s).", reason)
            self.last_auth_error = reason
            return False

        # The redirect_uri in the exchange must byte-match the one used in the
        # authorize request, so it is threaded through rather than re-derived.
        if self._exchange_code(outcome["code"], outcome["redirect_uri"]):
            return True
        self.last_auth_error = "exchange_failed"
        return False

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        hashtags: Optional[list[str]] = None,
        on_session=None,
    ) -> UploadResult:
        """Upload one video.

        `on_session(uri, file_size)` is invoked as soon as the resumable
        session exists and BEFORE any video bytes are sent, so the caller can
        persist the URI. If this process dies mid-upload, that URI is the only
        way the next run can tell "already live" from "never uploaded".
        """
        if not self._token_data:
            return UploadResult(self.PLATFORM, False, error="Not authenticated.")

        meta = VideoMetadata(title, description, hashtags or [])

        # Ensure #Shorts appears so YouTube surfaces it as a Short
        shorts_tag = "#Shorts"
        yt_title = meta.title if shorts_tag in meta.title else f"{meta.title} {shorts_tag}"

        privacy_status = resolve_privacy(self.PLATFORM)

        body = {
            "snippet": {
                "title": yt_title[:100],
                "description": meta.full_description[:5000],
                "tags": [t.lstrip("#") for t in meta.hashtags][:500],
                "categoryId": self.CATEGORY_EDUCATION,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        access_token = self._token_data["access_token"]
        file_size = os.path.getsize(video_path)

        # Step 1 – initiate resumable upload
        try:
            init_resp = requests.post(
                YOUTUBE_UPLOAD_URL,
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": "video/mp4",
                    "X-Upload-Content-Length": str(os.path.getsize(video_path)),
                },
                json=body,
                timeout=60,
            )
            init_resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("YouTube resumable init failed: %s", exc)
            return UploadResult(self.PLATFORM, False, error=str(exc))

        upload_url = init_resp.headers.get("Location")
        if not upload_url:
            return UploadResult(self.PLATFORM, False,
                                error="No upload URL in init response.")

        # The session now exists. Hand it to the caller BEFORE a single byte
        # of video is sent, so an attempt row can carry it even if this
        # process dies mid-chunk. Without this the URI lived only in a local
        # and every error path threw it away.
        if on_session is not None:
            try:
                on_session(upload_url, file_size)
            except Exception:                            # noqa: BLE001
                logger.exception("on_session callback failed; continuing")

        # Step 2 – upload file in chunks
        try:
            with open(video_path, "rb") as fh:
                offset = 0
                while offset < file_size:
                    chunk = fh.read(self.CHUNK_SIZE)
                    end = offset + len(chunk) - 1
                    headers = {
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{end}/{file_size}",
                    }
                    resp = requests.put(upload_url, data=chunk, headers=headers,
                                        timeout=UPLOAD_TIMEOUT_SECONDS)
                    if resp.status_code in (200, 201):
                        # Upload complete
                        result_data = resp.json()
                        video_id = result_data.get("id", "")
                        url = f"https://youtube.com/shorts/{video_id}" if video_id else None
                        logger.info("YouTube upload complete – id=%s", video_id)
                        return UploadResult(self.PLATFORM, True,
                                            upload_id=video_id, url=url,
                                            raw_response=result_data,
                                            session_uri=upload_url)
                    if resp.status_code == 308:
                        # Partially received, continue
                        range_header = resp.headers.get("Range", "")
                        if range_header:
                            offset = int(range_header.split("-")[1]) + 1
                        else:
                            offset += len(chunk)
                    else:
                        resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("YouTube chunk upload failed: %s", exc)
            return UploadResult(self.PLATFORM, False, error=str(exc),
                                session_uri=upload_url)

        return UploadResult(self.PLATFORM, False, error="Upload ended unexpectedly.",
                            session_uri=upload_url)

    def query_session(self, session_uri: str, file_size: int) -> dict:
        """Ask YouTube what happened to an interrupted resumable session.

        This is the only thing that can answer "is that video already live?"
        without guessing. Per Google's resumable protocol, a zero-length PUT
        with `Content-Range: bytes */<size>` returns:

          200/201  the upload ALREADY COMPLETED. The body is the video
                   resource, so this also hands back the video id — Google
                   replays the original completion response.
          308      Resume Incomplete. Bytes are still missing, so the video
                   resource was never created and nothing is live.
          404      the session URI EXPIRED. This says NOTHING about whether
                   the upload completed before it expired.
          4xx/5xx  the upload failed permanently.

        Returns {"state", "upload_id", "detail"} where state is one of
        published / incomplete / failed / unknown. `unknown` means a human has
        to look; it is never treated as "safe to retry".
        """
        if not self._token_data:
            return {"state": "unknown", "upload_id": None,
                    "detail": "not authenticated"}

        try:
            resp = requests.put(
                session_uri,
                headers={
                    "Authorization": f"Bearer {self._token_data['access_token']}",
                    "Content-Length": "0",
                    "Content-Range": f"bytes */{file_size}",
                },
                timeout=60,
            )
        except requests.RequestException as exc:
            # A network failure tells us nothing about the upload's fate.
            return {"state": "unknown", "upload_id": None, "detail": str(exc)}

        if resp.status_code in (200, 201):
            try:
                data = resp.json()
            except ValueError:
                data = {}
            return {"state": "published", "upload_id": data.get("id"),
                    "detail": f"session replayed {resp.status_code}",
                    "raw": data}

        if resp.status_code == 308:
            return {"state": "incomplete", "upload_id": None,
                    "detail": f"Range={resp.headers.get('Range', '')!r}"}

        if resp.status_code == 404:
            # Expired. It may have completed before expiring and we cannot
            # tell from here. Deliberately NOT "failed".
            return {"state": "unknown", "upload_id": None,
                    "detail": "session URI expired (404)"}

        if 400 <= resp.status_code < 600:
            return {"state": "failed", "upload_id": None,
                    "detail": f"HTTP {resp.status_code}"}

        return {"state": "unknown", "upload_id": None,
                "detail": f"unexpected HTTP {resp.status_code}"}

    def get_upload_status(self, upload_id: str) -> UploadResult:
        if not self._token_data:
            return UploadResult(self.PLATFORM, False, error="Not authenticated.")

        try:
            resp = requests.get(
                YOUTUBE_API_URL,
                params={"part": "status,processingDetails", "id": upload_id},
                headers={"Authorization": f"Bearer {self._token_data['access_token']}"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            return UploadResult(self.PLATFORM, False, upload_id=upload_id,
                                error=str(exc))

        items = data.get("items", [])
        if not items:
            return UploadResult(self.PLATFORM, False, upload_id=upload_id,
                                error="Video not found.")

        status_obj = items[0].get("status", {})
        upload_status = status_obj.get("uploadStatus", "unknown")
        success = upload_status == "processed"
        url = f"https://youtube.com/shorts/{upload_id}"
        return UploadResult(self.PLATFORM, success, upload_id=upload_id,
                            url=url, raw_response=data,
                            error=None if success else f"Status: {upload_status}")

    # -- private helpers -----------------------------------------------------

    def _token_expired(self) -> bool:
        if not self._token_data:
            return True
        return time.time() >= self._token_data.get("expires_at", 0) - 60

    def _missing_scopes(self) -> list:
        """Scopes YOUTUBE_SCOPES requires that the stored token does not have.

        Google returns the granted scopes as a space-separated `scope` string
        on the token response. A token with no `scope` field at all is treated
        as satisfying nothing: it predates this check, and assuming it is
        adequate is exactly the failure mode being fixed.
        """
        if not self._token_data:
            return list(YOUTUBE_SCOPES)
        granted = set((self._token_data.get("scope") or "").split())
        return [s for s in YOUTUBE_SCOPES if s not in granted]

    def _exchange_code(self, code: str, redirect_uri: str) -> bool:
        # redirect_uri is passed in, not hardcoded: Google requires it to
        # byte-match the one used in the authorize request, and that one now
        # carries an OS-assigned port that differs on every run.
        try:
            resp = requests.post(YOUTUBE_TOKEN_URL, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.error("YouTube token exchange failed: %s", exc)
            return False

        self._persist_token(data)
        return True

    def _refresh_token(self) -> bool:
        try:
            resp = requests.post(YOUTUBE_TOKEN_URL, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self._token_data["refresh_token"],
            }, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            # Google does not always return refresh_token on refresh
            data.setdefault("refresh_token", self._token_data["refresh_token"])
        except requests.RequestException as exc:
            logger.warning("YouTube token refresh failed: %s", exc)
            return False

        self._persist_token(data)
        return True

    def _persist_token(self, data: dict) -> None:
        data["expires_at"] = time.time() + data.get("expires_in", 3600)
        self._token_data = data
        _save_token(self.PLATFORM, data)


# ---------------------------------------------------------------------------
# Instagram Reels
# ---------------------------------------------------------------------------

class InstagramUploader(BaseUploader):
    """Upload Reels via the Instagram Graph API (Facebook platform).

    Flow:
        1. Create a media container with the video URL.
        2. Poll until the container is ready.
        3. Publish the container.

    Because the Graph API requires a *public* video URL (not a local file),
    callers must either:
        - Host the file themselves and pass the URL, or
        - Use a temporary hosting solution (e.g., S3 presigned URL).
    The upload_video method accepts a ``video_url`` keyword argument for this.
    When only a local path is given, it will raise an error with guidance.
    """

    PLATFORM = "instagram"

    def __init__(self) -> None:
        self.access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        self.account_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")

    # -- public interface ----------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.access_token and self.account_id)

    def authenticate(self) -> bool:
        if not self.is_configured():
            logger.error(
                "Instagram access token or business account ID not set. "
                "Set INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID."
            )
            return False
        # Long-lived tokens are passed directly; no interactive flow needed.
        logger.info("Instagram: credentials present, ready to upload.")
        return True

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        hashtags: Optional[list[str]] = None,
        *,
        video_url: Optional[str] = None,
    ) -> UploadResult:
        if not self.is_configured():
            return UploadResult(self.PLATFORM, False, error="Not configured.")

        if not video_url:
            return UploadResult(
                self.PLATFORM, False,
                error=(
                    "Instagram requires a publicly accessible video URL. "
                    "Pass video_url='https://...' pointing to the hosted file."
                ),
            )

        meta = VideoMetadata(title, description, hashtags or [])
        caption = f"{meta.title}\n\n{meta.full_description}"

        # Step 1 – create media container
        container_id = self._create_container(video_url, caption)
        if not container_id:
            return UploadResult(self.PLATFORM, False,
                                error="Failed to create media container.")

        # Step 2 – wait for container to finish processing
        if not self._wait_for_container(container_id):
            return UploadResult(self.PLATFORM, False, upload_id=container_id,
                                error="Container processing timed out.")

        # Step 3 – publish
        publish_id = self._publish_container(container_id)
        if not publish_id:
            return UploadResult(self.PLATFORM, False, upload_id=container_id,
                                error="Publish failed.")

        logger.info("Instagram Reel published – id=%s", publish_id)
        url = f"https://www.instagram.com/reel/{publish_id}/"
        return UploadResult(self.PLATFORM, True, upload_id=publish_id, url=url)

    def get_upload_status(self, upload_id: str) -> UploadResult:
        try:
            resp = requests.get(
                f"{INSTAGRAM_GRAPH_URL}/{upload_id}",
                params={
                    "fields": "status_code,status",
                    "access_token": self.access_token,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            return UploadResult(self.PLATFORM, False, upload_id=upload_id,
                                error=str(exc))

        status_code = data.get("status_code", "UNKNOWN")
        success = status_code == "PUBLISHED"
        return UploadResult(self.PLATFORM, success, upload_id=upload_id,
                            raw_response=data,
                            error=None if success else f"Status: {status_code}")

    # -- private helpers -----------------------------------------------------

    def _create_container(self, video_url: str, caption: str) -> Optional[str]:
        try:
            resp = requests.post(
                f"{INSTAGRAM_GRAPH_URL}/{self.account_id}/media",
                data={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": caption[:2200],
                    "share_to_feed": "true",
                    "access_token": self.access_token,
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json().get("id")
        except requests.RequestException as exc:
            logger.error("Instagram create container failed: %s", exc)
            return None

    def _wait_for_container(self, container_id: str) -> bool:
        for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
            try:
                resp = requests.get(
                    f"{INSTAGRAM_GRAPH_URL}/{container_id}",
                    params={
                        "fields": "status_code",
                        "access_token": self.access_token,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                status = resp.json().get("status_code", "")
            except requests.RequestException as exc:
                logger.warning("Instagram poll attempt %d failed: %s", attempt, exc)
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            if status == "FINISHED":
                return True
            if status == "ERROR":
                logger.error("Instagram container %s entered ERROR state.", container_id)
                return False

            logger.debug("Instagram container %s status: %s (attempt %d/%d)",
                         container_id, status, attempt, MAX_POLL_ATTEMPTS)
            time.sleep(POLL_INTERVAL_SECONDS)

        return False

    def _publish_container(self, container_id: str) -> Optional[str]:
        try:
            resp = requests.post(
                f"{INSTAGRAM_GRAPH_URL}/{self.account_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": self.access_token,
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json().get("id")
        except requests.RequestException as exc:
            logger.error("Instagram publish failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Upload Manager
# ---------------------------------------------------------------------------

class UploadManager:
    """Orchestrates uploads across all configured platforms.

    Usage::

        manager = get_upload_manager()
        results = manager.upload_all(
            "output/video.mp4",
            title="Learn English: Greetings",
            description="Common greeting phrases in English.",
            hashtags=["LearnEnglish", "Shorts", "ESL"],
        )
        for r in results:
            print(f"{r.platform}: {'OK' if r.success else r.error}")
    """

    def __init__(self) -> None:
        self.uploaders: dict[str, BaseUploader] = {
            "tiktok": TikTokUploader(),
            "youtube": YouTubeUploader(),
            "instagram": InstagramUploader(),
        }

    @property
    def configured_platforms(self) -> list[str]:
        """Return the list of platforms that have credentials configured."""
        return [name for name, up in self.uploaders.items() if up.is_configured()]

    def authenticate_all(self) -> dict[str, bool]:
        """Authenticate every configured platform. Returns {platform: success}."""
        results: dict[str, bool] = {}
        for name, uploader in self.uploaders.items():
            if not uploader.is_configured():
                logger.info("Skipping %s – not configured.", name)
                results[name] = False
                continue
            try:
                results[name] = uploader.authenticate()
            except Exception as exc:
                logger.error("Auth failed for %s: %s", name, exc)
                results[name] = False
        return results

    def upload_all(
        self,
        video_path: str,
        title: str,
        description: str,
        hashtags: Optional[list[str]] = None,
        platforms: Optional[list[str]] = None,
        **kwargs,
    ) -> list[UploadResult]:
        """Upload to every configured (or specified) platform.

        Args:
            video_path: Local path to the video file.
            title: Video title.
            description: Video description.
            hashtags: Optional list of hashtags (without leading #).
            platforms: Restrict to these platforms. None means all configured.
            **kwargs: Extra keyword arguments forwarded to each uploader
                      (e.g., ``video_url`` for Instagram).

        Returns:
            A list of UploadResult, one per attempted platform.
        """
        if not os.path.isfile(video_path):
            logger.error("Video file not found: %s", video_path)
            return [UploadResult("all", False, error=f"File not found: {video_path}")]

        target_platforms = platforms or self.configured_platforms
        results: list[UploadResult] = []

        # Only the YouTube backend implements a resumable session. Forwarding
        # this to TikTok/Instagram through **kwargs would TypeError.
        on_session = kwargs.pop("on_session", None)

        for name in target_platforms:
            uploader = self.uploaders.get(name)
            if not uploader:
                logger.warning("Unknown platform: %s", name)
                results.append(UploadResult(name, False, error="Unknown platform."))
                continue

            if not uploader.is_configured():
                logger.info("Skipping %s – not configured.", name)
                results.append(UploadResult(name, False, error="Not configured."))
                continue

            try:
                if not uploader.authenticate():
                    results.append(UploadResult(name, False,
                                                error="Authentication failed."))
                    continue

                extra = dict(kwargs)
                if on_session is not None and name == "youtube":
                    extra["on_session"] = on_session
                result = uploader.upload_video(
                    video_path, title, description, hashtags, **extra,
                )
                results.append(result)
                logger.info("Upload to %s: %s", name,
                            "success" if result.success else result.error)
            except Exception as exc:
                logger.error("Upload to %s raised exception: %s", name, exc,
                             exc_info=True)
                results.append(UploadResult(name, False, error=str(exc)))

        return results

    def upload(
        self,
        platform: str,
        video_path: str,
        title: str = "",
        description: str = "",
        hashtags: Optional[list[str]] = None,
        **kwargs,
    ) -> dict:
        """Upload to a single platform. Returns dict with 'success' and 'error' keys."""
        results = self.upload_all(video_path, title, description, hashtags,
                                  platforms=[platform], **kwargs)
        if results:
            r = results[0]
            return {"success": r.success, "error": r.error,
                    "upload_id": r.upload_id, "url": r.url,
                    "session_uri": r.session_uri}
        return {"success": False, "error": "No result returned"}

    def get_status(self, platform: str, upload_id: str) -> UploadResult:
        """Check the status of a single upload."""
        uploader = self.uploaders.get(platform)
        if not uploader:
            return UploadResult(platform, False, error="Unknown platform.")
        try:
            return uploader.get_upload_status(upload_id)
        except Exception as exc:
            return UploadResult(platform, False, upload_id=upload_id,
                                error=str(exc))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_upload_manager() -> UploadManager:
    """Create and return an UploadManager instance.

    Configured platforms are logged at INFO level so operators can verify
    which integrations are active without inspecting env vars directly.
    """
    manager = UploadManager()
    configured = manager.configured_platforms
    if configured:
        logger.info("Upload platforms configured: %s", ", ".join(configured))
    else:
        logger.warning(
            "No upload platforms configured. Set the appropriate environment "
            "variables (TIKTOK_CLIENT_KEY, YOUTUBE_CLIENT_ID, "
            "INSTAGRAM_ACCESS_TOKEN, etc.) to enable uploads."
        )
    return manager


# ---------------------------------------------------------------------------
# CLI — auth and status only
# ---------------------------------------------------------------------------
#
# Until this existed the ONLY way to trigger OAuth was to run the full
# pipeline with upload enabled, which meant generating and paying for a video
# in order to authenticate. These two commands touch neither generation nor
# upload, and spend nothing.
#
# The upload path, the redirect URIs and the loopback listener are Step 5 and
# are deliberately untouched here.

#: Platforms with an interactive OAuth authorization-code flow. Instagram is
#: excluded on purpose: it authenticates from a long-lived token in
#: INSTAGRAM_ACCESS_TOKEN and has no code to exchange, so `auth` would have
#: nothing to do. `status` still reports it.
OAUTH_PLATFORMS = ("youtube", "tiktok")


def _describe_token(platform: str) -> dict:
    """Local-only view of a stored token. Makes no network calls."""
    path = TOKEN_DIR / f"{platform}_token.json"
    data = _load_token(platform)
    if data is None:
        return {"platform": platform, "path": str(path), "present": False}

    expires_at = data.get("expires_at")
    remaining = (expires_at - time.time()) if isinstance(expires_at, (int, float)) else None

    # A file is not a token unless it carries an access_token.
    #
    # This is not defensive padding. TikTok's token endpoint answers a bad
    # request with HTTP 200 and an error BODY, so raise_for_status() does not
    # fire and _exchange_code persists the error payload verbatim — then
    # stamps it with expires_at = now + 24h. The result is a file that looks
    # like a fresh valid token and contains
    # {"error": "invalid_request", "error_description": ...}.
    #
    # Reporting that as "valid" would make this command confidently wrong
    # about the one thing it exists to answer. The underlying persist bug is
    # in the upload path and is left for Step 5; this stops the CLI repeating
    # it. See docs/recorded-debt.md.
    error = data.get("error")
    usable = bool(data.get("access_token"))

    return {
        "platform": platform,
        "path": str(path),
        "present": True,
        "expires_at": expires_at,
        "expires_in_s": remaining,
        # A minute of slack, matching the uploaders' own _token_expired.
        "valid": bool(usable and remaining is not None and remaining > 60),
        "has_access_token": usable,
        "error": error,
        "has_refresh_token": bool(data.get("refresh_token")),
        "scope": data.get("scope"),
        # Surfaced locally so a narrow token is visible in `status` without
        # waiting for an API call to 403. A token can be present, valid and
        # refreshable while still lacking a scope the code now needs.
        "missing_scopes": ([s for s in YOUTUBE_SCOPES
                            if s not in set((data.get("scope") or "").split())]
                           if platform == "youtube" else []),
    }


def _fmt_expiry(info: dict) -> str:
    if not info.get("present"):
        return "-"
    exp = info.get("expires_at")
    if not isinstance(exp, (int, float)):
        return "unknown (no expires_at in token)"
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp))
    secs = info["expires_in_s"]
    if secs is None:
        return stamp
    if secs <= 0:
        return f"{stamp}  (EXPIRED {_fmt_duration(-secs)} ago)"
    return f"{stamp}  (in {_fmt_duration(secs)})"


def _fmt_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _cli_logging() -> None:
    """Send INFO to stdout with no prefix.

    The uploaders emit the authorization URL through logger.info. Without a
    handler that line goes nowhere, which is why the URL was invisible when
    auth was only reachable from the pipeline. A bare format keeps the URL
    copy-pasteable.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


def cmd_auth(platform: str) -> int:
    """Run ONLY the OAuth flow for one platform. No upload, no generation."""
    _cli_logging()

    uploader = UploadManager().uploaders[platform]

    if not uploader.is_configured():
        env = {"youtube": "YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET",
               "tiktok": "TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET"}[platform]
        print(f"\n{platform}: NOT CONFIGURED — set {env} in .env", file=sys.stderr)
        return 2

    before = _describe_token(platform)
    if before["present"] and before["valid"]:
        print(f"{platform}: a valid token already exists "
              f"(expires {_fmt_expiry(before)}).")
        print("Delete it to force a fresh authorization:")
        print(f"  rm {before['path']}\n")

    print(f"--- {platform} OAuth ---")
    if platform == "youtube":
        # Loopback: the browser delivers the code back to a local listener,
        # so there is nothing to paste and nothing reads stdin.
        print("A browser will open. Approve there and this will finish on "
              "its own.\n")
    else:
        print("Open the URL below, approve, then paste the code back here.\n")

    try:
        ok = uploader.authenticate()
    except TokenPersistError as exc:
        # The store refused the payload. This is the intended outcome when a
        # provider returns an error body with HTTP 200 — nothing was written.
        sys.stdout.flush()
        print(f"\n{platform}: AUTH FAILED — {exc}", file=sys.stderr)
        print("  nothing was written; the previous token (if any) is intact.",
              file=sys.stderr)
        return 1
    except EOFError:
        print("\nNo authorization code on stdin. Run this in a terminal, or "
              "pipe the code:\n"
              f"  echo '<code>' | python -m uploader auth --platform {platform}",
              file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130

    after = _describe_token(platform)

    print()
    if not ok:
        # Exit 3 is "no authorization code was ever received" — the browser
        # never came back, the user denied, or the state did not match. Exit 1
        # is reserved for the case where a code DID arrive and the provider
        # then rejected the exchange. Different problems, different fixes.
        reason = getattr(uploader, "last_auth_error", None)
        if reason in ("timeout", "no_code", "state_mismatch", "access_denied"):
            hint = {
                "timeout": f"no browser callback within {LOOPBACK_TIMEOUT_S}s — "
                           "authorization was not completed",
                "no_code": "the callback carried no authorization code",
                "state_mismatch": "callback state did not match; rejected as CSRF",
                "access_denied": "authorization was denied in the browser",
            }[reason]
            print(f"{platform}: NO CODE RECEIVED — {hint}.", file=sys.stderr)
            return 3
        print(f"{platform}: AUTH FAILED — no token stored.", file=sys.stderr)
        return 1

    # authenticate() returning True is not proof a token was obtained — see
    # _describe_token. Check the artifact, not the return value.
    if not after.get("has_access_token"):
        sys.stdout.flush()
        print(f"\n{platform}: AUTH FAILED — the stored file has no access_token.",
              file=sys.stderr)
        if after.get("error"):
            print(f"  provider error: {after['error']}", file=sys.stderr)
        print(f"  the response was written to {after['path']} anyway; delete it.",
              file=sys.stderr)
        return 1

    print(f"{platform}: OK")
    print(f"  token stored at : {after['path']}")
    print(f"  expires         : {_fmt_expiry(after)}")
    print(f"  refresh_token   : {'yes' if after['has_refresh_token'] else 'NO'}")
    if after.get("scope"):
        print(f"  scope           : {after['scope']}")
    sys.stdout.flush()

    if not after["has_refresh_token"]:
        # Without a refresh token every future run needs a human, which
        # defeats an automated publish path — so this is a failure, not a
        # warning, even though a usable access_token was returned.
        print("\nFAIL: no refresh_token in the response.", file=sys.stderr)
        if platform == "youtube":
            print("Google only returns one with access_type=offline AND "
                  "prompt=consent, and only on the FIRST consent for an app. "
                  "Revoke access at https://myaccount.google.com/permissions "
                  "and retry.", file=sys.stderr)
        else:
            print("Re-authorize and confirm the app requests offline access.",
                  file=sys.stderr)
        return 4

    return 0


def cmd_status() -> int:
    """Local report on every platform's stored token. No network calls."""
    manager = UploadManager()

    print(f"token directory: {TOKEN_DIR}\n")
    print(f"{'platform':12}{'configured':>12}{'token':>9}{'valid':>8}"
          f"{'refresh':>9}  expires")
    print("-" * 78)

    for name in ("youtube", "tiktok", "instagram"):
        up = manager.uploaders[name]
        info = _describe_token(name)
        configured = "yes" if up.is_configured() else "no"

        if name == "instagram":
            # No OAuth code flow: the token IS the env var, so there is no
            # file to inspect and no expiry we can see locally.
            print(f"{name:12}{configured:>12}{'env':>9}{'-':>8}{'-':>9}  "
                  f"static INSTAGRAM_ACCESS_TOKEN (not inspectable locally)")
            continue

        detail = _fmt_expiry(info)
        if info.get("present") and not info.get("has_access_token"):
            detail = (f"CORRUPT — no access_token"
                      + (f", stored error: {info['error']}" if info.get("error") else ""))
        if info.get("missing_scopes"):
            short = ", ".join(x.rsplit("/", 1)[-1] for x in info["missing_scopes"])
            detail = f"MISSING SCOPES: {short} — re-run auth"
        print(f"{name:12}{configured:>12}"
              f"{('yes' if info['present'] else 'no'):>9}"
              f"{('yes' if info.get('valid') else 'no'):>8}"
              f"{('yes' if info.get('has_refresh_token') else 'no'):>9}  "
              f"{detail}")

    print("\nvalidity is checked against the stored expires_at only — no "
          "network calls, no API spend.")
    print(f"to authenticate:  python -m uploader auth --platform "
          f"{'|'.join(OAUTH_PLATFORMS)}")
    return 0


def _load_env() -> None:
    """Load .env before any uploader is constructed.

    uploader.py is the only env-reading module in src/ that does NOT call
    load_dotenv at import — it has always been imported by pipeline.py or
    admin.py, which load it first. Run standalone that assumption breaks, and
    every platform reports "not configured" while .env holds valid
    credentials.

    Done HERE rather than at module import so the upload path keeps exactly
    the import-time behaviour it has today. The uploaders read os.getenv in
    __init__, so this must run before UploadManager() is constructed.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main(argv=None) -> int:
    _load_env()
    parser = argparse.ArgumentParser(
        prog="python -m uploader",
        description="OAuth and token inspection. Never uploads, never "
                    "generates, never spends.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_auth = sub.add_parser("auth", help="run the OAuth flow for one platform")
    p_auth.add_argument("--platform", required=True, choices=OAUTH_PLATFORMS)

    sub.add_parser("status", help="show stored token state for every platform")

    args = parser.parse_args(argv)
    if args.command == "auth":
        return cmd_auth(args.platform)
    return cmd_status()


if __name__ == "__main__":
    sys.exit(main())

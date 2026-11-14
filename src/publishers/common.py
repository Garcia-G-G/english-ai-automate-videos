"""What the Meta Reels publishers share: the HTTP call, its errors, the spec check.

Both publishers are uploader.BaseUploader backends, so UploadManager, the
attempt log and upload_guard treat them exactly like YouTube. On top of that
they expose `publish(video_path, caption, hashtags)`, the platform-neutral
call the scheduler and the CLI use.

TOKENS NEVER LEAVE THIS PROCESS IN TEXT. requests puts the full URL, query
string included, into its exception messages, and debug_token takes the token
in the query. Every error string built here goes through `redact`.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import proc
from pathlib import Path
from typing import Dict, List, Optional

import requests

from uploader import BaseUploader, UploadResult

logger = logging.getLogger(__name__)

#: Graph API version, from developers.facebook.com/docs/graph-api/changelog (checked 2026-10-19).
GRAPH_VERSION = "v26.0"
RUPLOAD = "https://rupload.facebook.com"
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"

#: Graph error codes that mean "slow down", not "broken". 9/2207042 is IG's publishing cap.
RATE_CODES = {4, 17, 9, 32, 613}
RATE_SUBCODES = {2207042}
TOKEN_CODES = {190}


class MetaError(RuntimeError):
    def __init__(self, message: str, code: Optional[int] = None,
                 subcode: Optional[int] = None, status: Optional[int] = None):
        super().__init__(message)
        self.code, self.subcode, self.status = code, subcode, status


class RateLimited(MetaError):
    """The platform refused because of a quota. Nothing was published."""


class TokenExpired(MetaError):
    """The access token is expired or invalid; a human has to issue a new one."""


class ReelSpecError(ValueError):
    """The file does not meet the platform's Reels spec. Raised before any request."""


def redact(text: str, *secrets: str) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def call(method: str, url: str, token: str, **kwargs) -> Dict:
    """One Graph/rupload request. Returns the JSON body or raises a MetaError subclass."""
    try:
        resp = getattr(requests, method)(url, timeout=kwargs.pop("timeout", 60), **kwargs)
    except requests.RequestException as exc:
        raise MetaError(redact(f"{method.upper()} failed: {exc}", token)) from None
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:300]}
    err = body.get("error") if isinstance(body, dict) else None
    if resp.status_code < 400 and not err:
        return body
    err = err if isinstance(err, dict) else {"message": str(body.get("debug_info") or body)[:300]}
    code, sub = err.get("code"), err.get("error_subcode")
    msg = redact(f"HTTP {resp.status_code} code={code} subcode={sub}: "
                 f"{err.get('error_user_msg') or err.get('message', '')}", token)
    cls = (TokenExpired if code in TOKEN_CODES
           else RateLimited if code in RATE_CODES or sub in RATE_SUBCODES
           else MetaError)
    raise cls(msg, code, sub, resp.status_code)


def debug_token(token: str) -> Dict:
    """/debug_token on the token itself: type, expires_at (0 = never), scopes, is_valid."""
    return call("get", f"{GRAPH}/debug_token", token,
                params={"input_token": token, "access_token": token}).get("data") or {}


def expiry_text(info: Dict) -> str:
    """debug_token's expiry, said plainly: a Page token from a long-lived user token never expires."""
    at = info.get("expires_at")
    if at in (0, None):
        return "never"
    from datetime import datetime
    return datetime.fromtimestamp(int(at)).strftime("%Y-%m-%d %H:%M")


def rupload(url: str, token: str, video_path: str) -> Dict:
    """Send the whole file in one POST, the way both resumable endpoints accept it."""
    size = os.path.getsize(video_path)
    with open(video_path, "rb") as fh:
        return call("post", url, token, data=fh, timeout=max(300, size / 50_000),
                    headers={"Authorization": f"OAuth {token}", "offset": "0",
                             "file_size": str(size)})


# ── the Reels spec ────────────────────────────────────────────────────────
#
# From the IG Media reference and the FB Reels publishing guide (2026-10-19).
# Aspect is checked as 9:16 for both even though IG accepts far wider: the
# brief is vertical Reels, and a landscape file here is a pipeline mistake.

SPECS = {
    "instagram": {"min_s": 3, "max_s": 15 * 60, "fps": (23, 60), "min_w": 540,
                  "max_bytes": 300 * 1024 * 1024, "max_hz": 48000},
    "facebook": {"min_s": 3, "max_s": 90, "fps": (24, 60), "min_w": 540,
                 "max_bytes": None, "max_hz": 48000},
}
VIDEO_CODECS = {"h264", "hevc"}


def _rate(text: str) -> float:
    num, _, den = (text or "0/1").partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(video_path: str) -> Dict:
    done = proc.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                           "-of", "json", str(video_path)],
                          capture_output=True, text=True, check=False, timeout=proc.FFPROBE)
    if done.returncode:
        raise ReelSpecError(f"ffprobe could not read {video_path}: {done.stderr.strip()[:200]}")
    return json.loads(done.stdout)


def validate_reel(video_path: str, platform: str, info: Optional[Dict] = None) -> Dict:
    """Every way `video_path` breaks `platform`'s Reels spec, raised together. Returns the probe."""
    spec = SPECS[platform]
    path = Path(video_path)
    if not path.is_file():
        raise ReelSpecError(f"{platform}: file not found: {video_path}")
    if path.suffix.lower() not in (".mp4", ".mov"):
        raise ReelSpecError(f"{platform}: {path.name} must be .mp4 or .mov")
    info = info if info is not None else probe(video_path)
    streams = info.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise ReelSpecError(f"{platform}: {path.name} has no video stream")

    problems: List[str] = []
    w, h = int(video.get("width") or 0), int(video.get("height") or 0)
    duration = float((info.get("format") or {}).get("duration") or video.get("duration") or 0)
    fps = _rate(video.get("avg_frame_rate")) or _rate(video.get("r_frame_rate"))
    size = path.stat().st_size

    if video.get("codec_name") not in VIDEO_CODECS:
        problems.append(f"video codec {video.get('codec_name')} (needs H.264 or HEVC)")
    if not h or abs(w / h - 9 / 16) > 0.01:
        problems.append(f"aspect {w}x{h} is not 9:16")
    if w < spec["min_w"]:
        problems.append(f"width {w}px is under {spec['min_w']}px")
    if not spec["min_s"] <= duration <= spec["max_s"]:
        problems.append(f"duration {duration:.1f}s is outside {spec['min_s']}-{spec['max_s']}s")
    lo, hi = spec["fps"]
    if not lo <= round(fps, 2) <= hi:
        problems.append(f"frame rate {fps:.2f} fps is outside {lo}-{hi}")
    if spec["max_bytes"] and size > spec["max_bytes"]:
        problems.append(f"file is {size / 1e6:.0f} MB, over {spec['max_bytes'] / 1e6:.0f} MB")
    if audio is not None:
        if audio.get("codec_name") != "aac":
            problems.append(f"audio codec {audio.get('codec_name')} (needs AAC)")
        hz = int(audio.get("sample_rate") or 0)
        if hz > spec["max_hz"]:
            problems.append(f"audio sample rate {hz} Hz is over {spec['max_hz']} Hz")
    if problems:
        raise ReelSpecError(f"{platform}: {path.name} does not meet the Reels spec: "
                            + "; ".join(problems))
    return info


def compose_caption(caption: str, hashtags: Optional[List[str]], limit: int = 2200) -> str:
    """The caption plus any hashtag it does not already carry."""
    caption = (caption or "").strip()
    missing = [f"#{t.lstrip('#')}" for t in hashtags or []
               if f"#{t.lstrip('#')}".lower() not in caption.lower()]
    text = caption + ("\n\n" + " ".join(missing) if missing else "")
    return text[:limit]


class ReelsPublisher(BaseUploader):
    """BaseUploader adapter around `publish`. Subclasses set PLATFORM and implement the rest."""

    PLATFORM = ""

    def upload_video(self, video_path: str, title: str, description: str,
                     hashtags: Optional[list] = None, *, on_session=None) -> UploadResult:
        caption = "\n\n".join(p for p in (title, description) if p)
        return self.publish(video_path, caption, hashtags, on_session=on_session)

    def publish(self, video_path: str, caption: str, hashtags: Optional[list] = None,
                *, on_session=None) -> UploadResult:
        """Validate, upload and publish one Reel. Never raises; failures come back in the result.

        `on_session(handle, size)` is called with the container/video id before a
        byte is sent, so upload_guard can ask `query_session` after a crash.
        """
        if not self.is_configured():
            return UploadResult(self.PLATFORM, False, error="Not configured.")
        handle = []

        def session(h, size):
            handle.append(h)
            if on_session:
                on_session(h, size)
        try:
            validate_reel(video_path, self.PLATFORM)
            text = compose_caption(caption, hashtags)
            if self.PLATFORM == "instagram":                 # ≤ 30 hashtags, ≤ 2200 chars (platform_rules)
                import platform_rules
                text = platform_rules.instagram(text)["caption"]
            return self._publish(video_path, text, session)
        except (MetaError, ReelSpecError) as exc:
            logger.error("%s publish failed: %s", self.PLATFORM, exc)
            return UploadResult(self.PLATFORM, False, session_uri=handle[-1] if handle else None,
                                error=f"{self.PLATFORM}: {exc}")
        except Exception as exc:                                  # noqa: BLE001
            # Unexpected (e.g. a 200 without the id). Once bytes went out the post
            # may be live, so the attempt stays open for the guard.
            logger.exception("%s publish raised", self.PLATFORM)
            return UploadResult(self.PLATFORM, False, session_uri=handle[-1] if handle else None,
                                in_doubt=bool(handle), error=f"{self.PLATFORM}: {exc!r}")

    def _publish(self, video_path: str, caption: str, on_session) -> UploadResult:
        raise NotImplementedError

    def check(self) -> Dict:
        """Read-only calls that prove the credentials work and show the remaining quota."""
        raise NotImplementedError

"""Instagram Reels through the Instagram API with Instagram Login (graph.instagram.com).

Flow (developers.facebook.com/docs/instagram-platform/content-publishing):
    1. GET  /<IG_ID>/content_publishing_limit   refuse early when the quota is used
    2. POST /<IG_ID>/media  media_type=REELS upload_type=resumable  -> container id
    3. POST rupload.facebook.com/ig-api-upload/<ver>/<container>   the bytes
    4. GET  /<container>?fields=status_code   until FINISHED
    5. POST /<IG_ID>/media_publish creation_id  -> media id, then its permalink

TOKEN. IG_ACCESS_TOKEN is a 60-day long-lived token. Each refresh returns a
NEW token, which is kept in .tokens/instagram_token.json (gitignored, 0600)
together with a fingerprint of the env token it came from: put a fresh token
in .env and the stored chain is ignored and restarted from it.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Dict, Optional

import uploader
from env_setup import ensure_env_loaded
from uploader import UploadResult

from .common import GRAPH_VERSION, RUPLOAD, MetaError, RateLimited, ReelsPublisher, TokenExpired, call, rupload

logger = logging.getLogger(__name__)

GRAPH = f"https://graph.instagram.com/{GRAPH_VERSION}"
REFRESH_URL = "https://graph.instagram.com/refresh_access_token"
TOKEN_NAME = "instagram"
#: Refresh once the token has less than this left. The docs allow a refresh
#: once a token is 24 h old, so anything well inside 60 days works.
REFRESH_MARGIN_S = 10 * 86400
#: The docs: query the container once per minute, for no more than five minutes.
POLL_INTERVAL_S = 60
POLL_ATTEMPTS = 5


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def stored_token() -> tuple:
    """(token, expires_at) as kept: the stored chain if it came from the env token, else the
    env token with an unknown expiry. Reads only; never refreshes or writes."""
    ensure_env_loaded()
    env = os.getenv("IG_ACCESS_TOKEN", "")
    stored = uploader._load_token(TOKEN_NAME) or {}
    if stored.get("source") == _fingerprint(env) and stored.get("access_token"):
        return stored["access_token"], stored.get("expires_at")
    return env, None


def token_note(expires_at: Optional[float], now: Optional[float] = None) -> str:
    """The token's state for a read-only report (check, dry run)."""
    if not expires_at:
        return "expiry unknown (refresh with refresh-token)"
    left = expires_at - (time.time() if now is None else now)
    days = int(left // 86400)
    if left > REFRESH_MARGIN_S:
        return f"expires in {days} days"
    return f"expires in {days} days (refresh with refresh-token)"


def current_token(now: Optional[float] = None) -> str:
    """The token to use, refreshed first when it is near expiry. Only a real publish and
    `refresh-token` come here; check() and the dry run read stored_token().

    Raises TokenExpired when Meta says the token is dead: refreshing cannot
    revive it, a new one has to be generated (README, Meta setup).
    """
    now = time.time() if now is None else now
    env = os.getenv("IG_ACCESS_TOKEN", "")
    token, expires_at = stored_token()
    if expires_at and expires_at - now > REFRESH_MARGIN_S:
        return token
    try:
        data = call("get", REFRESH_URL, token,
                    params={"grant_type": "ig_refresh_token", "access_token": token})
    except TokenExpired:
        raise TokenExpired("IG_ACCESS_TOKEN is expired or invalid; generate a new long-lived "
                           "token (README, Meta setup) and put it in .env") from None
    except MetaError as exc:
        # A token younger than 24 h cannot be refreshed yet; it still works.
        if expires_at is None or expires_at > now:
            logger.warning("instagram token refresh skipped: %s", exc)
            return token
        raise
    uploader._save_token(TOKEN_NAME, {
        "access_token": data["access_token"],
        "expires_at": now + int(data.get("expires_in") or 60 * 86400),
        "refreshed_at": now,
        "source": _fingerprint(env),
    })
    logger.info("instagram token refreshed; valid %d days", int(data.get("expires_in") or 0) // 86400)
    return data["access_token"]


class InstagramReelsPublisher(ReelsPublisher):
    PLATFORM = "instagram"

    def __init__(self) -> None:
        ensure_env_loaded()
        self.user_id = os.getenv("IG_USER_ID", "")

    def is_configured(self) -> bool:
        return bool(self.user_id and os.getenv("IG_ACCESS_TOKEN"))

    def authenticate(self) -> bool:
        if not self.is_configured():
            logger.error("Instagram: set IG_USER_ID and IG_ACCESS_TOKEN.")
            return False
        try:
            current_token()
        except MetaError as exc:
            logger.error("Instagram: %s", exc)
            return False
        return True

    def quota(self, token: str) -> Dict:
        data = call("get", f"{GRAPH}/{self.user_id}/content_publishing_limit", token,
                    params={"fields": "quota_usage,config", "access_token": token})
        row = (data.get("data") or [{}])[0]
        # The docs disagree (50 vs 100 per 24 h), so the total is read, never assumed.
        return {"used": int(row.get("quota_usage") or 0),
                "total": int((row.get("config") or {}).get("quota_total") or 0)}

    def check(self) -> Dict:
        """Read-only: the token as stored, never refreshed (STEP 70 §2)."""
        token, expires_at = stored_token()
        me = call("get", f"{GRAPH}/me", token, params={"fields": "user_id,username", "access_token": token})
        return {"account": me.get("username"), "quota": self.quota(token), "token": token_note(expires_at)}

    def _publish(self, video_path: str, caption: str, on_session) -> UploadResult:
        token = current_token()
        q = self.quota(token)
        if q["total"] and q["used"] >= q["total"]:
            raise RateLimited(f"publishing limit reached ({q['used']}/{q['total']} in 24 h)")

        container = call("post", f"{GRAPH}/{self.user_id}/media", token, data={
            "media_type": "REELS", "upload_type": "resumable",
            "caption": caption, "access_token": token})["id"]
        if on_session:
            on_session(container, os.path.getsize(video_path))
        rupload(f"{RUPLOAD}/ig-api-upload/{GRAPH_VERSION}/{container}", token, video_path)

        status = ""
        for _ in range(POLL_ATTEMPTS):
            time.sleep(POLL_INTERVAL_S)
            status = self._container_status(container, token)
            if status in ("FINISHED", "ERROR", "EXPIRED"):
                break
        if status != "FINISHED":
            return UploadResult(self.PLATFORM, False, session_uri=container,
                                error=f"instagram: container {container} status {status or 'unknown'}")

        try:
            media_id = call("post", f"{GRAPH}/{self.user_id}/media_publish", token,
                            data={"creation_id": container, "access_token": token})["id"]
        except RateLimited:
            raise
        except MetaError as exc:
            # The publish may have landed even though the answer did not. Ask the container.
            state = self.query_session(container, 0)
            if state["state"] == "published":
                return UploadResult(self.PLATFORM, True, upload_id=state.get("upload_id"),
                                    session_uri=container)
            if state["state"] == "failed":
                raise
            return UploadResult(self.PLATFORM, False, session_uri=container, in_doubt=True,
                                error=f"instagram: publish answer lost ({exc}); check the account")
        return UploadResult(self.PLATFORM, True, upload_id=media_id, session_uri=container,
                             url=self._permalink(media_id, token))

    def _container_status(self, container: str, token: str) -> str:
        try:
            return call("get", f"{GRAPH}/{container}", token,
                        params={"fields": "status_code", "access_token": token}).get("status_code", "")
        except RateLimited:
            raise
        except MetaError as exc:
            logger.warning("instagram container poll failed: %s", exc)
            return ""

    def _permalink(self, media_id: str, token: str) -> Optional[str]:
        try:
            return call("get", f"{GRAPH}/{media_id}", token,
                        params={"fields": "permalink", "access_token": token}).get("permalink")
        except MetaError as exc:
            logger.warning("instagram permalink lookup failed: %s", exc)
            return None

    def query_session(self, session_uri: str, file_size: int) -> Dict:
        """upload_guard's question for an interrupted attempt: is container `session_uri` live?"""
        try:
            token = current_token()
            status = call("get", f"{GRAPH}/{session_uri}", token,
                          params={"fields": "status_code", "access_token": token}).get("status_code")
        except MetaError as exc:
            return {"state": "unknown", "detail": str(exc)}
        if status == "PUBLISHED":
            # The container does not name the media it became; the record keeps no id.
            return {"state": "published", "upload_id": None, "url": None, "detail": status}
        if status in ("ERROR", "EXPIRED"):
            return {"state": "failed", "detail": status}
        # FINISHED may be a publish whose status has not caught up: hold. It turns
        # EXPIRED after 24 h unpublished, and the guard then lets a new one through.
        return {"state": "unknown" if status == "FINISHED" else "incomplete", "detail": status}

    def get_upload_status(self, upload_id: str) -> UploadResult:
        try:
            token = current_token()
            url = self._permalink(upload_id, token)
        except MetaError as exc:
            return UploadResult(self.PLATFORM, False, upload_id=upload_id, error=str(exc))
        return UploadResult(self.PLATFORM, bool(url), upload_id=upload_id, url=url)

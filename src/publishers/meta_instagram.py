"""Instagram Reels through the Instagram API with Facebook Login (graph.facebook.com).

Flow (developers.facebook.com/docs/instagram-platform/content-publishing):
    0. GET  /<PAGE_ID>?fields=instagram_business_account   the IG id, cached
    1. GET  /<IG_ID>/content_publishing_limit   refuse early when the quota is used
    2. POST /<IG_ID>/media  media_type=REELS upload_type=resumable  -> container id (+ uri)
    3. POST rupload.facebook.com/ig-api-upload/<ver>/<container>   the raw bytes
    4. GET  /<container>?fields=status_code   until FINISHED
    5. POST /<IG_ID>/media_publish creation_id  -> media id, then its permalink

WHY THIS PATH (STEP 72). The Instagram Login API (graph.instagram.com) wants a
public video_url for Reels; resumable upload is documented only here. So
Instagram publishes with FB_PAGE_TOKEN, the same Page token Facebook uses: one
token, nothing hosted, nothing to refresh (a Page token from a long-lived user
token does not expire).

THE INSTAGRAM ID is the Page's instagram_business_account.id, looked up once and
kept in .tokens/meta_ids.json (0600). IG_USER_ID in .env never overrides it:
setup-check reports a mismatch.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Dict, Optional

import uploader
from env_setup import ensure_env_loaded
from uploader import UploadResult

from .common import GRAPH_VERSION, RUPLOAD, MetaError, RateLimited, ReelsPublisher, call, rupload

logger = logging.getLogger(__name__)

GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"
IDS_FILE = "meta_ids.json"
NOT_LINKED = "Instagram no está vinculado a la Página"
#: The docs: query the container once per minute, for no more than five minutes.
POLL_INTERVAL_S = 60
POLL_ATTEMPTS = 5


class NotLinked(MetaError):
    """The Page has no Instagram professional account linked. A setup error."""


def _ids_path():
    return uploader.TOKEN_DIR / IDS_FILE


def lookup_ig_account(page_id: str, token: str) -> Dict:
    """{"id", "username"} of the Instagram account linked to the Page. Raises NotLinked."""
    data = call("get", f"{GRAPH}/{page_id}", token,
                params={"fields": "instagram_business_account{id,username}", "access_token": token})
    account = data.get("instagram_business_account") or {}
    if not account.get("id"):
        raise NotLinked(f"{NOT_LINKED}: vincúlalo en Meta Business Suite y ejecuta setup-check")
    return {"id": str(account["id"]), "username": account.get("username")}


def cached_ig_account(page_id: str) -> Optional[Dict]:
    try:
        data = json.loads(_ids_path().read_text())
    except (OSError, ValueError):
        return None
    return data if data.get("page_id") == page_id and data.get("id") else None


def ig_account(page_id: str, token: str, *, cache: bool = True) -> Dict:
    """The cached account, else a lookup (stored only when `cache`: check and dry runs write nothing)."""
    found = cached_ig_account(page_id)
    if found:
        return found
    found = lookup_ig_account(page_id, token)
    if cache:
        uploader._ensure_token_dir()
        fd = os.open(_ids_path(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump({"page_id": page_id, **found}, fh)
        _ids_path().chmod(0o600)
    return {"page_id": page_id, **found}


class InstagramReelsPublisher(ReelsPublisher):
    PLATFORM = "instagram"

    def __init__(self) -> None:
        ensure_env_loaded()
        self.page_id = os.getenv("FB_PAGE_ID", "")
        self.token = os.getenv("FB_PAGE_TOKEN", "")

    def is_configured(self) -> bool:
        return bool(self.page_id and self.token)

    @property
    def user_id(self) -> str:
        """The Page's Instagram id (looked up once, then cached)."""
        return ig_account(self.page_id, self.token)["id"]

    def authenticate(self) -> bool:
        # As Facebook: credentials present is enough here. The Instagram id is looked up
        # in _publish, so «not linked» reaches the result instead of "Authentication failed".
        if not self.is_configured():
            logger.error("Instagram: set FB_PAGE_ID and FB_PAGE_TOKEN.")
        return self.is_configured()

    def quota(self, token: str, ig_id: Optional[str] = None) -> Dict:
        data = call("get", f"{GRAPH}/{ig_id or self.user_id}/content_publishing_limit", token,
                    params={"fields": "quota_usage,config", "access_token": token})
        row = (data.get("data") or [{}])[0]
        # The docs disagree (50 vs 100 per 24 h), so the total is read, never assumed.
        return {"used": int(row.get("quota_usage") or 0),
                "total": int((row.get("config") or {}).get("quota_total") or 0)}

    def check(self) -> Dict:
        """Read-only: GETs only, and the IG id is not cached from here (STEP 70 §2)."""
        account = ig_account(self.page_id, self.token, cache=False)
        return {"account": account.get("username"), "quota": self.quota(self.token, account["id"])}

    def _publish(self, video_path: str, caption: str, on_session) -> UploadResult:
        token = self.token
        q = self.quota(token)
        if q["total"] and q["used"] >= q["total"]:
            raise RateLimited(f"publishing limit reached ({q['used']}/{q['total']} in 24 h)")

        made = call("post", f"{GRAPH}/{self.user_id}/media", token, data={
            "media_type": "REELS", "upload_type": "resumable", "share_to_feed": "true",
            "caption": caption, "access_token": token})
        container = made["id"]
        if on_session:
            on_session(container, os.path.getsize(video_path))
        rupload(made.get("uri") or f"{RUPLOAD}/ig-api-upload/{GRAPH_VERSION}/{container}", token, video_path)

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
            token = self.token
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
            url = self._permalink(upload_id, self.token)
        except MetaError as exc:
            return UploadResult(self.PLATFORM, False, upload_id=upload_id, error=str(exc))
        return UploadResult(self.PLATFORM, bool(url), upload_id=upload_id, url=url)

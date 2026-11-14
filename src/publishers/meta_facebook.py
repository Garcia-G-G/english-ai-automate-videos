"""Facebook Page Reels through the Reels Publishing API (graph.facebook.com).

Flow (developers.facebook.com/docs/video-api/guides/reels-publishing):
    1. POST /<PAGE_ID>/video_reels upload_phase=start          -> video_id, upload_url
    2. POST rupload.facebook.com/video-upload/<ver>/<video_id>  the bytes
    3. POST /<PAGE_ID>/video_reels upload_phase=finish video_state=PUBLISHED description

THE FINISH CALL IS NEVER RETRIED BLIND. If its answer is lost, the reel's
status says whether publishing started; only a status that proves it did not
counts as a failure. Anything else is reported in doubt and the attempt stays
open for upload_guard to reconcile through `query_session`.

FB_PAGE_TOKEN should be a long-lived Page token, which does not expire.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict, Optional

from env_setup import ensure_env_loaded
from uploader import UploadResult

from .common import GRAPH_VERSION, MetaError, RateLimited, ReelsPublisher, call, rupload

logger = logging.getLogger(__name__)

GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"
#: API-published Reels per Page per moving 24 h (Reels publishing guide).
DAILY_LIMIT = 30


def reel_state(status: Dict) -> str:
    """published | failed | incomplete | unknown, from a Video node's `status` field."""
    video = status.get("video_status")
    publishing = status.get("publishing_phase") or {}
    if publishing.get("publish_status") == "published" or publishing.get("status") == "complete":
        return "published"
    if video in ("error", "expired", "upload_failed") or publishing.get("publish_status") == "error":
        return "failed"
    # Publishing under way means finish was accepted: it is going live.
    if publishing.get("status") == "in_progress":
        return "published"
    if (status.get("uploading_phase") or {}).get("status") != "complete":
        return "incomplete"
    # Processing without a publishing phase could be either side of finish: hold.
    if (status.get("processing_phase") or {}).get("status") == "in_progress":
        return "unknown"
    return "incomplete" if publishing.get("status") == "not_started" else "unknown"


class FacebookReelsPublisher(ReelsPublisher):
    PLATFORM = "facebook"

    def __init__(self) -> None:
        ensure_env_loaded()
        self.page_id = os.getenv("FB_PAGE_ID", "")
        self.token = os.getenv("FB_PAGE_TOKEN", "")

    def is_configured(self) -> bool:
        return bool(self.page_id and self.token)

    def authenticate(self) -> bool:
        if not self.is_configured():
            logger.error("Facebook: set FB_PAGE_ID and FB_PAGE_TOKEN.")
        return self.is_configured()

    def published_last_24h(self, now: Optional[datetime] = None) -> int:
        from publication_log import read_attempts
        from upload_limits import published_last_24h
        return len(published_last_24h(read_attempts(), now or datetime.now(), self.PLATFORM))

    def check(self) -> Dict:
        page = call("get", f"{GRAPH}/{self.page_id}", self.token,
                    params={"fields": "name", "access_token": self.token})
        return {"account": page.get("name"),
                "quota": {"used": self.published_last_24h(), "total": DAILY_LIMIT}}

    def _publish(self, video_path: str, caption: str, on_session) -> UploadResult:
        used = self.published_last_24h()
        if used >= DAILY_LIMIT:
            raise RateLimited(f"page limit reached ({used}/{DAILY_LIMIT} reels in 24 h)")
        reels = f"{GRAPH}/{self.page_id}/video_reels"
        start = call("post", reels, self.token,
                     data={"upload_phase": "start", "access_token": self.token})
        video_id = start["video_id"]
        if on_session:
            on_session(video_id, os.path.getsize(video_path))
        rupload(start.get("upload_url") or f"https://rupload.facebook.com/video-upload/{GRAPH_VERSION}/{video_id}",
                self.token, video_path)
        try:
            done = call("post", reels, self.token, data={
                "upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED",
                "description": caption, "access_token": self.token})
        except RateLimited:
            raise
        except MetaError as exc:
            state = self.query_session(video_id, 0)
            # Only a definite failure closes the attempt: right after a lost finish,
            # "not_started" may just mean Meta has not processed it yet.
            if state["state"] == "failed":
                raise
            if state["state"] != "published":
                return UploadResult(self.PLATFORM, False, session_uri=video_id, in_doubt=True,
                                    error=f"facebook: finish answer lost ({exc}); reel {video_id} state unknown")
        else:
            if done.get("success") is False:
                raise MetaError(f"finish for reel {video_id} answered success=false")
        return UploadResult(self.PLATFORM, True, upload_id=video_id, session_uri=video_id,
                            url=self._permalink(video_id))

    def _permalink(self, video_id: str) -> str:
        # permalink_url is not in the Video node's documented fields, so it is
        # asked for and the public reel URL is the fallback.
        try:
            link = call("get", f"{GRAPH}/{video_id}", self.token,
                        params={"fields": "permalink_url", "access_token": self.token}).get("permalink_url")
        except MetaError:
            link = None
        if link and link.startswith("/"):
            link = f"https://www.facebook.com{link}"
        return link or f"https://www.facebook.com/reel/{video_id}"

    def query_session(self, session_uri: str, file_size: int) -> Dict:
        """upload_guard's question for an interrupted attempt: is reel `session_uri` live?"""
        try:
            status = call("get", f"{GRAPH}/{session_uri}", self.token,
                          params={"fields": "status", "access_token": self.token}).get("status") or {}
        except MetaError as exc:
            return {"state": "unknown", "detail": str(exc)}
        state = reel_state(status)
        out = {"state": state, "detail": str(status)[:200]}
        if state == "published":
            out.update(upload_id=session_uri, url=f"https://www.facebook.com/reel/{session_uri}")
        return out

    def get_upload_status(self, upload_id: str) -> UploadResult:
        state = self.query_session(upload_id, 0)
        return UploadResult(self.PLATFORM, state["state"] == "published", upload_id=upload_id,
                            url=state.get("url"), error=None if state["state"] == "published" else state["detail"])

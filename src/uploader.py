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

import json
import logging
import os
import time
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
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

INSTAGRAM_GRAPH_URL = "https://graph.facebook.com/v19.0"

# Retry / polling settings
MAX_POLL_ATTEMPTS = 30
POLL_INTERVAL_SECONDS = 10
UPLOAD_TIMEOUT_SECONDS = 300


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class VideoMetadata:
    """Container for video metadata shared across platforms."""
    title: str
    description: str
    hashtags: list[str] = field(default_factory=list)
    privacy: str = "private"  # private | public | unlisted

    @property
    def hashtag_string(self) -> str:
        return " ".join(f"#{tag.lstrip('#')}" for tag in self.hashtags)

    @property
    def full_description(self) -> str:
        parts = [self.description]
        if self.hashtags:
            parts.append(self.hashtag_string)
        return "\n\n".join(parts)


@dataclass
class UploadResult:
    """Standardised result returned by every uploader."""
    platform: str
    success: bool
    upload_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[dict] = None


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


def _save_token(platform: str, data: dict) -> None:
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

        # Full OAuth2 flow requires user interaction in browser
        auth_url = (
            f"{TIKTOK_AUTH_URL}?client_key={self.client_key}"
            f"&response_type=code&scope=video.upload,video.publish"
            f"&redirect_uri=https://localhost/callback"
        )
        logger.info("TikTok: open this URL to authorize:\n%s", auth_url)
        auth_code = input("Paste the authorization code: ").strip()
        return self._exchange_code(auth_code)

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
                    "privacy_level": "SELF_ONLY" if meta.privacy == "private"
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

    # -- public interface ----------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def authenticate(self) -> bool:
        if not self.is_configured():
            logger.error("YouTube client ID/secret not set in environment.")
            return False

        if self._token_data and not self._token_expired():
            logger.info("YouTube: reusing existing token.")
            return True

        if self._token_data and self._token_data.get("refresh_token"):
            if self._refresh_token():
                return True

        # OAuth2 authorization-code flow (manual paste)
        auth_url = (
            f"{YOUTUBE_AUTH_URL}?client_id={self.client_id}"
            f"&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
            f"&response_type=code"
            f"&scope={'%20'.join(YOUTUBE_SCOPES)}"
            f"&access_type=offline&prompt=consent"
        )
        logger.info("YouTube: open this URL to authorize:\n%s", auth_url)
        auth_code = input("Paste the authorization code: ").strip()
        return self._exchange_code(auth_code)

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        hashtags: Optional[list[str]] = None,
    ) -> UploadResult:
        if not self._token_data:
            return UploadResult(self.PLATFORM, False, error="Not authenticated.")

        meta = VideoMetadata(title, description, hashtags or [])

        # Ensure #Shorts appears so YouTube surfaces it as a Short
        shorts_tag = "#Shorts"
        yt_title = meta.title if shorts_tag in meta.title else f"{meta.title} {shorts_tag}"

        privacy_map = {
            "public": "public",
            "unlisted": "unlisted",
            "private": "private",
        }
        privacy_status = privacy_map.get(meta.privacy, "private")

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

        # Step 2 – upload file in chunks
        file_size = os.path.getsize(video_path)
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
                                            raw_response=result_data)
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
            return UploadResult(self.PLATFORM, False, error=str(exc))

        return UploadResult(self.PLATFORM, False, error="Upload ended unexpectedly.")

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

    def _exchange_code(self, code: str) -> bool:
        try:
            resp = requests.post(YOUTUBE_TOKEN_URL, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
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

                result = uploader.upload_video(
                    video_path, title, description, hashtags, **kwargs,
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
            return {"success": r.success, "error": r.error, "upload_id": r.upload_id, "url": r.url}
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

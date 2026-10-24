"""Why an upload failed, in Spanish, and when the channel can take the next one (STEP 67).

On 2026-10-16 the 11th YouTube upload in 24 h failed with a bare «400 Client Error: Bad
Request», and the next 13 attempts failed the same way: upload_video threw Google's body
away. The uploader now keeps `error.errors[0].reason` in the error string,
«youtube 400 uploadLimitExceeded: …», and this module turns that string and
output/published/attempts.jsonl into what the panels show: a reason in Spanish, the
uploads of the last 24 h, the time the oldest of them frees a slot, and whether the
YouTube button must wait. Pure functions; the attempts are passed in.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional

UPLOAD_LIMIT = "uploadLimitExceeded"
QUOTA = "quotaExceeded"
WINDOW = timedelta(hours=24)
_FIELD = {"invalidTitle": "el título", "invalidDescription": "la descripción", "invalidTags": "las etiquetas"}
_REASON_RE = re.compile(r"\b(?:youtube|tiktok|instagram) \d{3} ([A-Za-z]+)")


def error_text(platform: str, status: int, body) -> str:
    """«youtube 400 uploadLimitExceeded: message» from a Google error body (dict or text)."""
    reason, message = "", ""
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else {}
        errors = err.get("errors") or [{}]
        reason = str(errors[0].get("reason") or err.get("status") or "")
        message = str(err.get("message") or "")
    elif body:
        message = str(body)[:200]
    return f"{platform} {status} {reason or 'error'}: {message}".strip().rstrip(":")


def reason_of(error: Optional[str]) -> Optional[str]:
    match = _REASON_RE.search(error or "")
    return match.group(1) if match else None


def _at(row: Dict) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(row["at"])
    except (KeyError, TypeError, ValueError):
        return None


def published_last_24h(attempts: Iterable[Dict], now: datetime, platform: str = "youtube") -> List[datetime]:
    """When each upload of the last 24 h went live, oldest first."""
    return sorted(t for r in attempts if r.get("platform") == platform and r.get("status") == "published"
                  and (t := _at(r)) is not None and now - WINDOW < t <= now)


def next_free_slot(attempts: Iterable[Dict], now: datetime, platform: str = "youtube") -> Optional[datetime]:
    """The oldest upload of the last 24 h, plus 24 h: when the channel frees one slot."""
    times = published_last_24h(attempts, now, platform)
    return times[0] + WINDOW if times else None


def spanish(error: Optional[str], attempts: Iterable[Dict] = (), now: Optional[datetime] = None) -> str:
    """What the panel says for a failed upload."""
    reason = reason_of(error)
    if reason == UPLOAD_LIMIT:
        slot = next_free_slot(list(attempts), now or datetime.now())
        when = f" Se libera hacia las {slot:%H:%M}." if slot else ""
        return f"YouTube: el canal llegó a su límite de subidas de 24 h.{when}"
    if reason == QUOTA:
        return "Cuota diaria de la API agotada; vuelve mañana después de la 1:00."
    if reason in _FIELD:
        return f"YouTube rechazó {_FIELD[reason]} ({reason})."
    return reason or (error or "Error desconocido")


def limit_block(attempts: Iterable[Dict], now: datetime, platform: str = "youtube") -> Optional[str]:
    """The message that keeps the YouTube button disabled, or None.

    Set by a failed attempt whose detail carries uploadLimitExceeded, until the slot
    time; a later successful upload clears it."""
    rows = [r for r in attempts if r.get("platform") == platform and r.get("status") in ("failed", "published")]
    if not rows or rows[-1].get("status") != "failed" or UPLOAD_LIMIT not in str(rows[-1].get("detail")):
        return None
    # the slot the refusal was waiting for: counted at the refusal, not now, or the
    # window would slide past it and keep the button grey for another day
    failed_at = _at(rows[-1]) or now
    slot = next_free_slot(rows, failed_at, platform)
    if slot is not None and now >= slot:
        return None
    return spanish(f"{platform} 400 {UPLOAD_LIMIT}", rows, failed_at)


def stops_batch(result) -> bool:
    """A batch stops at the first upload limit: the next video would fail the same way."""
    error = result.get("error") if isinstance(result, dict) else getattr(result, "error", None)
    return reason_of(error) == UPLOAD_LIMIT


def run_batch(videos: List, upload_one: Callable) -> Optional[str]:
    """upload_one(video) -> [results]; stops at the first upload limit and returns its message."""
    for video in videos:
        for result in upload_one(video) or []:
            if stops_batch(result):
                error = result.get("error") if isinstance(result, dict) else getattr(result, "error", None)
                return spanish(error)
    return None


_IN_FLIGHT: set = set()
_LOCK = threading.Lock()


def claim(artifact: str, platform: str) -> bool:
    """True for the first press; False while an attempt on the same video runs."""
    with _LOCK:
        if (artifact, platform) in _IN_FLIGHT:
            return False
        _IN_FLIGHT.add((artifact, platform))
        return True


def release(artifact: str, platform: str) -> None:
    with _LOCK:
        _IN_FLIGHT.discard((artifact, platform))

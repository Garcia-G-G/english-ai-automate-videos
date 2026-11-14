"""STEP 85 §4: the guarded upload, UI-free. Extracted from admin.py so the Streamlit page and the panel API send a
video through ONE path: guard decision, attempt log before a byte is sent, Meta publish lock, YouTube private with
`publishAt` at the exact time given, the ledger row, the thumbnail follow-up. admin.py keeps thin wrappers with the old
names; the only change is that `st` is now plain parameters (`state` for the operator's edits, `on_error` for the notice)."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import jobs

logger = logging.getLogger(__name__)


def guard_decide(artifact: str, platform: str, manager=None, **content):
    """Ask the idempotency guard before uploading. See upload_guard."""
    from upload_guard import decide
    return decide(artifact, platform, manager=manager, **content)


def upload_content(video: dict, script: dict, title: str, description: str, allow_duplicate: bool = False) -> dict:
    """What upload_guard.content_refusal checks for one approved video."""
    return {"title": title, "description": description,
            "gate": (video.get("meta") or {}).get("gate"),
            "topic_id": (script.get("_meta") or {}).get("topic_id"),
            "topic_name": script.get("theme") or (script.get("_meta") or {}).get("topic"),
            "allow_duplicate": allow_duplicate}


def move_to_uploaded(video_path: Path, upload_info: dict = None):
    """Move a video from approved/ to uploaded/, saving the upload info in its sidecar."""
    from .videos import read_sidecar
    dest_dir = jobs.UPLOADED_DIR / video_path.parent.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    import thumbs
    thumbs.carry(video_path, dest_dir)
    shutil.move(str(video_path), str(dest_dir / video_path.name))
    meta_path = video_path.with_suffix(".json")
    dest_meta = dest_dir / meta_path.name
    if meta_path.exists():
        meta, _ = read_sidecar(meta_path)
        if upload_info:
            meta["upload_info"] = upload_info
        shutil.move(str(meta_path), str(dest_meta))
        with open(dest_meta, "w") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)


def guarded_upload(manager, artifact: str, platform: str, video_path: str,
                    **kwargs):
    """_guarded_upload_unlocked, under the Meta publish lock for Instagram and Facebook
    (STEP 70 §3): a click while the slot tick publishes does nothing, and a video the tick
    has just published is not sent again."""
    from publishers import schedule
    if platform not in schedule.LOCKED_PLATFORMS:
        return guarded_upload_unlocked(manager, artifact, platform, video_path, **kwargs)
    with schedule.publish_lock() as got:
        if not got:
            return {"success": False, "error": schedule.LOCKED, "locked": True}
        state = schedule.platform_status(artifact, platform)["status"]
        if state in ("published", "holding"):           # re-read under the lock
            return {"success": False, "error": f"ya publicado o en curso en {platform}", "locked": True}
        return guarded_upload_unlocked(manager, artifact, platform, video_path, **kwargs)




def guarded_upload_unlocked(manager, artifact: str, platform: str, video_path: str,
                             **kwargs):
    """manager.upload, with the attempt persisted before a byte is sent.

    The dashboard needs this for the same reason main.py does: the window
    between a live video and its ledger row is structural, not specific to
    the unattended path.
    """
    import os as _os

    from publication_log import (ATTEMPT_FAILED, ATTEMPT_PUBLISHED,
                                 ATTEMPT_SESSION, ATTEMPT_STARTED,
                                 ATTEMPT_UNKNOWN, record_attempt)

    from upload_limits import claim, release

    # STEP 67: a second press while this video is uploading does nothing, and logs nothing.
    if not claim(artifact, platform):
        return {"success": False, "error": "ya se está subiendo este vídeo", "in_flight": True}
    try:
        size = _os.path.getsize(video_path)
    except OSError:
        size = 0

    record_attempt(artifact=artifact, platform=platform,
                   status=ATTEMPT_STARTED, video_path=video_path,
                   file_size=size, detail=str(kwargs.get("title", ""))[:120])

    def _session(uri, sz):
        record_attempt(artifact=artifact, platform=platform,
                       status=ATTEMPT_SESSION, video_path=video_path,
                       session_uri=uri, file_size=sz,
                       detail=str(kwargs.get("title", ""))[:120])

    # STEP 81 §2 / STEP 83 §3: YouTube goes up private and publishes itself at a free slot (the one Revisar
    # shows, else the next one); every other platform is untouched.
    scheduled_for = kwargs.pop("scheduled_for", None)
    scheduled_by = "garcia" if scheduled_for is not None else "auto"       # STEP 85 §0: his own time skips the limits
    if platform == "youtube" and "publish_at" not in kwargs:
        import slots as _slots
        scheduled_for = scheduled_for or _slots.next_free()
        if scheduled_for is not None:
            kwargs["publish_at"] = _slots.publish_at(scheduled_for)
    try:
        result = manager.upload(platform, video_path, on_session=_session, **kwargs)
    finally:
        release(artifact, platform)
    if scheduled_for is not None and platform == "youtube":
        try:
            result["scheduled_for"] = scheduled_for.isoformat()
        except TypeError:
            setattr(result, "scheduled_for", scheduled_for.isoformat())
        try:
            result["scheduled_by"] = scheduled_by
        except TypeError:
            setattr(result, "scheduled_by", scheduled_by)

    ok = (result.get("success") if isinstance(result, dict)
          else getattr(result, "success", False))
    uri = (result.get("session_uri") if isinstance(result, dict)
           else getattr(result, "session_uri", None))
    vid = (result.get("upload_id") if isinstance(result, dict)
           else getattr(result, "upload_id", None))

    # On success the attempt is closed only AFTER _record_upload writes the
    # ledger row, so it is left open here deliberately. On failure it is
    # closed now, because the platform said nothing was created.
    if not ok:
        err = (result.get("error") if isinstance(result, dict)
               else getattr(result, "error", None))
        doubt = (result.get("in_doubt") if isinstance(result, dict)
                 else getattr(result, "in_doubt", False))
        record_attempt(artifact=artifact, platform=platform,
                       status=ATTEMPT_UNKNOWN if doubt else ATTEMPT_FAILED,
                       video_path=video_path,
                       session_uri=uri, file_size=size,
                       detail=str(err or result)[:300])
    return result




def record_upload(video: dict, platform: str, result,
                  sent_title: str, sent_description: str,
                  sent_hashtags: list, on_error=None) -> None:
    """Persist the publication, and SHOUT if that fails.

    A video that is live but unrecorded is worse than a failed upload: a
    failure can be retried, an unrecorded success has to be found by hand on
    the platform. So a recording failure is surfaced in the UI rather than
    swallowed — the upload itself already succeeded and cannot be undone, but
    the operator has to know the id was lost.

    This is now only the UI half. The recording itself lives in
    publication_log.record_upload_result, so main.py's headless path uses the
    same recorder rather than a second one that could drift from it.
    """
    from publication_log import (ATTEMPT_PUBLISHED, ATTEMPT_SESSION,
                                 PublicationRecordError, record_attempt,
                                 record_upload_result)

    uri = (result.get("session_uri") if isinstance(result, dict)
           else getattr(result, "session_uri", None))
    vid = (result.get("upload_id") if isinstance(result, dict)
           else getattr(result, "upload_id", None))

    if platform == "youtube":                               # STEP 85b §4: the thumbnail follows the upload, never blocks it
        _vid_id = (result.get("upload_id") if isinstance(result, dict) else getattr(result, "upload_id", None))
        _jpg = Path(video["path"]).with_name(Path(video["path"]).stem + ".thumb") / "thumb.jpg"
        if _vid_id and _jpg.exists():
            try:
                from thumbs import publish as _tp
                _tp.after_youtube_upload(video["name"], str(_vid_id), _jpg)
            except Exception:                               # noqa: BLE001
                logger.exception("thumbnail follow-up not started for %s", video["name"])
    if platform == "facebook":                              # STEP 85b §4: same follow-up for the reel; the reel is already live
        _fb_id = (result.get("upload_id") if isinstance(result, dict) else getattr(result, "upload_id", None))
        _fjpg = Path(video["path"]).with_name(Path(video["path"]).stem + ".thumb") / "thumb.jpg"
        if _fb_id and _fjpg.exists():
            try:
                from thumbs import publish as _tp
                _tp.after_facebook_upload(video["name"], str(_fb_id), _fjpg)
            except Exception:                               # noqa: BLE001
                logger.exception("facebook thumbnail follow-up not started for %s", video["name"])
    try:
        record_upload_result(
            artifact=video["name"],
            video_path=str(video["path"]),
            video_type=video.get("type", ""),
            platform=platform,
            result=result,
            sent_title=sent_title,
            sent_description=sent_description,
            sent_hashtags=sent_hashtags,
            extra=({"scheduled_for": _sf, "scheduled_by": (result.get("scheduled_by") if isinstance(result, dict)
                                                           else getattr(result, "scheduled_by", None))}
                   if (_sf := (result.get("scheduled_for") if isinstance(result, dict)
                               else getattr(result, "scheduled_for", None))) else None),
        )
        # Only now is the attempt closed: the video is live AND named.
        record_attempt(artifact=video["name"], platform=platform,
                       status=ATTEMPT_PUBLISHED, video_path=str(video["path"]),
                       session_uri=uri, upload_id=vid, detail="recorded")
    except PublicationRecordError as exc:
        logger.exception("publication record failed")
        # Leave the attempt OPEN, now carrying the id. That open row is what
        # stops the next run from publishing a second copy.
        record_attempt(artifact=video["name"], platform=platform,
                       status=ATTEMPT_SESSION, video_path=str(video["path"]),
                       session_uri=uri, upload_id=vid,
                       detail=f"published but record failed: {exc}")
        (on_error or logger.error)(
            f"⚠️ Subido a {platform} pero NO SE PUDO REGISTRAR: {exc}. "
            f"The video is live and this repo cannot name it — note the id now."
        )




def schedule_approved(video: dict, script: dict, platforms: list, slot, state=None, mover=None, on_error=None) -> dict:
    """STEP 83 §3: send an approved video to each platform through the SAME guarded path as Subir (guard decision,
    attempt log, ledger row), YouTube private with publishAt at `slot`. Returns {platform: reason} for the ones
    that failed; empty when all went. On full success the video moves to «subidos»."""
    import slots as _s
    from upload_metadata import resolve_upload_metadata
    from uploader import get_upload_manager
    failed, done = {}, []
    if slot is not None and "youtube" in platforms:           # STEP 85 §0: the lead rule is the one limit that binds Garcia
        _err = _s.check_time(slot, [], datetime.now(slot.tzinfo))["error"]
        if _err:
            failed["youtube"] = _err
            platforms = [p for p in platforms if p != "youtube"]
            if not platforms:
                return failed
    manager = get_upload_manager()
    resolved = resolve_upload_metadata(video["name"], script, "", video.get("type", "educational"),
                                       (script.get("_meta") or {}).get("category", ""), state,
                                       generated=(video.get("meta") or {}).get("metadata"))
    title, desc, tags = resolved["title"][:100], resolved["description"], [t.lstrip("#") for t in resolved["hashtags"]]
    for platform in platforms:
        verdict = guard_decide(video["name"], platform, manager=manager, **upload_content(video, script, title, desc, False))
        if not verdict.should_upload:
            if verdict.action == "skip_done":
                done.append(platform)
            else:
                failed[platform] = verdict.reason
            continue
        extra = {"scheduled_for": slot} if (platform == "youtube" and slot is not None) else {}
        result = guarded_upload(manager, video["name"], platform, str(video["path"]), title=title, description=desc,
                                 hashtags=tags, **extra)
        ok = (isinstance(result, dict) and result.get("success")) or getattr(result, "success", False)
        if ok:
            done.append(platform)
            record_upload(video, platform, result, title, desc, tags, on_error=on_error)
        else:
            err = result.get("error") if isinstance(result, dict) else getattr(result, "error", "")
            failed[platform] = str(err or "error")[:120]
    if done and not failed and video["path"].exists():
        (mover or move_to_uploaded)(video["path"], {"platforms": done, "uploaded_at": datetime.now().isoformat(), "title": title,
                                         **({"scheduled_by": "garcia"} if slot is not None else {"scheduled_by": "auto"})})
    return failed

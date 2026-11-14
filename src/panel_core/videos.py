"""STEP 85 §0: the video lists and the review actions, with no UI. admin.py (Streamlit) and the new panel API
both import from here. Directories are read from `jobs` at call time, so a test that redirects them there
redirects every caller."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import jobs

logger = logging.getLogger(__name__)


#: What a page shows for a sidecar that is not valid JSON (STEP 75 §3).
DAMAGED = "archivo dañado"


def read_sidecar(meta_file: Path):
    """(meta, problem): problem is None, or «archivo dañado: name (why)» instead of a crash."""
    try:
        meta = json.loads(Path(meta_file).read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            raise ValueError("not an object")
        return meta, None
    except (OSError, ValueError) as e:
        logger.warning("sidecar %s unreadable: %s", meta_file, e)
        return {}, f"{DAMAGED}: {Path(meta_file).name} ({type(e).__name__})"


def get_pending_videos(root: Optional[Path] = None) -> list:
    base = root if root is not None else jobs.PENDING_DIR
    videos = []
    if not base.exists():
        return videos
    for type_dir in base.iterdir():
        if type_dir.is_dir():
            for video_file in type_dir.glob("*.mp4"):
                meta_file = video_file.with_suffix('.json')
                if not meta_file.exists():
                    # STEP 59 §6: no sidecar means the job never finished it.
                    logger.warning("review: %s has no sidecar; not shown", video_file.name)
                    continue
                meta, damaged = read_sidecar(meta_file)
                videos.append({
                    "path": video_file,
                    "type": type_dir.name,
                    "name": video_file.stem,
                    "meta": meta,
                    "damaged": damaged,
                    "stage": "pending",
                    "created": datetime.fromtimestamp(video_file.stat().st_mtime)
                })
    return sorted(videos, key=lambda x: x["created"], reverse=True)


def get_approved_videos(root: Optional[Path] = None) -> list:
    """Videos awaiting upload, each annotated with what the ledger knows.

    THE SECOND DUPLICATE VECTOR. main.py never moves an uploaded file the way
    move_to_uploaded does for the dashboard, so an already-published video
    stays sitting in approved/ where this function lists it as ready to
    upload. The operator then uploads it again BY HAND — and a hand upload is
    exactly how hPdSoqjvu3E happened.

    Moving the file (main.py now does) is not sufficient on its own: a move
    can fail, a re-render puts the file back, and the operator can move it
    back. The ledger is the authority on what is published, so the list
    consults it. The two fixes cover different failure modes and both are
    applied — the move keeps disk state honest, this keeps the DECISION
    honest even when disk state is not.
    """
    base = root if root is not None else jobs.APPROVED_DIR
    from publication_log import find_by_artifact

    videos = []
    if not base.exists():
        return videos
    for type_dir in base.iterdir():
        if type_dir.is_dir():
            for video_file in type_dir.glob("*.mp4"):
                meta_file = video_file.with_suffix('.json')
                meta, damaged = read_sidecar(meta_file) if meta_file.exists() else ({}, None)
                published = find_by_artifact(video_file.stem)
                videos.append({
                    "path": video_file,
                    "type": type_dir.name,
                    "name": video_file.stem,
                    "meta": meta,
                    "damaged": damaged,
                    "stage": "approved",
                    "published_to": sorted({r.get("platform") for r in published
                                            if r.get("platform")}),
                    "published_rows": published,
                    "created": datetime.fromtimestamp(video_file.stat().st_mtime)
                })
    return sorted(videos, key=lambda x: x["created"], reverse=True)


def get_library_videos(root: Optional[Path] = None) -> list:
    base = root if root is not None else jobs.VIDEO_DIR
    videos = []
    if not base.exists():
        return videos
    for type_dir in base.iterdir():
        if type_dir.is_dir():
            for video_file in type_dir.glob("*.mp4"):
                videos.append({
                    "path": video_file,
                    "type": type_dir.name,
                    "name": video_file.stem,
                    "size": video_file.stat().st_size,
                    # output/video/ is where `main.py --batch` stops. Until
                    # promote_to_review existed this was a dead end.
                    "stage": "batch",
                    "created": datetime.fromtimestamp(video_file.stat().st_mtime)
                })
    return sorted(videos, key=lambda x: x["created"], reverse=True)


def approve_video(video_path: Path, approved_dir: Optional[Path] = None):
    video_type = video_path.parent.name
    dest_dir = (approved_dir or jobs.APPROVED_DIR) / video_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    import thumbs
    thumbs.carry(video_path, dest_dir)                      # STEP 85b: the <stem>.thumb/ folder travels with it
    shutil.move(str(video_path), str(dest_dir / video_path.name))
    meta_path = video_path.with_suffix('.json')
    if meta_path.exists():
        shutil.move(str(meta_path), str(dest_dir / meta_path.name))
    from publishers import schedule
    if schedule.settings()["auto_enqueue_on_approve"]:
        try:
            schedule.enqueue(dest_dir / video_path.name)
        except (OSError, ValueError):
            logger.exception("could not queue %s for Meta publishing", video_path.name)


def reject_video(video_path: Path, rejected_dir: Optional[Path] = None):
    video_type = video_path.parent.name
    dest_dir = (rejected_dir or jobs.REJECTED_DIR) / video_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    import thumbs
    thumbs.carry(video_path, dest_dir)
    shutil.move(str(video_path), str(dest_dir / video_path.name))
    meta_path = video_path.with_suffix('.json')
    if meta_path.exists():
        shutil.move(str(meta_path), str(dest_dir / meta_path.name))

#!/usr/bin/env python3
"""One cached still per artifact, so a list of videos can be seen at a glance.

WHY NOT st.video. A player per row makes the browser fetch and decode every
artifact on the page. Eleven of them on Inicio is eleven video elements before
the operator has decided to watch anything. A still is one small jpg.

WHERE THE CACHE LIVES. Not next to the mp4, which is the obvious place and the
wrong one here: an artifact MOVES through output/video -> pending -> approved
-> uploaded, and a sidecar jpg would either be left behind as litter at every
stage or have to be carried by five separate move helpers. What is stable
across those moves is <video_type>/<stem>, because every stage directory has
the shape <stage>/<type>/<artifact>.mp4. So that is the key, and the cache is
one directory: output/thumbs/<type>/<stem>.jpg. An artifact keeps its
thumbnail for its whole life and is extracted exactly once.

The type is part of the key rather than the stem alone because nothing stops
vocabulary/blue.mp4 and quiz/blue.mp4 existing at the same time.

FAILURE IS NOT AN EXCEPTION. These calls happen inside a render loop. A
missing ffmpeg, a truncated mp4 or a zero-length file must degrade to "no
picture", never to a traceback that blanks the page.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
THUMBS_DIR = ROOT / "output" / "thumbs"

#: Seconds into the artifact to grab. Not 0: frame zero of these videos is
#: often the background before any text has been drawn, which makes every
#: thumbnail look identical.
DEFAULT_OFFSET_S = 1.5

#: Rendered height in pixels. The artifacts are 1080x1920, so this is ~113px
#: wide — a column of these reads as a list, not a wall.
DEFAULT_HEIGHT = 200

#: How long to let ffmpeg run before giving up on one still.
TIMEOUT_S = 20


def thumbnail_path(video_path, thumbs_dir: Path = None) -> Path:
    """Where this artifact's still lives. Pure; touches no disk."""
    video_path = Path(video_path)
    base = Path(thumbs_dir) if thumbs_dir else THUMBS_DIR
    return base / video_path.parent.name / f"{video_path.stem}.jpg"


def _extract(video_path: Path, out: Path, offset: float, height: int) -> bool:
    """One ffmpeg call. True if it left a non-empty file behind."""
    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
        "-ss", f"{offset:.3f}", "-i", str(video_path),
        "-frames:v", "1", "-vf", f"scale=-2:{height}",
        "-q:v", "4", str(out),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("thumbnail: ffmpeg failed for %s: %s", video_path, e)
        return False
    if proc.returncode != 0:
        logger.warning("thumbnail: ffmpeg rc=%s for %s: %s",
                       proc.returncode, video_path, proc.stderr.strip()[:200])
    return out.exists() and out.stat().st_size > 0


def ensure_thumbnail(video_path, *, offset: float = DEFAULT_OFFSET_S,
                     height: int = DEFAULT_HEIGHT, thumbs_dir: Path = None,
                     force: bool = False) -> Optional[str]:
    """The cached still for this artifact, extracting it once if needed.

    Returns a path as str (what st.image wants) or None if no picture could
    be made. Regenerates when the mp4 is newer than the cached jpg, so a
    re-render is not represented by its predecessor's frame.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return None

    out = thumbnail_path(video_path, thumbs_dir)
    if not force and out.exists() and out.stat().st_size > 0:
        try:
            if out.stat().st_mtime >= video_path.stat().st_mtime:
                return str(out)
        except OSError:
            pass

    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("thumbnail: cannot create %s: %s", out.parent, e)
        return None

    if _extract(video_path, out, offset, height):
        return str(out)

    # An artifact shorter than the offset yields nothing at that seek. Frame
    # zero is a worse picture but it is a picture.
    if offset > 0 and _extract(video_path, out, 0.0, height):
        return str(out)

    out.unlink(missing_ok=True)
    return None

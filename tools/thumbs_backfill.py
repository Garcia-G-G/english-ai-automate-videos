#!/usr/bin/env python3
"""STEP 85b §5: make `<stem>.thumb/` for every video on disk that lacks one, from its MP4 (or, for Tablero
videos, from the kit and the audio json's beats), with the §2 checks. One background run; prints the time and sizes.

    python3 tools/thumbs_backfill.py [--limit N]
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import thumbs  # noqa: E402

STAGES = ("pending", "approved", "uploaded", "video")


def audio_json(mp4: Path) -> dict:
    p = ROOT / "output" / "audio" / mp4.parent.name / f"{mp4.stem}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def duration(mp4: Path) -> float:
    from panel.revisar import duration_seconds
    return duration_seconds(mp4) or 0.0


def main(argv):
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    t0, done, skipped, failed, total_bytes = time.time(), 0, 0, 0, 0
    for stage in STAGES:
        for mp4 in sorted((ROOT / "output" / stage).glob("*/*.mp4")):
            if (thumbs.thumb_dir(mp4) / "thumb.jpg").exists():
                skipped += 1
                continue
            if limit is not None and done >= limit:
                break
            data = audio_json(mp4)
            dur = float(data.get("duration") or 0) or duration(mp4)
            info = thumbs.make_for_video(mp4, {**data, "type": mp4.parent.name, "design_variant": data.get("design_variant") or "cuaderno"}, dur) if dur else None
            if info:
                done += 1
                total_bytes += (thumbs.thumb_dir(mp4) / "thumb.jpg").stat().st_size
            else:
                failed += 1
    secs = time.time() - t0
    print(f"made {done}, already had {skipped}, failed {failed}; {secs:.0f} s; {total_bytes / 1e6:.1f} MB of thumb.jpg")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

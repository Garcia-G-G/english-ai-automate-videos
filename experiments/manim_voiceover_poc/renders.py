"""Where finished videos go and how they are recorded — shared by the admin page and batch_run.py."""
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
SCENE_FILE, SCENE_CLASS = "lesson_scene.py", "Lesson"
QUALITIES = {"l": ("480p15", "Borrador · 480p, rápido"), "m": ("720p30", "Normal · 720p"),
             "f": ("1080p30", "Final · 1080p (recomendado)"), "h": ("1080p60", "Final · 1080p60, lento")}
DEFAULT_QUALITY = "f"
QUALITY_FLAGS = {"f": ["-r", "1920,1080", "--fps", "30"]}     # the others are Manim's own -q letters


def manim_binary(studio_dir: Path = HERE) -> Optional[str]:
    local = studio_dir / ".venv" / "bin" / "manim"
    return str(local) if local.exists() else shutil.which("manim")


def render_command(manim_bin: str, quality: str, lesson_id: str, voice: str) -> tuple:
    """(argv, env additions) — the scene reads LESSON and VOICE_DIR, nothing else."""
    if quality not in QUALITIES:
        raise ValueError(f"quality must be one of {list(QUALITIES)}")
    flags = QUALITY_FLAGS.get(quality, [f"-q{quality}"])
    argv = [manim_bin, *flags, "--disable_caching", SCENE_FILE, SCENE_CLASS]
    env = {"LESSON": f"lessons/{lesson_id}.json", "VOICE_DIR": f"audio/{lesson_id}/{voice}"}
    return argv, env


def rendered_output(quality: str, studio_dir: Path = HERE) -> Path:
    return studio_dir / "media" / "videos" / Path(SCENE_FILE).stem / QUALITIES[quality][0] / f"{SCENE_CLASS}.mp4"


def probe_duration(path: Path) -> Optional[float]:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, timeout=30)
        return round(float(out.stdout.strip()), 2)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def timeline_path(lesson_id: str, studio_dir: Path = HERE) -> Path:
    return studio_dir / "media" / "timeline" / f"{lesson_id}.json"


def chapters_text(timeline: dict) -> str:
    """YouTube-style chapters from the section cards: `m:ss Title`, first line at 0:00."""
    lines = ["0:00 Introducción"]
    for beat in timeline.get("beats", []):
        if beat.get("type") == "heading" and beat.get("text") and beat.get("start", 0) >= 10:
            start = int(beat["start"])
            lines.append(f"{start // 60}:{start % 60:02d} {beat['text']}")
    return "\n".join(lines) + "\n"


def poster_time(timeline: dict, duration: Optional[float]) -> float:
    """A frame from the title card once it has fully drawn: 2.5 s in, or 5 % of the video."""
    first = (timeline.get("beats") or [{}])[0]
    if first.get("type") == "title":
        return min(first.get("start", 0) + 2.5, max(0.5, (duration or 60) * 0.05))
    return max(0.5, (duration or 60) * 0.05)


def make_poster(video: Path, at: float, out: Path) -> bool:
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1",
                        "-q:v", "3", str(out)], check=True, timeout=60)
        return out.exists()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def register(source_mp4: Path, lesson_id: str, voice: str, quality: str, seconds: float,
             studio_dir: Path = HERE, now: Optional[datetime] = None) -> dict:
    """Copy the render, its .srt, the beat timeline, a poster frame and a chapters file into
    renders/<lesson>/ and append one ledger row."""
    folder = studio_dir / "renders" / lesson_id
    folder.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now()
    target = folder / f"{now.strftime('%Y%m%d-%H%M%S')}_{voice}_{QUALITIES[quality][0]}.mp4"
    shutil.copyfile(source_mp4, target)
    srt = source_mp4.with_suffix(".srt")
    if srt.exists():
        shutil.copyfile(srt, target.with_suffix(".srt"))
    duration = probe_duration(target)
    timeline = {}
    tl_src = timeline_path(lesson_id, studio_dir)
    if tl_src.exists():
        timeline = json.loads(tl_src.read_text(encoding="utf-8"))
        shutil.copyfile(tl_src, target.with_suffix(".timeline.json"))
        target.with_suffix(".chapters.txt").write_text(chapters_text(timeline), encoding="utf-8")
    poster = target.with_suffix(".jpg")
    has_poster = make_poster(target, poster_time(timeline, duration), poster)
    row = {"at": now.isoformat(timespec="seconds"), "lesson": lesson_id, "file": f"{lesson_id}/{target.name}",
           "voice": voice, "quality": QUALITIES[quality][0], "bytes": target.stat().st_size,
           "duration_s": duration, "render_seconds": round(seconds, 1),
           "poster": f"{lesson_id}/{poster.name}" if has_poster else None,
           "chapters": f"{lesson_id}/{target.with_suffix('.chapters.txt').name}" if timeline else None}
    with (studio_dir / "renders" / "ledger.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def ledger(studio_dir: Path = HERE) -> list:
    path = studio_dir / "renders" / "ledger.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows))

"""Where finished videos go and how they are recorded — shared by the admin page and batch_run.py."""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
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


def render_command(manim_bin: str, quality: str, lesson_id: str, voice: str, theme: Optional[str] = None,
                   sfx: bool = True) -> tuple:
    """(argv, env additions) — the scene reads LESSON and VOICE_DIR, and THEME / SFX when given
    (no THEME: the lesson's "theme", else brand.json's default)."""
    if quality not in QUALITIES:
        raise ValueError(f"quality must be one of {list(QUALITIES)}")
    flags = QUALITY_FLAGS.get(quality, [f"-q{quality}"])
    argv = [manim_bin, *flags, "--disable_caching", SCENE_FILE, SCENE_CLASS]
    env = {"LESSON": f"lessons/{lesson_id}.json", "VOICE_DIR": f"audio/{lesson_id}/{voice}"}
    if theme:
        env["THEME"] = theme
    if not sfx:
        env["SFX"] = "0"
    return argv, env


def theme_names(studio_dir: Path = HERE) -> tuple:
    """(names, default) from brand.json → manim — the dashboard's dropdown."""
    brand = studio_dir.parent.parent / "assets" / "branding" / "english-unlimited" / "brand.json"
    block = json.loads(brand.read_text(encoding="utf-8"))["manim"]
    return list(block["themes"]), block["default_theme"]


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
    """A frame from the title card once it has fully drawn: 2.5 s into it. The title may
    be beat 2 or 3 (a lesson can open on a hook), so it is looked for, not assumed."""
    title = next((b for b in timeline.get("beats") or [] if b.get("type") == "title"), None)
    if title is not None:
        return title.get("start", 0) + 2.5
    return max(0.5, (duration or 60) * 0.05)


def make_poster(video: Path, at: float, out: Path) -> bool:
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1",
                        "-q:v", "3", str(out)], check=True, timeout=60)
        return out.exists()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


#: STEP 75 §7. Manim writes crf 23 (275–480 kb/s) with a BT.601 matrix and no tags, so HD
#: players decode it as BT.709 and the brand blue lands ΔE ≈ 7 off; its audio sat at −18 LUFS.
LESSON_X264 = ["-c:v", "libx264", "-crf", "14", "-preset", "slow", "-tune", "animation",
               "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
               "-color_trc", "bt709", "-color_range", "tv"]
LESSON_COLOUR = ("scale=in_color_matrix=bt601:in_range=tv:out_color_matrix=bt709:out_range=tv:"
                 "flags=lanczos+accurate_rnd+full_chroma_int,"
                 "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv")
LESSON_RATE = 48000


def final_encode(path: Path) -> dict:
    """One ffmpeg pass over a registered lesson: libx264 crf 14 slow -tune animation, BT.601→709
    with tags, +faststart, audio two-pass loudnorm to −14 LUFS / −1.5 dBTP, AAC 48 kHz 192k.
    The file is replaced only when the pass succeeds and its length matches; any failure
    raises and leaves the original as it was."""
    src_dir = str(HERE.parents[1] / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    import loudness
    import proc
    path = Path(path)
    before = probe_duration(path)
    limit = max(600.0, 3 * (before or 0))
    with tempfile.TemporaryDirectory(dir=str(path.parent), prefix=".encode-") as tmp:
        wav, level, out = Path(tmp) / "a.wav", Path(tmp) / "n.wav", Path(tmp) / "out.mp4"
        proc.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vn", "-c:a", "pcm_s24le", str(wav)],
                 check=True, capture_output=True, timeout=limit)
        report = loudness.loudnorm_two_pass(wav, level, rate=LESSON_RATE, channels=2)
        proc.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-i", str(level), "-map", "0:v:0", "-map", "1:a:0",
                  "-vf", LESSON_COLOUR, *LESSON_X264, "-c:a", "aac", "-b:a", "192k", "-ar", str(LESSON_RATE),
                  "-movflags", "+faststart", str(out)], check=True, capture_output=True, timeout=limit)
        after = probe_duration(out)
        if before is None or after is None or abs(after - before) > 0.1:
            raise RuntimeError(f"final encode changed the length: {before} -> {after}")
        os.replace(out, path)
    return {"loudnorm": report.get("normalization_type"), "output_i": report.get("output_i"),
            "output_tp": report.get("output_tp"), "bytes": path.stat().st_size}


def register(source_mp4: Path, lesson_id: str, voice: str, quality: str, seconds: float,
             studio_dir: Path = HERE, now: Optional[datetime] = None) -> dict:
    """Copy the render, its .srt, the beat timeline, a poster frame and a chapters file into
    renders/<lesson>/ and append one ledger row."""
    folder = studio_dir / "renders" / lesson_id
    folder.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now()
    tl_src = timeline_path(lesson_id, studio_dir)
    look = json.loads(tl_src.read_text(encoding="utf-8")).get("theme") if tl_src.exists() else None
    suffix = f"_{look}" if look else ""
    target = folder / f"{now.strftime('%Y%m%d-%H%M%S')}_{voice}_{QUALITIES[quality][0]}{suffix}.mp4"
    shutil.copyfile(source_mp4, target)
    try:
        encode = final_encode(target)
    except Exception as error:                              # noqa: BLE001 — the copy stays as Manim wrote it
        logging.getLogger(__name__).exception("final encode failed for %s", target)
        encode = {"error": str(error)[:300]}
    srt = source_mp4.with_suffix(".srt")
    if srt.exists():
        shutil.copyfile(srt, target.with_suffix(".srt"))
    duration = probe_duration(target)
    timeline = {}
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
           "chapters": f"{lesson_id}/{target.with_suffix('.chapters.txt').name}" if timeline else None,
           "theme": timeline.get("theme"), "sfx": timeline.get("sfx"),
           "max_cue_lag": (timeline.get("sync") or {}).get("max_lag"),
           "final_encode": encode,
           "gate": lesson_gate(target, timeline),
           **render_features(lesson_id, timeline, studio_dir)}
    with (studio_dir / "renders" / "ledger.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


#: STEP 79 §3: no stretch longer than this without motion (Bubi's breath and the slow push count).
STILL_MAX_S = 5.0
LUFS_TARGET, LUFS_TOLERANCE = -14.0, 1.0


def lesson_gate(mp4: Path, timeline: dict) -> dict:
    """The lesson's gate on a registered render (STEP 79 §3, §5): the sync report, −14 LUFS ± 1
    and no still stretch over STILL_MAX_S. {gate: PASS | REJECT, flags, checks}. The collision
    checker runs on the stills (tools/lesson_stills.py), not on the video."""
    src_dir = str(HERE.parents[1] / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    import loudness
    import stillness
    flags, checks = [], {}
    sync = sync_problems(timeline)
    checks["sync"] = sync
    flags += [f"sync: {line}" for line in sync]
    try:
        level = loudness.measure(mp4)
        checks["lufs"] = round(float(level["I"]), 1)
        if abs(level["I"] - LUFS_TARGET) > LUFS_TOLERANCE:
            flags.append(f"loudness: {level['I']:.1f} LUFS")
    except Exception as error:                              # noqa: BLE001 — unmeasured is a flag, not a pass
        flags.append(f"loudness: not measured ({error})")
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                          "-of", "csv=p=0", str(mp4)], capture_output=True, text=True, timeout=60).stdout.strip().split(",")
    try:
        width, height, rate = int(out[0]), int(out[1]), out[2].split("/")
    except (IndexError, ValueError):
        flags.append("still: the video could not be read")    # unmeasured is a flag, not a pass
    else:
        still = stillness.longest_still(mp4, float(rate[0]) / float(rate[1] if len(rate) > 1 else 1), (width, height))
        checks["still"] = still
        if still["seconds"] > STILL_MAX_S:
            flags.append(f"still: {still['seconds']} s from {still['from']} s")
    return {"gate": "REJECT" if flags else "PASS", "flags": flags, "checks": checks}


def sync_problems(timeline: dict, limit: float = None) -> list:
    """One line per cue whose animation started more than `limit` (lesson.MAX_CUE_LAG) after
    its word — [] when the render is in sync. A render without cue records is a problem too."""
    L = _lesson_module()
    limit = L.MAX_CUE_LAG if limit is None else limit
    if "cues" not in timeline:
        return ["the render recorded no cues (an old scene?) — sync cannot be proved"]
    report = L.sync_report(timeline["cues"], limit)
    return [f"{c['beat']} {c['key']} «{c['word']}»: +{c['start'] - c['cue']:.2f} s after its word" for c in report["late"]]


def render_features(lesson_id: str, timeline: dict, studio_dir: Path = HERE) -> dict:
    """words / beats / pause seconds of the lesson as rendered, and the end card's length,
    so lesson.fit_duration can refit the estimate on every render."""
    path = studio_dir / "lessons" / f"{lesson_id}.json"
    if not path.exists():
        return {}
    L = _lesson_module()
    end = next((b for b in timeline.get("beats", []) if b.get("type") == "end_screen"), None)
    return {**L.features(L.load(path)), "end_s": float(end.get("seconds", 0.0)) if end else 0.0}


def _lesson_module():
    import sys
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import lesson
    return lesson


def duration_fit(studio_dir: Path = HERE) -> dict:
    return _lesson_module().fit_duration(ledger(studio_dir))


def describe_fit(fit: dict) -> str:
    if not fit.get("n"):
        return "duration estimate: no render with features in the ledger yet — using the defaults"
    return (f"duration estimate refit on n = {fit['n']} render(s): {fit['wpm']} wpm "
            f"({fit['seconds_per_word']:.3f} s/word) + {fit['seconds_per_beat']:.2f} s/beat "
            f"[{fit['fitted']}], residuals {fit['residuals_s']} s")


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

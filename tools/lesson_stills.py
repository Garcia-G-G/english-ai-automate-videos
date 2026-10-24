"""STEP 79 §1: one still per beat for every lesson, the layout review's baseline.

    python3 tools/lesson_stills.py OUT_DIR [lesson-id ...]      # default: every lesson

Runs the lesson scene in stills mode (STILLS=1): each beat drawn at its midpoint, recorded timings
where the beat's audio is cached and still matches, estimated ones otherwise. No TTS (the scene's
stills service never asks for voice, and the ElevenLabs lock is on in any case) and nothing is
encoded (Manim --dry_run). Writes OUT_DIR/<lesson>/<nn>_<beat>_<type>.png + stills.json, a
contact sheet OUT_DIR/<lesson>.png and OUT_DIR/index.md.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
STUDIO = ROOT / "experiments" / "manim_voiceover_poc"
VOICE = "english-teacher"
SIZE = ("1280,720", "15")                    # enough to read a caption; a third of 1080p30's work
THUMB = (400, 225)
COLS = 4


def lessons() -> list:
    return sorted(p.stem for p in (STUDIO / "lessons").glob("*.json"))


def run(lesson_id: str, out: Path) -> dict:
    folder = out / lesson_id
    folder.mkdir(parents=True, exist_ok=True)
    voice_dir = STUDIO / "audio" / lesson_id / VOICE
    env = {**os.environ, "STILLS": "1", "STILLS_OUT": str(folder), "LESSON": f"lessons/{lesson_id}.json",
           "TIMELINE_OUT": str(folder / "timeline.json"), "ELEVENLABS_LOCK": "1"}
    if voice_dir.exists():
        env["VOICE_DIR"] = str(voice_dir.relative_to(STUDIO))
    else:
        env.pop("VOICE_DIR", None)
    manim = STUDIO / ".venv" / "bin" / "manim"
    started = time.time()
    log = folder / "manim.log"
    with log.open("w", encoding="utf-8") as fh:
        code = subprocess.run([str(manim), "-r", SIZE[0], "--fps", SIZE[1], "--dry_run", "--disable_caching",
                               "lesson_scene.py", "Lesson"], cwd=str(STUDIO), env=env, stdout=fh,
                              stderr=subprocess.STDOUT).returncode
    index = folder / "stills.json"
    if code != 0 or not index.exists():
        return {"lesson": lesson_id, "error": f"manim exited {code}; see {log.relative_to(out)}",
                "seconds": round(time.time() - started, 1)}
    data = json.loads(index.read_text(encoding="utf-8"))
    data["seconds"] = round(time.time() - started, 1)
    data["voiced"] = voice_dir.exists()
    sheet(folder, data, out / f"{lesson_id}.png")
    return data


def sheet(folder: Path, data: dict, target: Path) -> None:
    stills = data["stills"]
    rows = (len(stills) + COLS - 1) // COLS
    label_h = 26
    img = Image.new("RGB", (COLS * THUMB[0], rows * (THUMB[1] + label_h)), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(str(ROOT / "assets" / "fonts" / "Inter-Bold.ttf"), 16)
    except OSError:
        font = ImageFont.load_default()
    problem_list = [(s["id"], p) for s in stills for p in s.get("problems", [])]
    for k, s in enumerate(stills):
        x, y = (k % COLS) * THUMB[0], (k // COLS) * (THUMB[1] + label_h)
        img.paste(Image.open(folder / s["file"]).convert("RGB").resize(THUMB), (x, y + label_h))
        tag = f"{s['n']:02d} {s['id']} · {s['type']} · {s['t']:.0f} s" + (" · estimado" if s["estimated"] else "")
        d.text((x + 6, y + 4), tag, fill=(180, 40, 30) if s["estimated"] else (30, 30, 30), font=font)
    img.save(target)
    (folder / "problems.txt").write_text("".join(f"{b} {p}\n" for b, p in problem_list), encoding="utf-8")


def write_index(out: Path, results: list) -> None:
    lines = [f"# Lesson stills — {out.name}", "",
             "One still per beat at its midpoint (`tools/lesson_stills.py`, Manim `--dry_run`, 1280×720).",
             "Recorded timings where the beat's audio is cached and matches its narration; estimated",
             "(0.434 s per word plus its pauses) otherwise. No TTS, nothing encoded.", "",
             "| lesson | voiced | beats | estimated beats | layout problems | duration | stills time | sheet |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results:
        if "error" in r:
            lines.append(f"| {r['lesson']} | | | | | | {r['seconds']} s | ERROR: {r['error']} |")
            continue
        problems = sum(len(s.get("problems", [])) for s in r["stills"])
        lines.append(f"| {r['lesson']} | {'yes' if r['voiced'] else 'no'} | {len(r['stills'])} | {len(r['estimated'])} | {problems} | "
                     f"{r['duration']:.0f} s | {r['seconds']} s | [{r['lesson']}.png]({r['lesson']}.png) |")
    (out / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list) -> int:
    if not argv:
        print(__doc__)
        return 2
    out = Path(argv[0]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for lesson_id in argv[1:] or lessons():
        r = run(lesson_id, out)
        results.append(r)
        print(lesson_id, r.get("error") or f"{len(r['stills'])} stills, {len(r['estimated'])} estimated, {r['seconds']} s",
              flush=True)
        write_index(out, results)
    return 1 if any("error" in r for r in results) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

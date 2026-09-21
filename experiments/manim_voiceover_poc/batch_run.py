#!/usr/bin/env python3
"""The automatic path: for each lesson, make the audio (only the beats that changed),
render the video, record it. One command, N finished videos.

    python3 batch_run.py --lessons third-person-s simple-vs-continuous --voices matilda=XrEx… --quality m
    python3 batch_run.py --all --voices matilda=XrEx…                     # every lesson in lessons/
    python3 batch_run.py --all --offline --quality l                      # sandbox voices, draft

Stops at the first failure and says which step of which lesson. gen_audio.py and the
Manim render are subprocesses, so their logs are this program's log.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lesson as L  # noqa: E402
import renders as R  # noqa: E402


def run(argv, env=None):
    print("$ " + " ".join(argv), flush=True)
    full = {**__import__("os").environ, **(env or {})}
    return subprocess.run(argv, cwd=str(HERE), env=full).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lessons", nargs="*", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--voices", default=None, help="name=VOICE_ID[,…]; default matilda")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--quality", default=R.DEFAULT_QUALITY, choices=list(R.QUALITIES))
    parser.add_argument("--model", default=None)
    parser.add_argument("--skip-render", action="store_true", help="audio only")
    parser.add_argument("--force", action="store_true", help="regenerate every beat's audio even if the text did not change")
    args = parser.parse_args()

    ids = sorted(p.stem for p in (HERE / "lessons").glob("*.json")) if args.all else args.lessons
    if not ids:
        sys.exit("No lessons given (--lessons a b or --all).")
    manim_bin = R.manim_binary(HERE)
    if not manim_bin and not args.skip_render:
        sys.exit("manim not found (expected .venv/bin/manim here or manim on PATH).")
    voice_names = ["offline"] if args.offline else [p.split("=", 1)[0] for p in (args.voices or "matilda=x").split(",")]

    started = time.time()
    for lesson_id in ids:
        path = HERE / "lessons" / f"{lesson_id}.json"
        if not path.exists():
            sys.exit(f"{path} does not exist")
        problems = L.validate(L.load(path))
        if problems:
            sys.exit(f"{lesson_id}: not renderable:\n  " + "\n  ".join(problems))
        audio_cmd = [sys.executable, "gen_audio.py", "--lesson", str(path.relative_to(HERE))]
        if args.offline:
            audio_cmd.append("--offline")
        elif args.voices:
            audio_cmd += ["--voices", args.voices]
        if args.model:
            audio_cmd += ["--model", args.model]
        if args.force:
            audio_cmd.append("--force")
        if run(audio_cmd) != 0:
            sys.exit(f"{lesson_id}: audio failed")
        if args.skip_render:
            continue
        for voice in voice_names:
            argv, env = R.render_command(manim_bin, args.quality, lesson_id, voice)
            t0 = time.time()
            if run(argv, env) != 0:
                sys.exit(f"{lesson_id}/{voice}: render failed")
            row = R.register(R.rendered_output(args.quality, HERE), lesson_id, voice, args.quality, time.time() - t0, HERE)
            print(f"✓ {row['file']} — {row['duration_s']} s of video in {row['render_seconds']} s", flush=True)
    print(f"done: {len(ids)} lesson(s) in {time.time() - started:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

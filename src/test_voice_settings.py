#!/usr/bin/env python3
"""
Voice Settings A/B Test — generates the same text with different
ElevenLabs voice configurations so you can compare them by ear.

Usage:
    python src/test_voice_settings.py

Output: output/voice_tests/test_*.mp3  (one per variant)
"""

import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(__file__))

from tts_elevenlabs import generate_segment_audio, DEFAULT_VOICE_ID
from tts_common import get_audio_duration, generate_silence

# ── Test segments ──────────────────────────────────────────────
SEGMENTS = [
    {
        "id": "question",
        "type": "question",
        "text": "¿Qué significa 'awkward' en español?",
        "english_words": {"awkward"},
    },
    {
        "id": "answer",
        "type": "answer",
        "text": "Correcto. La respuesta es A, incómodo.",
        "english_words": set(),
    },
    {
        "id": "explanation",
        "type": "explanation",
        "text": (
            "Awkward significa incómodo o torpe. "
            "No confundas con 'weird' que significa raro. "
            "Son palabras diferentes con significados distintos."
        ),
        "english_words": {"awkward", "weird"},
    },
]

# ── Variants to compare ───────────────────────────────────────
VARIANTS = [
    {
        "name": "current",
        "label": "Current defaults",
        "stability": 0.40,
        "similarity_boost": 0.85,
        "style": 0.15,
        "speed": 0.88,
    },
    {
        "name": "warmer",
        "label": "Warmer / more human",
        "stability": 0.35,
        "similarity_boost": 0.85,
        "style": 0.20,
        "speed": 0.85,
    },
    {
        "name": "teacher",
        "label": "Teacher mode",
        "stability": 0.45,
        "similarity_boost": 0.80,
        "style": 0.10,
        "speed": 0.83,
    },
    {
        "name": "natural",
        "label": "Most natural",
        "stability": 0.30,
        "similarity_boost": 0.75,
        "style": 0.25,
        "speed": 0.87,
    },
]

PAUSE_BETWEEN = 1.0  # seconds of silence between segments
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "voice_tests")


def generate_variant(variant: dict) -> float:
    """Generate all segments for one variant, concatenate, return total duration."""
    name = variant["name"]
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"test_{name}.mp3")

    with tempfile.TemporaryDirectory(prefix=f"vt_{name}_") as tmp:
        audio_files = []

        for i, seg in enumerate(SEGMENTS):
            seg_path = os.path.join(tmp, f"{i}_{seg['id']}.mp3")
            generate_segment_audio(
                text=seg["text"],
                output_path=seg_path,
                voice_id=DEFAULT_VOICE_ID,
                stability=variant["stability"],
                similarity_boost=variant["similarity_boost"],
                style=variant["style"],
                speed=variant["speed"],
                segment_type=seg["type"],
                english_words=seg["english_words"] or None,
            )
            audio_files.append(seg_path)

            # Add pause between segments (not after last)
            if i < len(SEGMENTS) - 1:
                silence_path = os.path.join(tmp, f"pause_{i}.mp3")
                generate_silence(PAUSE_BETWEEN, silence_path)
                audio_files.append(silence_path)

        # Concatenate
        concat_path = os.path.join(tmp, "concat.txt")
        with open(concat_path, "w") as f:
            for p in audio_files:
                f.write(f"file '{p}'\n")

        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_path,
            "-acodec", "libmp3lame", "-q:a", "2",
            "-ar", "44100", "-ac", "1",
            output_path,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg failed for {name}: {r.stderr[:300]}")

    duration = get_audio_duration(output_path)
    return duration


def main():
    print("=" * 65)
    print("  VOICE SETTINGS A/B TEST")
    print(f"  Voice: {DEFAULT_VOICE_ID}")
    print(f"  Output: {os.path.abspath(OUTPUT_DIR)}/")
    print("=" * 65)
    print()

    results = []

    for variant in VARIANTS:
        label = f"{variant['name']} ({variant['label']})"
        print(f"  Generating: {label} ...", end=" ", flush=True)
        t0 = time.time()
        duration = generate_variant(variant)
        elapsed = time.time() - t0
        results.append((variant, duration, elapsed))
        print(f"{duration:.1f}s  (took {elapsed:.0f}s)")

    # Summary table
    print()
    print("=" * 65)
    print(f"  {'Variant':<12} {'Duration':>8}  {'Stab':>5} {'Sim':>5} {'Style':>5} {'Speed':>5}")
    print("-" * 65)
    for variant, duration, _ in results:
        print(
            f"  {variant['name']:<12} {duration:>7.1f}s"
            f"  {variant['stability']:>5.2f}"
            f"  {variant['similarity_boost']:>5.2f}"
            f"  {variant['style']:>5.2f}"
            f"  {variant['speed']:>5.2f}"
        )
    print("-" * 65)
    print(f"  Files saved to: {os.path.abspath(OUTPUT_DIR)}/")
    print()


if __name__ == "__main__":
    main()

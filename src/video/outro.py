"""Pre-rendered Learning Routes outro, and the concat that appends it.

RENDERED ONCE PER VARIANT, EVER. The clip lives in assets/outro/<id>.mp4 and
is reused by every video that draws that variant. Selection is per video;
synthesis is not. Any implementation that calls TTS per video is wrong — a
~40-character line is about $0.009, which is nothing once and real money at
scale, and re-synthesising also means the voice drifts between videos.

It is rendered through the SAME compositor as the main video
(video/compositor.render_video_ffmpeg), so resolution, fps, codec, pixel
format and audio parameters match by construction. That is what lets the
concat use `-c copy` with no re-encode; building the outro any other way
risks a parameter mismatch that either fails the concat or silently forces a
quality-losing re-encode.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from .compositor import render_video_ffmpeg
from .constants import FPS, VIDEO_HEIGHT, VIDEO_WIDTH
from .utils import instrument_serif_italic, manrope

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
OUTRO_CONFIG = ROOT / "src" / "config" / "outro.json"
OUTRO_DIR = ROOT / "assets" / "outro"

OUTRO_DURATION = 4.0

#: Learning Routes brand background.
BG_COLOR = (15, 14, 13)            # #0F0E0D
HEADING_COLOR = (247, 245, 240)
URL_COLOR = (255, 255, 255)
ACCENT_COLOR = (198, 168, 106)     # warm rule under the URL

HEADING_SIZE = 76                  # Instrument Serif italic, the LR heading face
URL_SIZE = 62                      # Manrope, the LR body face

FADE_IN = 0.35
FADE_OUT = 0.35


# ── copy ─────────────────────────────────────────────────────────────

def load_variants() -> Dict:
    return json.loads(OUTRO_CONFIG.read_text(encoding="utf-8"))


def select_variant(seed: Optional[str] = None) -> Dict:
    """Weighted choice among variants. `seed` makes it reproducible per video.

    Weights are relative, not percentages, and a weight of 0 retires a variant
    without renumbering the others.
    """
    cfg = load_variants()
    live = [v for v in cfg["variants"] if v.get("weight", 0) > 0]
    if not live:
        raise ValueError("no outro variant has a non-zero weight")

    rng = random.Random(seed) if seed is not None else random
    chosen = rng.choices(live, weights=[v["weight"] for v in live], k=1)[0]
    logger.info("outro variant: %s (weight %s of %s)", chosen["id"],
                chosen["weight"], sum(v["weight"] for v in live))
    return chosen


# ── frames ───────────────────────────────────────────────────────────

def _make_frame_fn(variant: Dict):
    heading = instrument_serif_italic(HEADING_SIZE)
    url_font = manrope(URL_SIZE, "Bold")

    base = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(base)

    l1, l2 = variant["line_1"], variant["line_2"]
    b1 = draw.textbbox((0, 0), l1, font=heading)
    b2 = draw.textbbox((0, 0), l2, font=url_font)

    total_h = (b1[3] - b1[1]) + 46 + (b2[3] - b2[1])
    y = VIDEO_HEIGHT // 2 - total_h // 2 - 40

    draw.text(((VIDEO_WIDTH - (b1[2] - b1[0])) // 2 - b1[0], y - b1[1]),
              l1, font=heading, fill=HEADING_COLOR)

    y2 = y + (b1[3] - b1[1]) + 46
    draw.text(((VIDEO_WIDTH - (b2[2] - b2[0])) // 2 - b2[0], y2 - b2[1]),
              l2, font=url_font, fill=URL_COLOR)

    rule_w = int((b2[2] - b2[0]) * 0.42)
    rule_y = y2 + (b2[3] - b2[1]) + 34
    draw.rounded_rectangle(
        [(VIDEO_WIDTH - rule_w) // 2, rule_y, (VIDEO_WIDTH + rule_w) // 2, rule_y + 5],
        radius=3, fill=ACCENT_COLOR)

    still = np.array(base, dtype=np.uint8)
    bg = np.array(BG_COLOR, dtype=np.float32)

    def frame_at(t: float) -> np.ndarray:
        # Fade from and to the brand background rather than to black, so the
        # join with the main video and the end of the clip are both clean.
        k = 1.0
        if t < FADE_IN:
            k = t / FADE_IN
        elif t > OUTRO_DURATION - FADE_OUT:
            k = max(0.0, (OUTRO_DURATION - t) / FADE_OUT)
        if k >= 0.999:
            return still
        return (bg + (still.astype(np.float32) - bg) * k).astype(np.uint8)

    return frame_at


# ── audio ────────────────────────────────────────────────────────────

def _synthesize(variant: Dict, out_path: Path) -> None:
    """One TTS call, the same ElevenLabs voice as the narration."""
    from tts_elevenlabs import generate_segment_audio

    logger.info("outro TTS (ONE TIME for variant %s): %r",
                variant["id"], variant["spoken"])
    generate_segment_audio(
        text=variant["spoken"],
        output_path=str(out_path),
        voice_id=None,             # module default = the narration voice
        segment_type="explanation",
    )


# ── build / cache ────────────────────────────────────────────────────

def outro_path(variant_id: str) -> Path:
    return OUTRO_DIR / f"{variant_id}.mp4"


def ensure_outro(variant: Dict, force: bool = False) -> Path:
    """Return the cached clip, rendering it only if absent.

    THE CACHE IS THE POINT. A hit costs one stat() call and zero API spend.
    """
    path = outro_path(variant["id"])
    if path.exists() and not force:
        logger.info("outro: cache HIT %s (no TTS, no render)", path.name)
        return path

    logger.info("outro: cache MISS for %s — rendering once", variant["id"])
    OUTRO_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        voice = Path(tmp) / "outro_voice.mp3"
        _synthesize(variant, voice)

        # Pad the voice to the full clip length so the audio stream is exactly
        # as long as the video. A short audio stream under -shortest would
        # truncate the video instead.
        padded = Path(tmp) / "outro_audio.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(voice),
             "-af", f"apad=whole_dur={OUTRO_DURATION}",
             "-t", str(OUTRO_DURATION), str(padded)],
            check=True, capture_output=True,
        )

        render_video_ffmpeg(
            frame_generator=_make_frame_fn(variant),
            audio_path=str(padded),
            output_path=str(path),
            duration=OUTRO_DURATION,
            fps=FPS,
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
        )

    logger.info("outro rendered once -> %s", path)
    return path


# ── concat ───────────────────────────────────────────────────────────

def _probe_params(path: str) -> Dict:
    """Codec/format parameters that must match for `-c copy` to be legal."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_name,width,height,r_frame_rate,pix_fmt,sample_rate,channels",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    streams = json.loads(out.stdout).get("streams", [])
    params = {}
    for s in streams:
        if "width" in s:
            params["video"] = (s.get("codec_name"), s.get("width"), s.get("height"),
                               s.get("r_frame_rate"), s.get("pix_fmt"))
        else:
            params["audio"] = (s.get("codec_name"), s.get("sample_rate"),
                               s.get("channels"))
    return params


def append_outro(video_path: str, variant: Dict,
                 output_path: Optional[str] = None) -> str:
    """Concatenate the cached outro onto `video_path` with no re-encode.

    Verifies the stream parameters match first. They should, because both
    clips came out of the same compositor — but a mismatch silently forcing a
    re-encode is exactly the kind of quality loss nobody notices, so it is
    checked rather than assumed.
    """
    outro = ensure_outro(variant)
    main_p, outro_p = _probe_params(video_path), _probe_params(str(outro))

    if main_p != outro_p:
        raise RuntimeError(
            "outro stream parameters differ from the main video, so `-c copy` "
            f"would be unsafe.\n  main : {main_p}\n  outro: {outro_p}"
        )

    output_path = output_path or video_path.replace(".mp4", "_with_outro.mp4")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write(f"file '{os.path.abspath(video_path)}'\n")
        fh.write(f"file '{os.path.abspath(outro)}'\n")
        list_path = fh.name

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", list_path, "-c", "copy", output_path],
            check=True, capture_output=True,
        )
    finally:
        os.unlink(list_path)

    logger.info("outro appended (variant=%s, -c copy) -> %s",
                variant["id"], output_path)
    return output_path


def measure_seam(joined_path: str, seam_t: float) -> Dict:
    """Measure the audio gap at the concat boundary, in ms.

    Concatenating separately-encoded audio can leave a gap or a click at the
    join — the same LAME padding class found in Step 3. Uses the QA gate's own
    silence detector so the number is comparable with everything else measured
    in this project.
    """
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from qa_gate import silence_regions

    spans, _duration = silence_regions(joined_path)
    covering = [(s, e) for s, e in spans if s <= seam_t <= e]
    nearest = min(spans, key=lambda se: min(abs(se[0] - seam_t),
                                            abs(se[1] - seam_t))) if spans else None

    gap_ms = round((covering[0][1] - covering[0][0]) * 1000, 1) if covering else 0.0
    return {
        "seam_s": round(seam_t, 3),
        "silence_spans_at_seam": [[round(s, 3), round(e, 3)] for s, e in covering],
        "gap_ms": gap_ms,
        "nearest_silence": [round(nearest[0], 3), round(nearest[1], 3)] if nearest else None,
    }

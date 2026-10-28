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
import shutil
import subprocess
import proc
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from .compositor import render_video_ffmpeg
from .constants import FPS, VIDEO_HEIGHT, VIDEO_WIDTH

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
OUTRO_CONFIG = ROOT / "src" / "config" / "outro.json"
OUTRO_DIR = ROOT / "assets" / "outro"

OUTRO_DURATION = 4.0

#: STEP 62 §4: the brand sticker card on sand. Colours and faces come from brand.json.
#: STEP 71 (brand v3, mock_cierre_short.png): Bubi waving stands on the card's top edge.
SYMBOL = ROOT / "assets" / "branding" / "english-unlimited" / "simbolo_512.png"
CARD_W, CARD_H = 784, 520           # STEP 80 §6: x 148-932, clear of the Shorts button rail (x > 940)
CARD_RADIUS = 30
CARD_OUTLINE = 7
CARD_DY = 60                       # the card's centre sits this far below the frame's
SYMBOL_PX = 440                    # Bubi's drawn width (his visible pixels, arm and badge included)
SYMBOL_OVERLAP = 70                # how far his body comes down over the card's top edge
LEAD_SIZE = 64                     # «Aprende inglés en», Fredoka medium, ink
URL_SIZE = 96                      # learningroutes.com, Fredoka bold, English blue
SUB_SIZE = 40                      # the site's line, Fredoka medium, muted
MARKER_H = 30                      # the yellow stroke under the URL's lower half

FADE_OUT = 0.35
#: STEP 77 §3: the card comes up from below with an overshoot as the page leaves the Short,
#: and Bubi waves: two poses, tilted either way about his feet, swapped every WAVE_STEP.
ENTER = 0.5
ENTER_FROM = 520
WAVE_STEP = 0.2
WAVE_SWINGS = 6
WAVE_DEG = 6.0

#: STEP 80 §6: the v3 logo's wordmark over Bubi, the next step from the queue, «Link en la bio».
LOGO = ROOT / "assets" / "branding" / "english-unlimited" / "logo_horizontal.png"
WORDMARK_FROM_X = 520              # logo_horizontal: Bubi left of this x, «English Unlimited» right
WORDMARK_W, WORDMARK_TOP = 560, 190
NEXT_TOP, NEXT_W = 350, 760        # «Mañana:» and the next topic, ending above Bubi's head (~y 535)
FOLLOW = "Síguenos para el siguiente"
LINK = "Link en la bio"
_ARTICLES = ("los ", "las ", "el ", "la ")


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


# ── the next step (STEP 80 §6) ───────────────────────────────────────

def _next_phrase(video_type: str, script: Dict) -> str:
    """How the next script is announced: «¿Cómo se dicen los ANIMALES DEL MAR? 🐬»."""
    theme = str(script.get("theme") or "").split(" (")[0].strip()
    if video_type == "how_do_you_say" and theme:
        article = next((a for a in _ARTICLES if theme.lower().startswith(a)), "")
        verb = "dicen" if article in ("los ", "las ") else "dice"
        items = script.get("items") or []
        emoji = str(items[0].get("emoji") or "") if items else ""
        return f"¿Cómo se {verb} {article}{theme[len(article):].upper()}? {emoji}".strip()
    if video_type == "hecho_con_claude":
        title = str(script.get("title") or "")
        return title.split(":", 1)[1].strip() if title.upper().startswith("RETO:") else title
    return theme.upper()


def next_step(video_type: str, script: Dict) -> str:
    """«Mañana: …» from the queue's next script of the same type (another topic), or FOLLOW."""
    try:
        if video_type == "hecho_con_claude":
            import series
            paths = series.queued(script.get("style"))
        else:
            import queue_priority
            import topic_history
            root = topic_history.QUEUE_DIR
            paths = [p for p in sorted(root.rglob("*.json"))
                     if not {"_done", "_skipped", "hecho_con_claude"} & set(p.relative_to(root).parts[:-1])]
            paths = [p for p, _pr, _why in queue_priority.ranked(paths)]
        for path in paths:
            other = json.loads(Path(path).read_text(encoding="utf-8"))
            if (other.get("type") or video_type) != video_type or other.get("id", 0) == script.get("id", 1):
                continue
            if other.get("theme") and other.get("theme") == script.get("theme"):
                continue
            phrase = _next_phrase(video_type, other)
            if phrase:
                return f"Mañana: {phrase}"
    except Exception:                                       # noqa: BLE001 — no queue: the plain line
        logger.debug("outro: no next step", exc_info=True)
    return FOLLOW


def _wordmark() -> Image.Image:
    logo = Image.open(LOGO).convert("RGBA")
    part = logo.crop((WORDMARK_FROM_X, 0, logo.width, logo.height))
    part = part.crop(part.getchannel("A").getbbox())
    return part.resize((WORDMARK_W, round(part.height * WORDMARK_W / part.width)), Image.LANCZOS)


def draw_top(img: Image.Image, next_line: Optional[str]) -> None:
    """The wordmark, then «Mañana:» and the next topic (its emoji drawn as art), or FOLLOW."""
    from .notebook import kit
    from .series import series_kit as K
    mark = _wordmark()
    img.alpha_composite(mark, ((VIDEO_WIDTH - mark.width) // 2, WORDMARK_TOP))
    ink, muted = _brand_colour("ink"), _brand_colour("secondary_text")
    line = (next_line or FOLLOW).strip()
    if not line.startswith("Mañana:"):
        size, lines = K.fit(line, "fredoka", NEXT_W, 52, 36, 1)
        K.text_block(img, lines, "fredoka", size, 0, NEXT_TOP + 50, ink, "center", VIDEO_WIDTH)
        return
    text = line[len("Mañana:"):].strip()
    emoji = ""
    if text and ord(text[-1]) > 0x2000 and not text[-1].isalnum() and text[-1] not in "?!.»":
        text, emoji = text[:-1].rstrip(), text[-1]
    K.text_block(img, ["Mañana:"], "fredoka_medium", 36, 0, NEXT_TOP, muted, "center", VIDEO_WIDTH)
    size, lines = K.fit(text, "fredoka", NEXT_W - (60 if emoji else 0), 50, 34, 2)
    box = K.text_block(img, list(lines), "fredoka", size, 0, NEXT_TOP + 50, ink, "center", VIDEO_WIDTH)
    if emoji:
        try:
            art = kit.emoji(emoji, size)
            last_w = K.block_box([lines[-1]], "fredoka", size, 0, 0, "center", VIDEO_WIDTH)
            img.alpha_composite(art, (int(last_w[2] + 12), int(box[3] - size * 0.95)))
        except Exception:                                   # noqa: BLE001 — an emoji without art: none
            logger.debug("outro: no art for %r", emoji)


# ── frames ───────────────────────────────────────────────────────────

def _brand_colour(name: str) -> Tuple[int, int, int]:
    from .how_do_you_say import brand
    value = brand()["color"].get(name) or brand()["manim"]["themes"]["sand"][name]
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def _sand() -> Tuple[int, int, int]:
    from .how_do_you_say import brand
    value = brand()["manim"]["themes"]["sand"]["bg"]
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def outro_still(variant: Dict, next_line: Optional[str] = None) -> Image.Image:
    """The card at rest: «line_1» in ink, line_2 big in English blue over a yellow marker
    stroke, outro.json's `line_3` small and muted, the symbol on the top edge."""
    card, bubi, at = outro_layers(variant, next_line)
    img = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (*_sand(), 255))
    img.alpha_composite(card)
    img.alpha_composite(bubi, at)
    return img.convert("RGB")


def outro_layers(variant: Dict, next_line: Optional[str] = None) -> Tuple[Image.Image, Image.Image, Tuple[int, int]]:
    """(the card and its text on a transparent frame, Bubi, where Bubi stands)."""
    from .how_do_you_say import fredoka
    ink, blue, yellow = _brand_colour("ink"), _brand_colour("english_blue"), _brand_colour("brand_yellow")
    from .notebook import kit
    muted = _brand_colour("secondary_text")
    x0, y0 = (VIDEO_WIDTH - CARD_W) // 2, (VIDEO_HEIGHT - CARD_H) // 2 + CARD_DY
    # The notebook kit's card, in the page's one paper colour (STEP 77 §1).
    img = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    kit.page(img, x0, y0, CARD_W, CARD_H, CARD_RADIUS, CARD_OUTLINE, (8, 8), fill=kit.PAPER)
    draw = ImageDraw.Draw(img)

    def centred(text, font, cy, fill):
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((VIDEO_WIDTH - (box[2] - box[0])) // 2 - box[0], cy - (box[1] + box[3]) // 2),
                  text, font=font, fill=fill)
        return box

    lead = fredoka(LEAD_SIZE, "display_medium")
    url = fredoka(URL_SIZE)
    while draw.textlength(variant["line_2"], font=url) > CARD_W - 100:
        url = fredoka(url.size - 4)
    centred(variant["line_1"], lead, y0 + 135, ink)
    ucy = y0 + 262
    w = draw.textlength(variant["line_2"], font=url)
    draw.rounded_rectangle([(VIDEO_WIDTH - w) // 2 - 8, ucy + 2, (VIDEO_WIDTH + w) // 2 + 8, ucy + 2 + MARKER_H],
                           radius=MARKER_H // 2, fill=yellow)
    centred(variant["line_2"], url, ucy, blue)
    sub = load_variants().get("line_3")
    if sub:
        centred(sub, fredoka(SUB_SIZE, "display_medium"), y0 + 370, muted)
    centred(LINK, fredoka(32, "display_medium"), y0 + 448, blue)
    draw_top(img, next_line)
    symbol = Image.open(SYMBOL).convert("RGBA")
    symbol = symbol.crop(symbol.getchannel("A").getbbox())          # his pixels, not the canvas
    symbol = symbol.resize((SYMBOL_PX, round(symbol.height * SYMBOL_PX / symbol.width)), Image.LANCZOS)
    return img, symbol, ((VIDEO_WIDTH - SYMBOL_PX) // 2, y0 + SYMBOL_OVERLAP - symbol.height)


def wave_pose(t: float) -> int:
    """Bubi's pose at t: 0 at rest, +1 / -1 while he waves (after the card lands)."""
    k = int((t - ENTER) // WAVE_STEP)
    if t < ENTER or k >= WAVE_SWINGS:
        return 0
    return 1 if k % 2 == 0 else -1


def card_dy(t: float) -> int:
    from .motion import ease_out_back
    return int(round(ENTER_FROM * (1.0 - ease_out_back(t / ENTER)))) if t < ENTER else 0


def _make_frame_fn(variant: Dict, next_line: Optional[str] = None):
    from .notebook import kit
    card, bubi, (bx, by) = outro_layers(variant, next_line)
    # a pose tilts him about his feet; the canvas grows so the tilt never clips him
    poses = {0: (bubi, bx, by)}
    for sign in (1, -1):
        r = bubi.rotate(sign * WAVE_DEG, resample=Image.BICUBIC, expand=True,
                        center=(bubi.width / 2, bubi.height))
        poses[sign] = (r, bx - (r.width - bubi.width) // 2, by - (r.height - bubi.height))
    sand = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (*_sand(), 255))
    bg = np.array(_sand(), dtype=np.float32)

    def frame_at(t: float) -> np.ndarray:
        img = sand.copy()
        dy = card_dy(t)
        kit._composite_clipped(img, card, 0, dy)
        b, x, y = poses[wave_pose(t)]
        kit._composite_clipped(img, b, x, y + dy)
        out = np.array(img.convert("RGB"))
        # fade to the sand background at the end, so the clip's end is clean
        if t > OUTRO_DURATION - FADE_OUT:
            k = max(0.0, (OUTRO_DURATION - t) / FADE_OUT)
            out = (bg + (out.astype(np.float32) - bg) * k).astype(np.uint8)
        return out

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
        voice = Path(tmp) / "outro_voice.m4a"
        if path.exists():
            # A redraw (force=True) keeps the voice the clip already has: the same
            # `spoken`, $0 (STEP 62 §4). Only a missing clip asks the TTS. After editing
            # a variant's `spoken`, delete assets/outro/<id>.mp4 to get the new voice
            # (one TTS call); force=True alone keeps the old one.
            proc.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-vn", "-c:a", "copy",
                            str(voice)], check=True, capture_output=True, timeout=proc.FFMPEG)
            logger.info("outro: redraw of %s keeps its voice, no TTS", variant["id"])
        else:
            voice = voice.with_suffix(".mp3")
            _synthesize(variant, voice)

        # STEP 75 §5: the outro speaks at the narration's −14 LUFS, so the seam has no jump.
        import loudness
        level = Path(tmp) / "outro_voice.wav"
        loudness.loudnorm_two_pass(voice, level)

        # Pad the voice to the full clip length so the audio stream is exactly
        # as long as the video. A short audio stream under -shortest would
        # truncate the video instead.
        padded = Path(tmp) / "outro_audio.wav"
        proc.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(level),
             "-af", f"apad=whole_dur={OUTRO_DURATION}",
             "-t", str(OUTRO_DURATION), str(padded)],
            check=True, capture_output=True, timeout=proc.FFMPEG
        )

        # Rendered in tmp and moved in only when complete: a cut render must never
        # become a cached clip, since a cache hit is never checked again (STEP 73 §0).
        rendered = Path(tmp) / "outro_new.mp4"
        render_video_ffmpeg(
            frame_generator=_make_frame_fn(variant),
            audio_path=str(padded),
            output_path=str(rendered),
            duration=OUTRO_DURATION,
            fps=FPS,
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
        )
        # tmp may be another volume: copy next to the clip first, then an atomic rename.
        part = path.with_name(f".{path.name}.part")
        shutil.move(str(rendered), str(part))
        os.replace(part, path)

    logger.info("outro rendered once -> %s", path)
    return path


# ── concat ───────────────────────────────────────────────────────────

def _probe_params(path: str) -> Dict:
    """Codec/format parameters that must match for `-c copy` to be legal."""
    out = proc.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_name,width,height,r_frame_rate,pix_fmt,sample_rate,channels",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True, timeout=proc.FFPROBE
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


def outro_for(variant: Dict, next_line: str, out_path: Path) -> Path:
    """STEP 80 §6: this video's outro — the card with its «Mañana: …» line, over the variant's
    cached voice (no TTS, $0), through the same compositor so the concat stays `-c copy`."""
    cached = ensure_outro(variant)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "outro_voice.wav"
        proc.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(cached), "-vn", str(wav)],
                 check=True, capture_output=True, timeout=proc.FFMPEG)
        render_video_ffmpeg(frame_generator=_make_frame_fn(variant, next_line), audio_path=str(wav),
                            output_path=str(out_path), duration=OUTRO_DURATION, fps=FPS,
                            width=VIDEO_WIDTH, height=VIDEO_HEIGHT)
    return Path(out_path)


def append_outro(video_path: str, variant: Dict,
                 output_path: Optional[str] = None, next_line: Optional[str] = None) -> str:
    """Concatenate the cached outro onto `video_path` with no re-encode.

    Verifies the stream parameters match first. They should, because both
    clips came out of the same compositor — but a mismatch silently forcing a
    re-encode is exactly the kind of quality loss nobody notices, so it is
    checked rather than assumed.
    """
    own = None
    if next_line and next_line != FOLLOW:                   # the cached clip already says FOLLOW
        own = Path(tempfile.mkdtemp()) / "outro_own.mp4"
        outro = outro_for(variant, next_line, own)
    else:
        outro = ensure_outro(variant)
    try:
        return _concat(video_path, outro, variant, output_path)
    finally:
        if own is not None:
            shutil.rmtree(own.parent, ignore_errors=True)


def _concat(video_path: str, outro: Path, variant: Dict, output_path: Optional[str]) -> str:
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
        proc.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", list_path, "-c", "copy", "-movflags", "+faststart", output_path],
            check=True, capture_output=True, timeout=proc.FFMPEG
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

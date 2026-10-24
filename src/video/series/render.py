"""Render one «Hecho con Claude» Short (STEP 78 §2): voice → beats → the style's frames → the
outro card with the challenge's answer, through the STEP 77 machinery (frame pool, x264 medium,
BT.709, −14 LUFS, the procedural sounds, the Bubi outro).

    render_series(script, out_mp4, work_dir)                    the real thing (TTS, cached)
    render_series(script, out_mp4, work_dir, silent=True,
                  seconds=2.0)                                   a smoke clip: estimated beats,
                                                                 silent audio, no TTS spend

A style is a module of this package with
    frame(t, script, timeline) -> PIL RGBA 1080×1920   (t inside the voice)
    sfx_events(script, timeline) -> [(name, start, length)]
    text_boxes(script) -> [(label, box)]                 every readable box at its final state
"""
from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Dict, Optional

import numpy as np

from . import beats as B
from . import series_kit as K

STYLE_MODULES = {"mensajes": "mensajes", "escena": "escena", "poster": "poster", "comic": "comic"}
#: Estimated speech for smoke clips: characters a second, and the pause between lines.
EST_CPS, EST_GAP = 14.0, 0.35


def style_module(style: str):
    return importlib.import_module(f"video.series.{STYLE_MODULES[style]}")


def estimated_timeline(script: Dict) -> Dict:
    """Beats from text length alone (smoke clips and tests): never presented as measured."""
    t, beats = 0.2, []
    for k, line in enumerate(script["voice"]):
        plain = re.sub(r"\[\[|\]\]", "", line)
        dur = max(0.8, len(plain) / EST_CPS)
        english, cursor = [], 0
        for m in re.finditer(r"\[\[(.+?)\]\]", line):
            pos = len(re.sub(r"\[\[|\]\]", "", line[:m.start()]))
            a = t + dur * pos / max(1, len(plain))
            english.append({"text": m.group(1), "start": round(a, 3),
                            "end": round(a + dur * len(m.group(1)) / max(1, len(plain)), 3)})
        toks = plain.split()
        words = [{"word": w, "start": round(t + dur * j / len(toks), 3), "end": round(t + dur * (j + 0.9) / len(toks), 3)}
                 for j, w in enumerate(toks)]
        beats.append({"i": k, "text": line, "start": round(t, 3), "end": round(t + dur, 3), "english": english,
                      "words": words})
        t += dur + EST_GAP
    tl = {"beats": beats, "duration": round(t, 3), "countdown": None, "estimated": True}
    after = B.countdown_line(script)
    if after is not None:
        rate = 100
        tl, _ = B.insert_countdown(tl, np.zeros(int(tl["duration"] * rate) + 1), rate, after)
    return tl


def render_series(script: Dict, out_mp4, work_dir, *, silent: bool = False, seconds: Optional[float] = None,
                  variant: Optional[Dict] = None, workers: Optional[int] = None) -> Dict:
    """Render `script` to out_mp4. Returns {"duration", "voice_seconds", "tts_usd", "timeline", …}."""
    import loudness
    from video import outro as O
    from video.compositor import render_workers, render_video_ffmpeg
    from video.notebook import sfx as SFX

    out_mp4, work_dir = Path(out_mp4), Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    style = style_module(script["style"])
    rate = loudness.RATE

    # 1. the voice and its beats
    if silent:
        tl = estimated_timeline(script)
        narration = np.zeros(int(round(tl["duration"] * rate)))
        tts_usd = 0.0
    else:
        tl = B.voice_timeline(script, work_dir)
        tts_usd = tl.get("tts_usd", 0.0)
        data_json = work_dir / f"{script['id']}.segments.json"
        data_json.write_text(json.dumps({"segments": [
            {"id": f"beat_{b['i']}", "start": b["start"], "end": b["end"], "text": b["text"]} for b in tl["beats"]]}),
            encoding="utf-8")
        levelled = work_dir / f"{script['id']}.narration.wav"
        loudness.prepare_narration(tl["audio"], data_json, levelled)     # −14 LUFS, segments levelled
        narration = loudness.decode(levelled)
    voice_s = narration.size / rate

    # 2. the style's sounds, under the voice
    spoken = [(b["start"], b["end"]) for b in tl["beats"]]
    if not silent:
        narration, _placed = SFX.mix(narration, rate, style.sfx_events(script, tl), spoken)

    # 3. the outro: its own voice (cached, −14 LUFS), the card, the answer
    variant = variant or O.select_variant(seed=script["id"])
    outro_audio = loudness.decode(O.ensure_outro(variant)) if not silent else np.zeros(int(O.OUTRO_DURATION * rate))
    audio = np.concatenate([narration, outro_audio[:int(O.OUTRO_DURATION * rate)]])
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0.999:
        audio *= 0.999 / peak
    total = voice_s + O.OUTRO_DURATION
    duration = min(total, seconds) if seconds else total
    audio = audio[:int(round(duration * rate))]
    wav = work_dir / f"{script['id']}.mix.wav"
    loudness._write_wav(audio, wav)

    answer = script["challenge"]["answer"]

    def frame_at(t: float) -> np.ndarray:
        if t < voice_s:
            return np.asarray(style.frame(t, script, tl).convert("RGB"))
        return K.outro_frame(t - voice_s, variant, answer)

    render_video_ffmpeg(frame_at, str(wav), str(out_mp4), duration,
                        workers=workers if workers is not None else render_workers())
    info = {"id": script["id"], "style": script["style"], "level": script["level"],
            "duration": round(duration, 3), "voice_seconds": round(voice_s, 3), "tts_usd": tts_usd,
            "outro_variant": variant["id"], "timeline": tl, "silent": silent}
    out_mp4.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info

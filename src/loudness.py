"""Narration loudness for Shorts: even segments, then −14 LUFS (STEP 75 §5).

The cached narration is many TTS calls joined end to end, and each call comes back at
its own level: the §0 baseline sat at −15.5 LUFS with a −0.4 dBTP peak, and a quiet
Spanish line next to a loud English one is the jump a listener hears. So, before the mux:

  1. each spoken segment (the audio JSON's `segments`, «[silence]» skipped) is brought to
     the median level of the segments, clamped ±6 dB, with 10 ms ramps at its edges
     (the logic of experiments/manim_voiceover_poc/gen_audio.level_match, applied to the
     segment spans of the joined file so cached narrations get it too);
  2. a two-pass loudnorm to −14 LUFS / −1.5 dBTP / LRA 7.

Nothing moves in time: the result has the input's sample count, so every word timestamp
stays right (asserted). The cached mp3 is never rewritten; this writes a new file.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

import proc

logger = logging.getLogger(__name__)

RATE = 44100                    # the outros and every narration are 44.1 kHz; -c copy needs a match
TARGET_I, TARGET_TP, TARGET_LRA = -14.0, -1.5, 7.0
MAX_GAIN_DB = 6.0
SILENT_DB = -50.0               # a segment quieter than this is silence, not speech
RAMP_S = 0.010
#: A sample limiter at 4× the rate sees (nearly) the true peak. The sample-peak limiter
#: before loudnorm left inter-sample overs at −0.5 dBTP; −2.5 dBFS leaves room for the AAC
#: encode, which added ~1 dB on a 48 kHz stereo lesson (−1.1 dBTP at a −2 dBFS guard).
TRUE_PEAK_CEILING = 0.7499                                                   # −2.5 dBFS


def true_peak_guard(rate: int) -> str:
    return (f"aresample={4 * rate}:filter_size=64,"
            f"alimiter=limit={TRUE_PEAK_CEILING}:level=false:attack=0.5:release=40:latency=true")


def decode(path) -> np.ndarray:
    raw = proc.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(RATE),
                    "-f", "f32le", "-"], capture_output=True, check=True, timeout=proc.FFMPEG).stdout
    return np.frombuffer(raw, "<f4").astype(np.float64)


def _db(x: np.ndarray) -> float:
    """Gated RMS dB: the 20 ms frames that carry speech, so a pause inside a line does not
    make the line read quieter than it sounds."""
    frame = int(0.02 * RATE)
    n = x.size // frame
    if not n:
        return -120.0
    power = np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1)
    frames_db = 10 * np.log10(np.maximum(power, 1e-12))
    loud = power[frames_db > SILENT_DB]
    if not loud.size:
        return -120.0
    return float(10 * np.log10(np.mean(loud)))


def speech_spans(segments: List[Dict], n_samples: int) -> List[tuple]:
    """(id, first sample, last sample) of each spoken segment."""
    spans = []
    for seg in segments or []:
        if "[silence]" in str(seg.get("text", "")):
            continue
        a, b = int(round(float(seg.get("start", 0)) * RATE)), int(round(float(seg.get("end", 0)) * RATE))
        a, b = max(0, a), min(n_samples, b)
        if b - a >= int(0.15 * RATE):
            spans.append((seg.get("id", "?"), a, b))
    return spans


def segment_levels(samples: np.ndarray, segments: List[Dict]) -> Dict[str, float]:
    """RMS dB of each spoken segment (silent ones left out)."""
    out = {}
    for sid, a, b in speech_spans(segments, samples.size):
        level = _db(samples[a:b])
        if level > SILENT_DB:
            out[sid] = round(level, 2)
    return out


def spread(levels: Dict[str, float]) -> float:
    return round(max(levels.values()) - min(levels.values()), 2) if levels else 0.0


def level_segments(samples: np.ndarray, segments: List[Dict]) -> tuple:
    """Each spoken segment to the median level, ±MAX_GAIN_DB. Returns (samples, {id: gain dB})."""
    levels = segment_levels(samples, segments)
    if not levels:
        return samples, {}
    target = float(np.median(list(levels.values())))
    gain = np.ones_like(samples)
    ramp = int(RAMP_S * RATE)
    gains = {}
    for sid, a, b in speech_spans(segments, samples.size):
        if sid not in levels:
            continue
        g_db = max(-MAX_GAIN_DB, min(MAX_GAIN_DB, target - levels[sid]))
        gains[sid] = round(g_db, 2)
        g = 10 ** (g_db / 20)
        env = np.full(b - a, g)
        r = min(ramp, (b - a) // 2)
        if r:
            env[:r] = np.linspace(1.0, g, r)
            env[-r:] = np.linspace(g, 1.0, r)
        gain[a:b] = env
    return samples * gain, gains


def _write_wav(samples: np.ndarray, path: Path) -> None:
    proc.run(["ffmpeg", "-v", "error", "-y", "-f", "f64le", "-ar", str(RATE), "-ac", "1", "-i", "-",
              "-c:a", "pcm_s24le", str(path)], input=samples.astype("<f8").tobytes(), check=True,
             capture_output=True, timeout=proc.FFMPEG)


def _loudnorm_json(stderr: str) -> Dict:
    block = stderr[stderr.rfind("{"):stderr.rfind("}") + 1]
    return json.loads(block)


def loudnorm_two_pass(src: Path, dst: Path, rate: int = RATE, channels: int = 1) -> Dict:
    """Two-pass loudnorm, linear. Returns pass 2's report.

    loudnorm only stays linear when the gain it needs leaves the peak under TP; TTS peaks
    sit near 0 dBFS, so it fell back to «dynamic» (gain riding, which re-opens the segment
    spread). A limiter first caps the peaks where the gain will put them under −1.5 dBTP."""
    spec = f"I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
    level = measure(src)["I"]
    if level <= -60:                                    # silence (ebur128 floors it at −70): nothing to do
        proc.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", str(channels), "-ar", str(rate),
                  "-c:a", "pcm_s24le", str(dst)], check=True, capture_output=True, timeout=proc.FFMPEG)
        return {"input_i": str(level), "normalization_type": "none (silence)"}
    gain = TARGET_I - level
    ceiling = max(0.0625, min(1.0, 10 ** ((TARGET_TP - 1.0 - gain) / 20)))   # alimiter's range
    limiter = f"alimiter=limit={ceiling:.4f}:level=false:attack=1:release=60:latency=true"
    first = proc.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-af",
                      f"{limiter},loudnorm={spec}:print_format=json", "-f", "null", "-"],
                     capture_output=True, text=True, check=True, timeout=proc.FFMPEG)
    m = _loudnorm_json(first.stderr)
    second = proc.run(["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(src), "-af",
                       f"{limiter},loudnorm={spec}:linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                       f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                       f"offset={m['target_offset']}:print_format=json,{true_peak_guard(rate)},aresample={rate}:filter_size=64",
                       "-ac", str(channels), "-c:a", "pcm_s24le", str(dst)],
                      capture_output=True, text=True, check=True, timeout=proc.FFMPEG)
    return _loudnorm_json(second.stderr)


def measure(path) -> Dict[str, float]:
    """Integrated loudness, true peak and LRA of a file's first audio stream (ebur128)."""
    err = proc.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af",
                    "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True,
                   timeout=proc.FFMPEG).stderr
    summary = err[err.rfind("Summary:"):]
    num = lambda k: float(re.search(k + r":\s+(-?[\d.]+|-inf)", summary).group(1).replace("-inf", "-120"))
    return {"I": num("I"), "TP": num("Peak"), "LRA": num("LRA")}


def prepare_narration(audio_path, data_path, out_path) -> Dict:
    """Level the segments of `audio_path`, normalise to −14 LUFS, write `out_path` (wav)."""
    out_path = Path(out_path)
    segments = json.loads(Path(data_path).read_text(encoding="utf-8")).get("segments") or []
    samples = decode(audio_path)
    before = segment_levels(samples, segments)
    leveled, gains = level_segments(samples, segments)
    peak = float(np.max(np.abs(leveled))) if leveled.size else 0.0
    if peak > 0.999:                                    # a +6 dB segment must not clip before loudnorm
        leveled = leveled * (0.999 / peak)
    mid = out_path.with_name(out_path.stem + ".leveled.wav")
    try:
        _write_wav(leveled, mid)
        report = loudnorm_two_pass(mid, out_path)
    finally:
        mid.unlink(missing_ok=True)
    result = decode(out_path)
    if abs(result.size - samples.size) > int(0.01 * RATE):
        raise RuntimeError(f"loudness pass changed the length: {samples.size} -> {result.size} samples")
    after = segment_levels(result, segments)
    info = {"spread_before": spread(before), "spread_after": spread(after), "gains": gains,
            "loudnorm": {k: report.get(k) for k in ("input_i", "input_tp", "output_i", "output_tp",
                                                    "output_lra", "normalization_type")},
            "samples": [samples.size, result.size]}
    logger.info("loudness: spread %.1f -> %.1f dB, %s -> %s LUFS (%s)", info["spread_before"],
                info["spread_after"], report.get("input_i"), report.get("output_i"),
                report.get("normalization_type"))
    return info


def gate(path, segments: Optional[List[Dict]] = None) -> Dict:
    """STEP 75 §5 thresholds on a rendered file: −14 ±1 LUFS, TP ≤ −1 dBTP, spread ≤ 3 dB."""
    m = measure(path)
    flags = []
    if abs(m["I"] - TARGET_I) > 1.0:
        flags.append(f"loudness:{m['I']:.1f}LUFS")
    if m["TP"] > -1.0:
        flags.append(f"true_peak:{m['TP']:.1f}dBTP")
    if segments:
        s = spread(segment_levels(decode(path), segments))
        m["spread"] = s
        if s > 3.0:
            flags.append(f"segment_spread:{s:.1f}dB")
    return {**m, "flags": flags}

"""STEP 80 §00: a split-band de-esser on every narration (Garcia: «si o si, las s me rompen el oído»).

The voice alone — the stitched narration of the Shorts, the series and the lessons, and the outro's
voice — goes through one ffmpeg chain before any SFX are mixed and before the final loudnorm:

    [voice]acrossover=split=SPLIT:order=4th[lo][hi];
    [hi]acompressor=threshold=T:ratio=R:attack=1:release=60:knee=3:makeup=1[hic];
    [lo][hic]amix=inputs=2:normalize=0

T is relative to the narration, so the TTS level does not matter: T = integrated LUFS − 12 dB.
Measured by Claude on a cached eleven_v3 narration: −8.7 dB on the sibilant frames' 5–10 kHz,
−0.4 dB on the other frames', 0.00 dB on the body (100 Hz–4 kHz). ffmpeg's own `deesser` took
0.85 dB off the body: it dulls the voice.

`deess(src, dst)` writes the de-essed voice and returns the band measure (`measure`) that the
gates read: HF on sibilant frames down 5–12 dB, other frames ≤ 1.0 dB, body ≤ 0.3 dB.

Standard library, numpy and ffmpeg only: the lesson studio's venv uses it too.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, Optional

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.yaml"
DEFAULTS = {"enabled": True, "split_hz": 5500, "below_lufs_db": 12.0, "ratio": 4.0}
RATE = 44100
#: The gate's band math (STEP 80 §00).
SIB_MIN_DB, SIB_MAX_DB, NONSIB_MAX_DB, BODY_MAX_DB = 5.0, 12.0, 1.0, 0.3


def settings() -> Dict:
    """config.yaml audio.deesser, read without yaml (the studio's venv has none)."""
    out = dict(DEFAULTS)
    try:
        text = CONFIG.read_text(encoding="utf-8")
    except OSError:
        return out
    block = re.search(r"^\s+deesser:\s*\{([^}]*)\}", text, re.M)
    if not block:
        return out
    for key, value in re.findall(r"(\w+)\s*:\s*([^,\s]+)", block.group(1)):
        if key == "enabled":
            out[key] = value.strip().lower() in ("true", "yes", "1", "on")
        elif key in out:
            out[key] = float(value)
    return out


def _lufs(path: Path) -> float:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128",
                          "-f", "null", "-"], capture_output=True, text=True, timeout=600).stderr
    summary = err[err.rfind("Summary:"):]
    match = re.search(r"I:\s+(-?[\d.]+|-inf)", summary)
    return -70.0 if not match or match.group(1) == "-inf" else float(match.group(1))


def chain(threshold_db: float, cfg: Optional[Dict] = None) -> str:
    cfg = cfg or settings()
    thr = 10 ** (threshold_db / 20)
    return (f"acrossover=split={int(cfg['split_hz'])}:order=4th[lo][hi];"
            f"[hi]acompressor=threshold={thr:.6f}:ratio={cfg['ratio']:g}:attack=1:release=60:knee=3:makeup=1[hic];"
            f"[lo][hic]amix=inputs=2:normalize=0")


def _decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(RATE),
                          "-f", "f32le", "-"], capture_output=True, check=True, timeout=600).stdout
    return np.frombuffer(raw, "<f4").astype(np.float64)


def _bands(x: np.ndarray, n: int = 2048, hop: int = 1024):
    """Per-frame power in 5–10 kHz (HF) and 100 Hz–4 kHz (body)."""
    if x.size < n:
        x = np.pad(x, (0, n - x.size))
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    freqs = np.fft.rfftfreq(n, 1 / RATE)
    hf = power[:, (freqs >= 5000) & (freqs < 10000)].sum(axis=1)
    body = power[:, (freqs >= 100) & (freqs < 4000)].sum(axis=1)
    return hf, body


def measure(before: Path, after: Path) -> Dict:
    """The gate's numbers (dB taken off): HF on sibilant frames, HF on the other voiced frames,
    and the body. Sibilant frames: voiced, with HF within 6 dB of the body or above it.

    Sibilants are weighed by energy (how much the loud «s» the ear complains about comes down);
    the other frames by the mean of their per-frame reduction (whether an ordinary frame is
    dulled — summed, the few loud transitions into an «s» would dominate them). On the cached
    series narrations: sibilants 7.0–8.1 dB, other 0.3–0.5 dB, body 0.00 dB."""
    a, b = _decode(before), _decode(after)
    k = min(a.size, b.size)
    hf_a, body_a = _bands(a[:k])
    hf_b, body_b = _bands(b[:k])
    total = hf_a + body_a
    voiced = total > total.max() * 10 ** (-50 / 10) if total.size else total.astype(bool)
    sib = voiced & (hf_a >= body_a * 10 ** (-6 / 10))
    rest = voiced & ~sib
    off = lambda x, y, m: round(float(10 * np.log10((x[m].sum() + 1e-20) / (y[m].sum() + 1e-20))), 2) if m.any() else None
    per_frame = 10 * np.log10((hf_a + 1e-20) / (hf_b + 1e-20))
    other = round(float(per_frame[rest].mean()), 2) if rest.any() else None
    return {"sibilant_hf_db": off(hf_a, hf_b, sib), "other_hf_db": other,
            "body_db": off(body_a, body_b, voiced), "sibilant_frames": int(sib.sum()), "voiced_frames": int(voiced.sum())}


def flags(m: Dict) -> list:
    """What the gate refuses in a measure (none when the de-esser is off)."""
    if not m or m.get("enabled") is False:
        return []
    out = []
    sib = m.get("sibilant_hf_db")
    if sib is not None and not SIB_MIN_DB <= sib <= SIB_MAX_DB:
        out.append(f"deesser:sibilants_{sib}dB")
    if (m.get("other_hf_db") or 0.0) > NONSIB_MAX_DB:
        out.append(f"deesser:other_hf_{m['other_hf_db']}dB")
    if abs(m.get("body_db") or 0.0) > BODY_MAX_DB:
        out.append(f"deesser:body_{m['body_db']}dB")
    return out


def deess(src, dst, cfg: Optional[Dict] = None) -> Dict:
    """The voice in `src`, de-essed, as a wav at `dst`; returns the measure. With the de-esser
    disabled in config.yaml, `dst` is a plain copy and the measure says so."""
    cfg = cfg or settings()
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not cfg["enabled"]:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", str(RATE), str(dst)],
                       check=True, timeout=600)
        return {"enabled": False}
    lufs = _lufs(src)
    threshold = lufs - cfg["below_lufs_db"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", chain(threshold, cfg),
                    "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_f32le", str(dst)], check=True, timeout=600)
    return {"enabled": True, "input_lufs": round(lufs, 1), "threshold_db": round(threshold, 1),
            **measure(src, dst)}


def combine(measures) -> Dict:
    """One measure for a voice made of many clips (a lesson's beats), each number weighed by the
    frames it was measured on."""
    ms = [m for m in measures if m and m.get("enabled") is not False]
    if not ms:
        return {"enabled": False}

    def avg(key, weight):
        pairs = [(m[key], m[weight]) for m in ms if m.get(key) is not None and m.get(weight)]
        total = sum(w for _v, w in pairs)
        return round(sum(v * w for v, w in pairs) / total, 2) if total else None

    for m in ms:
        m.setdefault("other_frames", m.get("voiced_frames", 0) - m.get("sibilant_frames", 0))
    return {"enabled": True, "clips": len(ms), "sibilant_hf_db": avg("sibilant_hf_db", "sibilant_frames"),
            "other_hf_db": avg("other_hf_db", "other_frames"), "body_db": avg("body_db", "voiced_frames"),
            "sibilant_frames": sum(m.get("sibilant_frames", 0) for m in ms),
            "voiced_frames": sum(m.get("voiced_frames", 0) for m in ms)}

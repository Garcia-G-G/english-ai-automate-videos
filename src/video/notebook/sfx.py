"""Sound design for the notebook Shorts (STEP 77 §7): synthesised with numpy, like the
lessons' sfx.py — no downloads, no sample libraries, no licences, and no music bed.

    pop      30 ms sine burst 600→900 Hz        an emoji pops, a tick lands, a note slaps on
    swish    250 ms swept band of noise         the page comes in, turns, or leaves
    scratch  band-passed noise in strokes       the pencil writing, for as long as it writes

Each effect sits UNDER_DB below the voice's RMS (measured on the spoken segments of the
narration it is mixed into), and DUCK_DB lower again wherever it lands on a spoken word.
"""
from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

import numpy as np

UNDER_DB = 22.0
DUCK_DB = 6.0
#: A spoken word under an effect: the voice there within this much of its RMS.
WORD_WITHIN_DB = 15.0
#: The pencil is a texture under the voice, not an event: a little lower still.
SCRATCH_EXTRA_DB = 4.0
Event = Tuple[str, float, float]               # (name, start s, length s; 0 = the sound's own)


def pop(rate: int) -> np.ndarray:
    t = np.arange(int(0.030 * rate)) / rate
    freq = 600 + 300 * t / t[-1]
    env = np.minimum(1, t / 0.002) * np.exp(-t / 0.008)
    return np.sin(2 * np.pi * np.cumsum(freq) / rate) * env


def swish(rate: int) -> np.ndarray:
    n = int(0.250 * rate)
    noise = np.random.default_rng(11).standard_normal(n)
    out, y1, y2 = np.zeros(n), 0.0, 0.0
    r = 0.985
    for i in range(n):                         # a two-pole resonator whose centre sweeps up
        f = 400 * (2500 / 400) ** (i / n)
        a1, a2 = -2 * r * np.cos(2 * np.pi * f / rate), r * r
        y = (1 - r) * noise[i] - a1 * y1 - a2 * y2
        out[i], y2, y1 = y, y1, y
    return out * np.hanning(n)


def scratch(rate: int, seconds: float) -> np.ndarray:
    """Graphite on paper: high-passed noise in short strokes (~11 a second), soft ends."""
    n = max(1, int(seconds * rate))
    rng = np.random.default_rng(int(seconds * 1000) + 5)
    noise = rng.standard_normal(n)
    hp = np.concatenate([[0.0], np.diff(noise)])                 # tilt toward the top end
    smooth = np.convolve(hp, np.ones(3) / 3, mode="same")        # but not hiss
    t = np.arange(n) / rate
    strokes = 0.55 + 0.45 * np.sin(2 * np.pi * 11 * t + rng.uniform(0, 6)) ** 2
    ramp = np.minimum(1.0, np.minimum(t, t[-1] - t) / 0.03)
    return smooth * strokes * ramp


def clap(rate: int) -> np.ndarray:
    """A clapperboard: a hard noise crack (2 ms attack, 25 ms decay) over a short wooden knock."""
    n = int(0.12 * rate)
    t = np.arange(n) / rate
    crack = np.random.default_rng(7).standard_normal(n) * np.minimum(1, t / 0.002) * np.exp(-t / 0.025)
    knock = np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.03) * 0.6
    return crack + knock


def rms_db(x: np.ndarray) -> float:
    return 20 * np.log10(np.sqrt(np.mean(np.square(x))) + 1e-12)


def voice_rms_db(samples: np.ndarray, rate: int, spoken: Sequence[Tuple[float, float]]) -> float:
    """RMS of the narration over its spoken spans only (the think pauses are silence)."""
    parts = [samples[int(a * rate):int(b * rate)] for a, b in spoken if b > a]
    parts = [p for p in parts if p.size]
    return rms_db(np.concatenate(parts)) if parts else rms_db(samples)


def render(name: str, rate: int, seconds: float = 0.0) -> np.ndarray:
    return {"pop": lambda: pop(rate), "swish": lambda: swish(rate), "clap": lambda: clap(rate),
            "scratch": lambda: scratch(rate, seconds)}[name]()


def mix(samples: np.ndarray, rate: int, events: Iterable[Event],
        spoken: Sequence[Tuple[float, float]]) -> Tuple[np.ndarray, List[dict]]:
    """`samples` with every event added at its level; returns (mix, what was placed)."""
    voice = voice_rms_db(samples, rate, spoken)
    out = samples.astype(np.float64).copy()
    placed = []
    for name, start, length in events:
        x = render(name, rate, length)
        level = voice - UNDER_DB - (SCRATCH_EXTRA_DB if name == "scratch" else 0.0)
        i0, i1 = max(0, int(start * rate)), min(samples.size, int(start * rate) + x.size)
        under = samples[i0:i1]
        on_word = bool(under.size) and bool(rms_db(under) > voice - WORD_WITHIN_DB)   # the voice, not the pause
        if on_word:
            level -= DUCK_DB
        x = x * 10 ** ((level - rms_db(x)) / 20)
        i = int(round(start * rate))
        if i >= out.size or i < 0:
            continue
        x = x[:out.size - i]
        out[i:i + x.size] += x
        placed.append({"name": name, "at": round(start, 3), "level_db": round(level, 1), "ducked": on_word})
    return out, placed

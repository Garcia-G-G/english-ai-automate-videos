"""Three small sound effects, synthesised with numpy — no downloads, no sample libraries.

    pop     30 ms sine burst 600→900 Hz, fast decay      chip drops, sort landings
    whoosh  250 ms band-passed noise, centre 400→2500 Hz  transform moves, camera pushes
    tick    8 ms click at 2 kHz                           once per second of a quiz pause

Each file is levelled so its RMS sits UNDER_DB below the voice (gen_audio levels every
segment near TARGET_RMS_DB = −20 dBFS RMS); the tick sits 4 dB lower still. The scene
ducks an effect a further DUCK_DB when it lands on a spoken word. Written once as
16-bit mono WAV under media/sfx/ and reused.
"""
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RATE = 44_100
VOICE_RMS_DB = -20.0
UNDER_DB = 22.0
DUCK_DB = 6.0
NAMES = ("pop", "whoosh", "tick")


def pop() -> np.ndarray:
    t = np.arange(int(0.030 * RATE)) / RATE
    freq = 600 + 300 * t / t[-1]
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    env = np.minimum(1, t / 0.002) * np.exp(-t / 0.008)
    return np.sin(phase) * env


def whoosh() -> np.ndarray:
    n = int(0.250 * RATE)
    noise = np.random.default_rng(11).standard_normal(n)
    out, y1, y2 = np.zeros(n), 0.0, 0.0
    for i in range(n):                                  # a two-pole resonator whose centre sweeps up
        f = 400 * (2500 / 400) ** (i / n)
        r = 0.985
        a1, a2 = -2 * r * np.cos(2 * np.pi * f / RATE), r * r
        y = (1 - r) * noise[i] - a1 * y1 - a2 * y2
        out[i], y2, y1 = y, y1, y
    return out * np.hanning(n)


def tick() -> np.ndarray:
    t = np.arange(int(0.008 * RATE)) / RATE
    return np.sin(2 * np.pi * 2000 * t) * np.exp(-t / 0.0015)


def level_db(name: str) -> float:
    return VOICE_RMS_DB - UNDER_DB - (4.0 if name == "tick" else 0.0)


def rms_db(x: np.ndarray) -> float:
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


def render(name: str) -> np.ndarray:
    x = {"pop": pop, "whoosh": whoosh, "tick": tick}[name]()
    return x * 10 ** ((level_db(name) - rms_db(x)) / 20)


def path(name: str, out_dir: Path = HERE / "media" / "sfx") -> Path:
    """The effect's WAV, written on first use."""
    out = Path(out_dir) / f"{name}.wav"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        pcm = (np.clip(render(name), -1, 1) * 32767).astype("<i2").tobytes()
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm)
    return out

"""How TTS clips are asked for and joined — one rule for Shorts and lessons (STEP 76 §2).

Three things the Manim lessons learned by ear, now shared instead of copied:

  context  At a language switch, and at the start of a line, only the text that FOLLOWS
           is sent (next_text). With the previous text too, the model often starts a clip
           mid-sound or with a ~50 ms fragment of that context — the owner's «i-ira la
           tabla», «d-do the beds»: clean onsets 1/10 with both, 7/10 with next only
           (audio/_probe/stitching, 2026-10-13). Where the same voice goes on in the same
           language, both are sent.
  onset    Every clip is checked as it arrives (start level, fragment, doubled onset) and
           re-asked up to ONSET_RETRIES times; the cleanest take is kept, never just the last.
  gaps     After trimming, the gap between clips follows the punctuation that ends them.

The onset detector itself was experiments/manim_voiceover_poc/probes/onset.py (which now
re-exports it from here) and the gate was tts_elevenlabs' level path, loading that file
by path.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

import proc

RATE, FRAME = 44100, 220            # 5 ms
FINE = 88                           # 2 ms

#: Takes re-asked when a clip starts dirty.
ONSET_RETRIES = 2

#: Start-to-peak (first 5 ms frame minus the clip's peak, dB) a clean take stays under.
#: -30 came from the Manim lessons on multilingual_v2. eleven_v3 trims the lead-in, so a
#: word opening on /s/ /n/ /f/ /l/ starts at -9…-24 dB (30 takes of lv001, STEP 59 §2);
#: only takes that open within 5 dB of their peak (-4.1, -1.2, -0.4: a cut-in) sit above.
#: -6.5 is the midpoint of that gap. Re-measure with tools/onset_calibrate.py.
ONSET_START_DB = {"default": -30.0, "eleven_v3": -6.5}

#: STEP 76 §3, by ear: on eleven_v3 the start-to-peak limit above let through the takes the
#: owner hears as cut in (first 10 ms at −19…−16 dBFS, start-to-peak −13…−9 dB). The first
#: 10 ms level separates them: tools/onset_calibrate.py --on-disk _audit/onset_eleven_v3 put
#: 30 stored takes on a continuum with the gap between −21.7 and −19.0 dBFS; −20.9 is its
#: middle. It flags 10 of 30 (the old limit flagged 3). shortcut: one script's takes; re-run
#: the calibration when the owner flags a word on another script.
ONSET_FIRST_DBFS = {"eleven_v3": -20.9}

#: Gap after a trimmed clip, by the mark that ends it (seconds).
GAP_AFTER = {".": 0.30, "?": 0.30, "!": 0.30, ":": 0.20, ",": 0.14, ";": 0.18}
DEFAULT_GAP = 0.05          # a language switch mid-sentence: pad + gap + pad ≈ 130 ms


# ── context ──────────────────────────────────────────────────────────

def context(previous_lang: Optional[str], lang: str, before: str, after: str,
            full: bool = False) -> Tuple[str, str]:
    """(previous_text, next_text) for one clip: the previous text only when the same voice
    goes on in the same language (or `full`, the old behaviour everywhere)."""
    if full or (previous_lang is not None and previous_lang == lang):
        return before or "", after or ""
    return "", after or ""


def gap_after(text: str) -> float:
    return GAP_AFTER.get((text or "").rstrip()[-1:], DEFAULT_GAP)


# ── the onset detector ───────────────────────────────────────────────

def load(path) -> np.ndarray:
    pcm = proc.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE),
                    "-f", "s16le", "-"], capture_output=True, check=True, timeout=proc.FFMPEG).stdout
    return np.frombuffer(pcm, "<i2").astype(float) / 32768


def env_db(x):
    n = len(x) // FRAME
    f = x[: n * FRAME].reshape(n, FRAME)
    return 20 * np.log10(np.sqrt((f ** 2).mean(1)) + 1e-9)


def onset(x, below_peak=45.0):
    e = env_db(x)
    if not len(e):
        return None, e
    thr = e.max() - below_peak
    idx = np.where(e > thr)[0]
    return (int(idx[0]) if len(idx) else None), e


def fragment(e, start, peak):
    """A burst ≤ 90 ms, then a dip ≥ 14 dB under the burst lasting ≥ 10 ms, then speech again —
    all within the first 220 ms. Returns (burst_ms, dip_db) or None."""
    win = e[start: start + 44]
    if len(win) < 10:
        return None
    loud = win > peak - 30
    k = 0
    while k < len(win) and not loud[k]:
        k += 1
    b0 = k
    while k < len(win) and loud[k]:
        k += 1
    b1 = k                                   # end of the first loud run
    if b1 - b0 > 18 or b1 >= len(win):       # longer than 90 ms: that is the word itself
        return None
    burst = win[b0:b1].max()
    d0 = k
    while k < len(win) and win[k] < burst - 14:
        k += 1
    if k - d0 >= 2 and k < len(win) and (win[k:] > peak - 30).any():
        return ((b1 - b0) * 5, round(float(burst - win[d0:k].min()), 1))
    return None


def _fine(x):
    n = len(x) // FINE
    f = x[: n * FINE].reshape(n, FINE)
    return 20 * np.log10(np.sqrt((f ** 2).mean(1)) + 1e-9)


def _hf_share(x, i):
    """Share of energy above 1 kHz (dB) in a 22 ms window around 2 ms frame i."""
    seg = x[max(0, (i - 5) * FINE):(i + 6) * FINE]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    fr = np.fft.rfftfreq(len(seg), 1 / RATE)
    return 10 * np.log10(spec[fr > 1000].sum() / (spec.sum() + 1e-18) + 1e-12)


def doubled_onset(x):
    """None, or why the start sounds doubled («d-do», «m-make»):
    - 'fragment': a murmur lead from the onset (median share above 1 kHz < −30 dB), then
      within 140 ms a dip ≥ 12 dB under that lead and below −28 dB re peak, then the word — a
      quiet fragment the old check missed; a real first syllable («es | la») has a vowel's
      energy above 1 kHz, and the voice bar of a /d/ in running speech (one-request audio,
      owner: clean) sits more than 20 dB under the peak — his «d-do»s lead at −18…−8 dB;
    - 'held nasal': a nasal murmur (no energy above 1 kHz) of 80–160 ms held as loud as the
      vowel after it — a normal /m/ is quieter than its vowel.
    shortcut: tuned on the owner's 5 dirty + 3 clean spots (b18, b05); the −20 dB lead line has
    ~2 dB of margin each side — re-check against his ear on more beats."""
    e = _fine(x)
    if not len(e):
        return None
    r = e - e.max()
    start = int(np.argmax(r > -30))
    lead = r[start:start + 70]                                     # 140 ms
    for k in range(8, len(lead)):                                  # a dip after ≥ 16 ms of lead
        before = np.median(lead[:k])
        if before >= -20 and lead[k] < -28 and lead[k] < before - 12 and (r[start + k:start + k + 60] > -12).any():
            # …and the lead is a murmur (nothing above 1 kHz), not a real first syllable («es | la»)
            if np.median([_hf_share(x, start + i) for i in range(0, k, 4)]) < -30:
                return "fragment"
            break
    hf = [_hf_share(x, i) for i in range(start, min(len(e), start + 150))]
    run = next((k for k, v in enumerate(hf) if v > -18), len(hf))    # 2 ms frames of nasal murmur
    # 80–160 ms: longer is /m/ + a closed vowel («Mira»: /i/ has little energy above 1 kHz too)
    if 40 <= run <= 80:
        nasal, vowel = np.mean(r[start:start + run]), np.mean(r[start + run:start + run + 50])
        if nasal >= vowel:
            return "held nasal"
    return None


def first_dbfs(x, ms: float = 10.0) -> float:
    """RMS level of a clip's first `ms`, in dBFS: a clip that rises from the noise floor sits
    far below speech; one that starts mid-sound («cut-in») sits at speech level."""
    n = max(1, int(RATE * ms / 1000))
    head = x[:n]
    return round(float(20 * np.log10(np.sqrt(np.mean(head ** 2)) + 1e-9)), 1) if head.size else -120.0


# ── the gate ─────────────────────────────────────────────────────────

def onset_start_limit(model: Optional[str] = None) -> float:
    return ONSET_START_DB.get(model or "default", ONSET_START_DB["default"])


def onset_values(path) -> Dict:
    """The gate's three measurements of one clip as the TTS returned it."""
    x = load(path)
    e = env_db(x)
    start, _ = onset(x)
    if start is None:
        return {"start_db": None, "fragment": None, "doubled_onset": None, "first_dbfs": first_dbfs(x)}
    return {"start_db": round(float(e[0] - e.max()), 1), "fragment": fragment(e, start, e.max()),
            "doubled_onset": doubled_onset(x), "first_dbfs": first_dbfs(x)}


def onset_clean(values: Dict, model: Optional[str] = None) -> bool:
    """No fragment, no doubled onset, and a quiet start: under the model's first-10 ms limit
    where it has one (eleven_v3), else under its start-to-peak limit."""
    if values["start_db"] is None or values["fragment"] is not None or values["doubled_onset"] is not None:
        return False
    first_limit = ONSET_FIRST_DBFS.get(model or "default")
    if first_limit is not None and values.get("first_dbfs") is not None:
        return values["first_dbfs"] < first_limit
    return values["start_db"] < onset_start_limit(model)


def cleanest_take(takes: List[Dict], model: Optional[str] = None) -> int:
    """Index of the take to keep: a clean one, else no fragment and no doubled onset with the
    quietest start, else the quietest start. Never just the last one."""
    def rank(i):
        v = takes[i]
        flawed = v["start_db"] is None or v["fragment"] is not None or v["doubled_onset"] is not None
        return (not onset_clean(v, model), flawed, v["start_db"] if v["start_db"] is not None else 0.0, i)
    return min(range(len(takes)), key=rank)

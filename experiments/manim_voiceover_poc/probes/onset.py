"""Onset of a speech file: where it starts, and whether it starts with a short fragment
(burst → dip → speech) — the «i-ira» the owner hears. 5 ms RMS frames."""
import subprocess, sys
import numpy as np

RATE, FRAME = 44100, 220            # 5 ms

def load(path):
    pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
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

if __name__ == "__main__":
    for path in sys.argv[1:]:
        x = load(path)
        s, e = onset(x)
        print(path, s * 5 if s is not None else None, fragment(e, s, e.max()) if s is not None else None)


# ── v2, from the owner's ear on make-vs-do b18 (2026-10-13): relative to the segment's peak ──
FINE = 88                            # 2 ms


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

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

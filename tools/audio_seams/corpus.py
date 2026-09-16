"""Corpus sweep for end-of-segment cuts.

TWO metrics, because the first one alone cannot see a repaired tail.

  CLIFF  the voice is still loud in the 60 ms before the recorded end AND the
         audio is at digital-zero territory 40-120 ms after it (past the mp3
         decoder ringing that follows any hard cut). This is
         the defect: a guillotine. A repaired clip fails condition 2 and stops
         being counted, which is the point.

  DROP   the older metric: loud tail, then >=6 dB quieter. It stays because the
         before/after comparison has to be honest, but READ IT WITH CARE. It
         fires on any loud tail followed by a natural decay too, so a clip whose
         decay was rebuilt still trips it. A DROP count that does not fall after
         a tail repair is not a regression. A CLIFF count that does not fall is.

Why the distinction exists: `repair_truncated_tail` adds its fade AFTER the
recorded end (the end is measured speech end, which by construction has speech
before it), so no metric anchored 60 ms BEFORE the end can see the repair. What
changes is what comes AFTER, and only CLIFF looks there.
"""
import json, glob, subprocess, math, os, collections, sys

import numpy as np

SR = 16000
FLOOR_DB = -100.0      # below this is anullsrc/exact-zero territory, not room tone
LOUD_DB = -30.0


def load(p):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-f", "s16le",
                        "-ac", "1", "-ar", str(SR), "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype="<i2").astype(np.float32) / 32768.0


def db(x):
    if x.size == 0:
        return None
    r = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    return -140.0 if r <= 1e-7 else 20 * math.log10(r)


def win(a, t0, t1):
    i0, i1 = max(0, int(t0 * SR)), min(a.size, int(t1 * SR))
    return a[i0:i1] if i1 > i0 else a[0:0]


def sweep(pattern="output/audio/*/*.json"):
    agg = collections.defaultdict(lambda: [0, 0, 0, 0])   # cliff, drop, total, files
    for jf in sorted(glob.glob(pattern)):
        mp3 = jf[:-5] + ".mp3"
        if not os.path.exists(mp3):
            continue
        try:
            j = json.load(open(jf))
        except Exception:                                  # noqa: BLE001
            continue
        segs = j.get("segments")
        if not isinstance(segs, list) or not segs or not isinstance(segs[0], dict):
            continue
        a = load(mp3)
        if a.size == 0:
            continue
        vt = jf.split("/")[2]
        for s in segs:
            en = s.get("end")
            if en is None or en <= 0.05 or str(s.get("id", "")).startswith("countdown"):
                continue
            tail = db(win(a, en - 0.060, en))
            post = db(win(a, en, en + 0.100))
            near = db(win(a, en + 0.040, en + 0.120))
            if tail is None or post is None or near is None:
                continue
            d = agg[vt]
            d[2] += 1
            if tail > LOUD_DB and near <= FLOOR_DB:
                d[0] += 1
            if tail > LOUD_DB and (tail - post) >= 6:
                d[1] += 1
        agg[vt][3] += 1
    return agg


if __name__ == "__main__":
    agg = sweep(sys.argv[1] if len(sys.argv) > 1 else "output/audio/*/*.json")
    print(f"{'type':14} {'CLIFF (the defect)':>20} {'DROP (read with care)':>23}   videos")
    print("-" * 68)
    tc = td = tt = 0
    for vt, (c, dr, t, n) in sorted(agg.items()):
        print(f"{vt:14} {f'{c}/{t} = {100*c/t if t else 0:.0f}%':>20} "
              f"{f'{dr}/{t} = {100*dr/t if t else 0:.0f}%':>23}   {n}")
        tc += c; td += dr; tt += t
    print("-" * 68)
    print(f"{'TOTAL':14} {f'{tc}/{tt} = {100*tc/tt if tt else 0:.0f}%':>20} "
          f"{f'{td}/{tt} = {100*td/tt if tt else 0:.0f}%':>23}")

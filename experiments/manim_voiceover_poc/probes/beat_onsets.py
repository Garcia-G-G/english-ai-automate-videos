"""Score a finished beat: at every segment start (where L.segments switches language),
cut from the quietest point after the previous word to the next segment's start and run
doubled_onset on it. Works on any variant — stitched or one request."""
import json, re, subprocess, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import lesson as L
from probes import onset as O


def starts(narration: str) -> list:
    """Index (among word tokens) of the first word of each text segment, and its text."""
    out, k = [], 0
    for seg in L.segments(narration):
        if "text" in seg:
            toks = [t for t in seg["text"].split() if re.search(r"\w", t)]
            if toks:
                out.append((k, seg["lang"], seg["text"]))
            k += len(toks)
    return out


def score(mp3: Path, words: list, narration: str) -> list:
    x = O.load(mp3)
    words = [w for w in words if re.search(r"\w", w["word"])]
    rows = []
    begins = starts(narration)
    for n, (k, lang, text) in enumerate(begins):
        if k >= len(words):
            rows.append({"text": text, "lang": lang, "dirty": None})
            continue
        a = max(words[k - 1]["end"] if k else 0.0, words[k]["start"] - 0.4)
        b = words[k]["start"]
        if b - a > 0.004:                         # start at the quietest point between the two words
            e = O._fine(x[int(a * O.RATE): int(b * O.RATE)])
            t0 = a + int(np.argmin(e)) * O.FINE / O.RATE if len(e) else a
        else:
            t0 = a
        nxt = begins[n + 1][0] if n + 1 < len(begins) else None      # to the next segment: the same peak as a segment
        t1 = words[nxt]["start"] if nxt is not None and nxt < len(words) else len(x) / O.RATE
        win = x[int(t0 * O.RATE): int(t1 * O.RATE)]
        why = O.doubled_onset(win) if len(win) > O.FINE * 20 else None
        rows.append({"text": text, "lang": lang, "at": round(words[k]["start"], 2), "dirty": why})
    return rows


if __name__ == "__main__":
    mp3, words, lesson, beat = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
    narration = next(b for b in L.load(HERE / f"lessons/{lesson}.json")["beats"] if b["id"] == beat)["narration"]
    for r in score(mp3, json.loads(words.read_text()), narration):
        print(r)

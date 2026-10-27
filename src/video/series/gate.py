"""The quality gate for «Hecho con Claude» (STEP 78 §7), on a rendered Short:

    duration     25–60 s, outro included (beats.DURATION_RANGE)
    loudness     −14 LUFS ± 1, true peak ≤ −1 dBTP (loudness.gate, the notebook Shorts' own)
    deesser      the voice's sibilants down 5–12 dB, other frames ≤ 1.0 dB, body ≤ 0.3 dB (STEP 80 §00)
    english      every [[English]] phrase heard in the transcript, where its beat is (the local
                 whisper, $0): its words in order, in a run of consecutive words, within
                 HEARD_WINDOW of the beat; one miss allowed per four words
    hook         frame 0 shows `hook_text`: its box differs from the same frame drawn without it
    safe areas   every readable box of the style inside them (series_kit.in_safe_area)
    stillness    no stretch longer than STILL_MAX_S of consecutive frames whose mean absolute
                 difference stays under STILL_DIFF (STEP 78b §1: a cursor, grain, a breath or a
                 slow push all count as motion; a static x264 frame repeats at exactly 0)

check() returns {"gate": "PASS" | "REJECT", "flags": [...], "checks": {...}}.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from . import beats as B
from . import series_kit as K

HEARD_WINDOW = 1.5
STILL_MAX_S = 4.0


def longest_still(mp4: Path, fps: float = 30.0) -> Dict:
    """The longest run of consecutive frames that do not move (src/stillness.py), at the Shorts' size."""
    import stillness
    return stillness.longest_still(mp4, fps, (K.W, K.H))


#: Whisper writes what it hears, not what the script spells (STEP 78b §2, hc_c010 from the panel:
#: «since three o'clock» came back «since 3 o clock», a lone «for» came back «4»). Both sides are
#: compared by sound: numbers as words, «o clock» as one word, then the homophones folded.
_NUMBER = {str(n): w for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split())}
_SOUND = {"four": "for", "two": "to", "too": "to"}


def _by_sound(tokens: List[str]) -> List[str]:
    out = []
    for tok in tokens:
        tok = _NUMBER.get(tok, tok)
        if tok == "clock" and out and out[-1] == "o":
            out[-1] = "oclock"
            continue
        out.append(_SOUND.get(tok, tok))
    return out


def _same_word(a: str, b: str) -> bool:
    """Equal, or one letter apart in a word of three or more (Ana / Anna, your / youre); never
    two short words («am» / «an»)."""
    if a == b:
        return True
    if min(len(a), len(b)) < 3 or abs(len(a) - len(b)) > 1:
        return False
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio() >= 0.85


def _in_order(want: List[str], stream: List[str]) -> int:
    """The most of `want` found in order inside any run of len(want) + 1 consecutive words."""
    best, n = 0, len(want)
    for i in range(len(stream)):
        window, k = stream[i:i + n + 1], 0
        for tok in window:
            if k < n and _same_word(tok, want[k]):
                k += 1
        best = max(best, k)
    return best


def english_heard(timeline: Dict, words: List[Dict]) -> Dict:
    """Each [[English]] phrase against the transcript near its beat: its words IN ORDER, in a run
    of consecutive words, one miss allowed per four («I am cold» is not heard in «I have cold»)."""
    toks = [(B._norm(w["word"]), float(w["start"])) for w in words]
    rows = []
    for beat in timeline["beats"]:
        near = _by_sound([t for t, s in toks if t and beat["start"] - HEARD_WINDOW <= s <= beat["end"] + HEARD_WINDOW])
        for e in beat["english"]:
            want = _by_sound(B._tokens(e["text"]))
            got = _in_order(want, near)
            heard = len(want) - got <= len(want) // 4
            rows.append({"text": e["text"], "share": round(got / max(1, len(want)), 2), "heard": heard})
    return {"phrases": rows, "missing": [r["text"] for r in rows if not r["heard"]]}


def frame_zero(mp4: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True, timeout=120).stdout
    return np.frombuffer(raw, np.uint8).reshape(K.H, K.W, 3)


def hook_shown(script: Dict, style, timeline: Dict, frame0: np.ndarray) -> Dict:
    """Frame 0's hook box against the same frame drawn with a blank hook."""
    box = dict(style.text_boxes(script)).get("hook")
    if box is None:
        return {"shown": False, "why": "the style declares no hook box"}
    blank = np.asarray(style.frame(0.0, dict(script, hook_text=" "), timeline).convert("RGB")).astype(int)
    x0, y0, x1, y1 = (int(v) for v in box)
    diff = float(np.abs(frame0[y0:y1, x0:x1].astype(int) - blank[y0:y1, x0:x1]).mean())
    return {"shown": diff > 4.0, "mean_diff": round(diff, 2), "box": [round(v) for v in box]}


def check(script: Dict, mp4, info: Dict, narration_wav: Optional[Path] = None, style=None,
          transcribe=None) -> Dict:
    """The gate on a rendered Short. `transcribe(path) -> words` defaults to the local whisper."""
    import loudness
    from .render import style_module
    mp4 = Path(mp4)
    style = style or style_module(script["style"])
    timeline = info["timeline"]
    flags, checks = [], {}

    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                           capture_output=True, text=True, check=True)
    duration = float(probe.stdout.strip())
    checks["duration"] = round(duration, 2)
    reason = B.gate(duration)
    if reason:
        flags.append(reason)

    loud = loudness.gate(mp4)
    checks["loudness"] = {k: loud.get(k) for k in ("I", "TP", "LRA")}
    flags += [f for f in loud.get("flags", []) if not f.startswith("spread")]

    # STEP 80 §00: the de-esser, measured on the voice alone before the mix
    import deesser
    checks["deesser"] = info.get("deesser")
    flags += deesser.flags(info.get("deesser"))

    source = narration_wav or timeline.get("audio") or mp4
    if transcribe is None:
        # Local only ($0). The base model's temperature fallback makes runs differ on a mixed
        # Spanish/English voice, so a phrase counts as heard in the auto-language transcript or
        # in one forced to English.
        import asr_timings as A
        passes = [lambda path: A._words_from_local(Path(path), None) or [],
                  lambda path: A._words_from_local(Path(path), "en") or []]
    else:
        passes = [transcribe]
    words, heard = [], None
    for run in passes:
        got = run(source)
        words = words or got
        this = english_heard(timeline, got)
        if heard is None:
            heard = this
        else:
            for row, other in zip(heard["phrases"], this["phrases"]):
                row["heard"] = row["heard"] or other["heard"]
                row["share"] = max(row["share"], other["share"])
            heard["missing"] = [r["text"] for r in heard["phrases"] if not r["heard"]]
        if not heard["missing"]:
            break
    checks["english"] = heard
    flags += [f"english_unheard:{t}" for t in heard["missing"]]
    if not words:
        flags.append("english_unchecked:no_transcript")

    hook = hook_shown(script, style, timeline, frame_zero(mp4))
    checks["hook"] = hook
    if not hook["shown"]:
        flags.append("hook_not_on_frame_0")

    outside = [label for label, box in style.text_boxes(script) if not K.in_safe_area(box)]
    if not K.in_safe_area(K.outro_answer_box(script["challenge"]["answer"])):
        outside.append("outro answer")
    challenge_box = dict(style.text_boxes(script)).get("challenge")
    if challenge_box and not K.in_safe_area(K.reveal_layout(challenge_box, script["challenge"]["answer"])["box"]):
        outside.append("the answer's reveal")
    checks["safe_areas"] = {"outside": outside}
    flags += [f"unsafe:{label}" for label in outside]

    still = longest_still(mp4)
    checks["still"] = still
    if still["seconds"] > STILL_MAX_S:
        flags.append(f"still:{still['seconds']}s_from_{still['from']}s")

    return {"gate": "REJECT" if flags else "PASS", "flags": flags, "checks": checks}

"""One timeline from the voice (STEP 78 §2).

The series' narration is its `voice` lines, joined and voiced through the existing bilingual
path (tts_bilingual: the STEP 76 [[ ]] segmenter, stitch rule, TTS cache, eleven_v3). Its timed
words are mapped back onto the lines, and every style animates on the result:

    beats = [{"i", "text", "start", "end", "english": [{"text", "start", "end"}]}]

Nothing is timed by hand. The comic's countdown is the one inserted silence: COUNTDOWN seconds
of room tone after its countdown line («Tienes tres segundos», «Tres, dos, uno…»), or, in a
script without one, just before the reveal («¡La B!…»).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

COUNTDOWN = 3.0
ROOM_TONE_DB = -62.0                 # the quiet under a pause: a still room, not digital zero
DURATION_RANGE = (25.0, 60.0)        # the whole Short, outro included
MODEL_ID = "eleven_v3"               # STEP 78: the series' voice
_MARK = re.compile(r"\[\[(.+?)\]\]")


def full_script(script: Dict) -> str:
    return " ".join(line.strip() for line in script["voice"])


def _norm(token: str) -> str:
    token = unicodedata.normalize("NFD", token.lower())
    return "".join(c for c in token if c.isalnum() and unicodedata.category(c) != "Mn")


def _tokens(text: str) -> List[str]:
    return [t for t in (_norm(x) for x in _MARK.sub(r"\1", text).split()) if t]


def line_of_words(lines: List[str], words: List[Dict]) -> List[int]:
    """For each timed word, the index of the voice line it belongs to.

    Greedy alignment of normalised tokens: the TTS words follow the script in order, but may
    split or merge a token («25», «I'm») — a word that matches nothing ahead stays on the
    current line."""
    stream = [(k, tok) for k, line in enumerate(lines) for tok in _tokens(line)]
    out, pos = [], 0
    for w in words:
        tok = _norm(w["word"])
        found = None
        for j in range(pos, min(len(stream), pos + 6)):
            if stream[j][1] == tok or (tok and (stream[j][1].startswith(tok) or tok.startswith(stream[j][1]))):
                found = j
                break
        if found is not None:
            pos = found + 1
            out.append(stream[found][0])
        else:
            out.append(stream[pos - 1][0] if pos else 0)
    return out


def countdown_line(script: Dict) -> Optional[int]:
    """The line after which the comic's countdown goes, or None (other styles)."""
    if script.get("style") != "comic":
        return None
    for k, line in enumerate(script["voice"]):
        low = line.lower()
        if "tres segundos" in low or re.search(r"tres,\s*dos,\s*uno", low):
            return k
    for k, line in enumerate(script["voice"]):
        if k and line.lstrip().startswith("¡La "):
            return k - 1
    return None


def build_beats(script: Dict, words: List[Dict], duration: float) -> Dict:
    """The beat list from timed words: one beat per voice line, with its [[English]] times."""
    lines = script["voice"]
    owner = line_of_words(lines, words)
    beats = []
    for k, line in enumerate(lines):
        mine = [w for w, o in zip(words, owner) if o == k]
        start = mine[0]["start"] if mine else (beats[-1]["end"] if beats else 0.0)
        end = mine[-1]["end"] if mine else start
        english = []
        for phrase in _MARK.findall(line):
            want = _tokens(phrase)
            hit = _find_phrase(mine, want)
            if hit:
                english.append({"text": phrase, "start": hit[0], "end": hit[1]})
            else:                                    # not heard where expected: the line's own span
                english.append({"text": phrase, "start": start, "end": end, "unheard": True})
        beats.append({"i": k, "text": line, "start": round(start, 3), "end": round(end, 3), "english": english,
                      "words": [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in mine]})
    return {"beats": beats, "duration": round(duration, 3), "countdown": None}


def word_time(beat: Dict, phrase: str) -> Optional[float]:
    """When the voice starts saying `phrase` (Spanish or English) inside a beat, from its words."""
    want = _tokens(phrase)
    hit = _find_phrase(beat.get("words") or [], want) if want else None
    return hit[0] if hit else None


def _find_phrase(words: List[Dict], want: List[str]) -> Optional[Tuple[float, float]]:
    toks = [_norm(w["word"]) for w in words]
    n = len(want)
    for i in range(len(toks) - n + 1):
        if all(toks[i + j] == want[j] or toks[i + j].startswith(want[j]) for j in range(n)):
            return words[i]["start"], words[i + n - 1]["end"]
    if want:                                         # the first token alone, as a fallback
        for i, t in enumerate(toks):
            if t == want[0]:
                return words[i]["start"], words[min(len(words) - 1, i + n - 1)]["end"]
    return None


def insert_countdown(timeline: Dict, samples: np.ndarray, rate: int, after: int) -> Tuple[Dict, np.ndarray]:
    """COUNTDOWN seconds of room tone between beat `after` and the next; everything later
    moves by COUNTDOWN. Returns (timeline, samples)."""
    beats = timeline["beats"]
    a = beats[after]["end"]
    b = beats[after + 1]["start"] if after + 1 < len(beats) else a
    at = (a + b) / 2
    i = int(round(at * rate))
    rng = np.random.default_rng(3)
    tone = rng.standard_normal(int(COUNTDOWN * rate)) * 10 ** (ROOM_TONE_DB / 20)
    ramp = np.minimum(1.0, np.arange(tone.size) / (0.01 * rate))
    tone *= np.minimum(ramp, ramp[::-1])
    out = np.concatenate([samples[:i], tone, samples[i:]])
    shifted = []
    for beat in beats:
        if beat["start"] >= at:
            beat = dict(beat, start=round(beat["start"] + COUNTDOWN, 3), end=round(beat["end"] + COUNTDOWN, 3),
                        english=[dict(e, start=round(e["start"] + COUNTDOWN, 3), end=round(e["end"] + COUNTDOWN, 3))
                                 for e in beat["english"]],
                        words=[dict(w, start=round(w["start"] + COUNTDOWN, 3), end=round(w["end"] + COUNTDOWN, 3))
                               for w in beat.get("words") or []])
        shifted.append(beat)
    return ({**timeline, "beats": shifted, "duration": round(timeline["duration"] + COUNTDOWN, 3),
             "countdown": (round(at, 3), round(at + COUNTDOWN, 3))}, out)


def gate(total_seconds: float) -> Optional[str]:
    """None when the whole Short (outro included) is inside DURATION_RANGE, else the reason."""
    lo, hi = DURATION_RANGE
    if total_seconds < lo:
        return f"duration:{total_seconds:.1f}s<{lo:.0f}s"
    if total_seconds > hi:
        return f"duration:{total_seconds:.1f}s>{hi:.0f}s"
    return None


def voice_timeline(script: Dict, out_dir: Path, *, dry_run: bool = False) -> Dict:
    """Voice the script (cached), map its words to beats, insert the comic's countdown.

    Writes <out_dir>/<id>.voice.wav (the narration at the TTS's level; loudness comes later) and
    returns the timeline with "audio" set to it. dry_run plans the calls, voices nothing."""
    import loudness
    import tts_bilingual as B
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    from cost_tracker import reset_tracker
    settings = dict(B.resolve_settings(), model_id=MODEL_ID)
    data = {"type": "hecho_con_claude", "full_script": full_script(script)}
    mp3 = out_dir / f"{script['id']}.voice.mp3"
    tracker = reset_tracker(script["id"])                # its spend is this script's (STEP 78: ≤ $0.30)
    try:
        result = B.generate_bilingual_narration(data, str(mp3), settings=settings, dry_run=dry_run)
    finally:
        tracker.save()
    timeline = build_beats(script, result["words"], result["duration"])
    timeline["tts_calls"] = len(result.get("tts_calls") or [])
    timeline["tts_usd"] = round(sum(e["cost_usd"] for e in tracker.entries), 4)
    if dry_run:
        return timeline
    samples = loudness.decode(mp3)
    after = countdown_line(script)
    if after is not None:
        timeline, samples = insert_countdown(timeline, samples, loudness.RATE, after)
    wav = out_dir / f"{script['id']}.voice.wav"
    loudness._write_wav(samples, wav)
    timeline["audio"] = str(wav)
    timeline["duration"] = round(samples.size / loudness.RATE, 3)
    return timeline

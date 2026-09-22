#!/usr/bin/env python3
"""Measure how long a script actually becomes, from the videos already on disk.

    python3 tools/duration_calibrate.py

WHY. config.yaml carries a `rate` and a `silence` per video type and the
duration band is judged against them. Those numbers were CALCULATED, never
measured: the band has existed for weeks and nothing ever compared a prediction
to a finished mp3. This reads every (script, audio) pair on disk and fits the
real relationship. It costs nothing -- the material is already produced.

THE FINDING THAT MAKES THIS NECESSARY. `full_script` is NOT the spoken text for
four of the six types. tts_elevenlabs.generate_<type>_audio_segmented builds
the audio from the STRUCTURED FIELDS -- question, options, explanation,
statement, sentence, pairs -- and copies full_script into the metadata
untouched. So measuring full_script for a quiz measures a string nobody says,
and a script can sit perfectly inside the band while producing a 30-second
video. spoken_words() below is the correction: each type measured against the
text its own generator actually sends to the API.
"""

from __future__ import annotations

import collections
import glob
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    from audio_tags import strip_tags
except ImportError:                                         # noqa: BLE001
    def strip_tags(t): return t


#: Which fields each type's generator sends to the TTS. Not a guess -- read off
#: generate_<type>_audio_segmented, where every other field is metadata.
SPOKEN_FIELDS = {
    "educational":   ("full_script",),
    "pronunciation": ("full_script",),
    "vocabulary":    ("title", "pairs"),
    "quiz":          ("question", "options", "explanation"),
    "true_false":    ("statement", "explanation"),
    "fill_blank":    ("sentence", "options", "explanation"),
}


def _count(value) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(strip_tags(value).split())
    if isinstance(value, dict):
        return sum(_count(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return sum(_count(v) for v in value)
    return 0


#: Where each type keeps its extra items, and what one item contributes.
ITEM_ARRAY = {
    "quiz":       ("questions",  ("question", "options", "explanation")),
    "true_false": ("statements", ("statement", "explanation")),
    "fill_blank": ("sentences",  ("sentence", "options", "explanation")),
}


def _items_spoken(vtype: str) -> int:
    """How many items the pipeline actually synthesises, from config."""
    try:
        import yaml
        cfg = yaml.safe_load(open(ROOT / "config.yaml", encoding="utf-8"))
        return int(((cfg["duration"]["types"].get(vtype) or {})
                    .get("items_spoken")) or 1)
    except Exception:                                       # noqa: BLE001
        return 1


def items_in_audio(meta: dict) -> int:
    """How many items THIS artifact's audio actually carries.

    WHY NOT config. `items_spoken` says what the pipeline synthesises
    TODAY; a sample on disk was produced under whatever the config said the
    day it ran. The moment quiz moved from 1 to 2, reading config here
    started counting item two's words for eighty-nine historical one-item
    videos that never spoke them -- and the fit answered with a straight
    face: quiz's rate leapt 2.43 -> 3.95 words per second, which is not a
    measurement of anything, just the same seconds divided by words nobody
    said.

    The audio knows. 1af342d writes item N>1 as `i<N>_<name>`, so the
    highest prefix present IS the item count, per sample, whatever the
    config has since become.
    """
    st = (meta or {}).get("segment_times") or {}
    highest = 1
    for name in st:
        if name[:1] == "i" and "_" in name:
            head = name.split("_", 1)[0][1:]
            if head.isdigit():
                highest = max(highest, int(head))
    return highest


def spoken_words(script: dict, items: int = None) -> int:
    """Words this script's generator sends to the TTS for `items` items.

    `items` is measured from the artifact's own audio (items_in_audio) when
    there is one. It falls back to config's `items_spoken` for a script with
    no audio beside it -- a prediction rather than a measurement, which is
    the only case where today's config is the right answer.
    """
    vtype = script.get("type")
    fields = SPOKEN_FIELDS.get(vtype)
    if not fields:
        return _count(script.get("full_script"))
    total = sum(_count(script.get(f)) for f in fields)

    spec = ITEM_ARRAY.get(vtype)
    if not spec:
        return total
    key, item_fields = spec
    wanted = _items_spoken(vtype) if items is None else max(1, items)
    items = script.get(key) or []
    # item one is the root, already counted, so only the extras are added
    for item in items[1:wanted]:
        total += sum(_count(item.get(f)) for f in item_fields)
    return total


def _pairs():
    """(audio metadata path, script path) for every produced pair on disk.

    TWO LAYOUTS, AND MISSING THE SECOND MADE THIS TOOL MEASURE THE PAST.
    The original walked output/audio/<type>/*.json against
    output/scripts/<type>/<same name>.json. That is the LEGACY tree, and
    nothing has been written into it since 2026-08-21: every render since
    produces output/artifacts/<id>/ with audio/narration.json and
    script/script.json beside it.

    So 30 finished artifacts were invisible here -- 11 of them quiz -- and
    quiz's fit of n=56 was drawn entirely from videos made before the
    current layout existed. A calibration tool that cannot see the last
    month of production is measuring the wrong month.
    """
    for audio in glob.glob(str(ROOT / "output/audio/*/*.json")):
        vtype = os.path.basename(os.path.dirname(audio))
        yield audio, str(ROOT / "output/scripts" / vtype / os.path.basename(audio))

    for audio in glob.glob(str(ROOT / "output/artifacts/*/audio/narration.json")):
        yield audio, os.path.join(os.path.dirname(os.path.dirname(audio)),
                                  "script", "script.json")


def samples():
    """(type, spoken_words, seconds) for every produced pair on disk."""
    out = collections.defaultdict(list)
    seen = set()
    for audio, script_path in _pairs():
        try:
            meta = json.load(open(audio, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        duration, vtype = meta.get("duration"), meta.get("type")
        if not duration or not vtype:
            continue
        if not os.path.exists(script_path):
            continue
        try:
            script = json.load(open(script_path, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        # The same artifact can appear in both trees when an older render
        # was copied forward; counting it twice would weight it twice.
        n = spoken_words(script, items=items_in_audio(meta))
        key = (vtype, round(float(duration), 3), n)
        if key in seen:
            continue
        seen.add(key)
        if n >= 3:
            out[vtype].append((n, float(duration)))
    return out


def fit(data):
    """Least squares on duration = words/rate + overhead."""
    xs = [w for w, _ in data]
    ys = [d for _, d in data]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if not den:
        return None
    slope = sum((x - mx) * (y - my) for x, y in data) / den
    if slope <= 0:
        return None
    return 1 / slope, my - slope * mx


def main():
    import yaml
    cfg = yaml.safe_load(open(ROOT / "config.yaml", encoding="utf-8"))["duration"]
    band = cfg["band"]
    data = samples()

    print(f"{'type':14} {'n':>3} {'median words':>13} {'median s':>9}"
          f"   {'rate':>6} {'overhead':>9}   {'cfg rate':>8} {'cfg sil':>8}")
    print("-" * 88)
    for vtype in sorted(data):
        rows = data[vtype]
        if len(rows) < 4:
            print(f"{vtype:14} {len(rows):>3}   too few samples")
            continue
        fitted = fit(rows)
        c = cfg["types"].get(vtype, {})
        if not fitted:
            print(f"{vtype:14} {len(rows):>3}   no fit — duration does not "
                  f"track this word count")
            continue
        rate, overhead = fitted
        print(f"{vtype:14} {len(rows):>3} "
              f"{statistics.median([w for w, _ in rows]):>13.0f} "
              f"{statistics.median([d for _, d in rows]):>8.1f}s"
              f"   {rate:>6.2f} {overhead:>8.1f}s"
              f"   {c.get('rate', 0):>8.2f} {c.get('silence', 0):>8.1f}")

    print(f"\nTO LAND IN {band['min_seconds']:.0f}-{band['max_seconds']:.0f}s "
          f"(target {band['target_seconds']:.0f}), SPOKEN words needed:")
    for vtype in sorted(data):
        fitted = fit(data[vtype]) if len(data[vtype]) >= 4 else None
        if not fitted:
            continue
        rate, overhead = fitted
        need = (band["target_seconds"] - overhead) * rate
        lo = (band["min_seconds"] - overhead) * rate
        hi = (band["max_seconds"] - overhead) * rate
        print(f"  {vtype:14} {max(0, need):>5.0f}   (band {max(0, lo):>4.0f}-{max(0, hi):>4.0f})")


#: Silence the generator splices around ONE item, from its own constants --
#: not from the fit, which cannot see it. Every sample on disk is a one-item
#: video, so the fitted intercept folds this together with the per-video
#: overhead and a linear extrapolation to three items is wrong by two of these.
#:
#: MEASURED, NOT ADDED UP. This was 8.0, derived by listing the pauses that
#: looked per-item and calling the option block "per video". After 1af342d
#: the option block repeats per ITEM -- transition gap, four letter-to-word
#: gaps, three between-option gaps -- and so do the dramatic pre-answer
#: beat, the repeat-the-answer pause, and the gap between one item and the
#: next. Instrumenting generate_silence and generating 1, 2 and 3 item
#: quizzes gives 12.70 / 25.90 / 39.10 s of spliced silence: 13.20 s per
#: extra item, both times. At 8.0 a three-item quiz was predicted 10.4 s
#: short.
#:
#:      0.50  gap before this item (PAUSE_AFTER_EXPLANATION), items 2..n
#:      0.50  after the question
#:      0.40  after the transition line
#:      1.20  letter -> word, 4 x 0.30
#:      1.20  between options, 3 x 0.40
#:      0.60  after the option block
#:      1.50  after "piensa"
#:      4.50  countdown, 3 x 1.50, silent
#:      1.00  dramatic pause before the reveal
#:      ~0.90 before the repeated answer (_repeat_pause)
#:      0.40  after the answer
#:      0.50  after the explanation
#:
#: A re-FIT of `rate` and `overhead` is deliberately NOT done here: that
#: needs a batch of new videos on disk, and there is none yet. Two inputs
#: are waiting for it -- this constant, and pronunciation's rate 1.54 (n=12,
#: marked indicative), which predicted 77.5 s for pr002 against a real
#: 57.5 s.
PER_ITEM_SILENCE = 13.2


def predict(vtype: str, words: int, rate: float, overhead: float,
            items: int = 1) -> float:
    """Seconds for `items` items, splitting the fitted overhead honestly.

    The fitted `overhead` is what a ONE-item video carries, so it already
    contains one PER_ITEM_SILENCE. Everything else in it is per video: the
    "Escucha las opciones" transition, the option letter clips, the leading
    and trailing buffer. Adding items adds silence, and that is the term the
    regression could never learn.
    """
    fixed = max(0.0, overhead - PER_ITEM_SILENCE)
    return words / rate + fixed + items * PER_ITEM_SILENCE


if __name__ == "__main__":
    main()

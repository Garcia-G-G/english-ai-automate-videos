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


def spoken_words(script: dict) -> int:
    """Words this script's generator will actually send to the TTS.

    ITEMS-AWARE ON PURPOSE. The root-level question/statement/sentence is item
    one; items two and three live in the array the schema calls DEAD PAYLOAD
    and are spoken only once `items_spoken` says so. Reading the count from
    config means this measurement follows the pipeline instead of drifting
    behind it -- the day items_spoken becomes 3, the band it is judged against
    becomes true on its own, with nothing here to remember to change.
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
    wanted = _items_spoken(vtype)
    items = script.get(key) or []
    # item one is the root, already counted, so only the extras are added
    for item in items[1:wanted]:
        total += sum(_count(item.get(f)) for f in item_fields)
    return total


def samples():
    """(type, spoken_words, seconds) for every produced pair on disk."""
    out = collections.defaultdict(list)
    for audio in glob.glob(str(ROOT / "output/audio/*/*.json")):
        try:
            meta = json.load(open(audio, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        duration, vtype = meta.get("duration"), meta.get("type")
        if not duration or not vtype:
            continue
        script_path = ROOT / "output/scripts" / vtype / os.path.basename(audio)
        if not script_path.exists():
            continue
        try:
            script = json.load(open(script_path, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        n = spoken_words(script)
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
PER_ITEM_SILENCE = 8.0   # 0.5 question + 0.6 option + 1.5 think
                         # + 4.5 countdown (3 x 1.5, silent) + 0.4 answer
                         # + 0.5 explanation


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

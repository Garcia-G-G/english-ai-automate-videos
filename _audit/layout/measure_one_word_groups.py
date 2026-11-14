#!/usr/bin/env python3
"""One-word groups: what they are, and how long they are really on screen.

    python3 _audit/layout/measure_one_word_groups.py

Two corrections to the earlier reading are built in.

First, duration. The 0.44s figure quoted before was g['end'] - g['start'],
the AUDIO span of the group. What a viewer sees is display_end -
display_start, which video/v2/timing_engine.py derives separately and which
already enforces a floor of its own: a group never leaves before its last
word ends plus 350ms. So the audio span is not the on-screen time and cannot
be used to argue a card is unreadable.

Second, population. The samples looked like two kinds of thing — phonetic
notation that is plausibly a deliberate teaching beat, and ordinary words
that are simply alone. They are split structurally here: a token carrying a
slash, a leading hyphen or an internal hyphen is notation. Respellings
without any of those markers ("pleyd.") cannot be separated structurally and
are counted with the ordinary words, so the notation figure is a floor.
"""

import glob
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from animations.subtitle_processor import SubtitleProcessor  # noqa: E402
from video.educational import add_sentence_boundaries        # noqa: E402
from video.v2 import timing_engine as TE                     # noqa: E402

PATHS = sorted(glob.glob(str(ROOT / "output/audio/educational/*.json"))) + \
    sorted(glob.glob(str(ROOT / "output/step3_verify/edu*_FRESH.json")))

NOTATION = re.compile(r"[/]|^-|\w-\w")


def is_notation(text: str) -> bool:
    return bool(NOTATION.search(text.strip()))


def grouped():
    """Yield (group, display_seconds, audio_seconds) for every group."""
    for p in PATHS:
        try:
            d = json.load(open(p))
        except Exception:
            continue
        words = d.get('words') or []
        if len(words) <= 10 or not d.get('full_script') or d.get('english_phrases') is None:
            continue
        duration = d.get('duration') or (words[-1]['end'] + 1.0)
        whisper = [bool(x.get('is_english')) for x in words]
        ws = json.loads(json.dumps(words))
        for x, f in zip(ws, whisper):
            x['is_english'] = f
            x.pop('segment_id', None)
            x.pop('segment_end', None)
        groups = SubtitleProcessor().group_words(
            add_sentence_boundaries(ws, d['full_script']))
        try:
            groups = TE.compute_display_windows(
                groups, duration, content_end=max(0.0, duration - TE.CTA_LEN))
        except Exception:
            continue
        for g in groups:
            ds = g.get('display_start', g['start'])
            de = g.get('display_end', g['end'])
            yield g, de - ds, g['end'] - g['start']


def describe(label, vals):
    if not vals:
        print(f"   {label:22s} none")
        return
    vals = sorted(vals)
    print(f"   {label:22s} n={len(vals):4d}  min {vals[0]:4.2f}  p25 {vals[len(vals)//4]:4.2f}  "
          f"median {statistics.median(vals):4.2f}  p75 {vals[3*len(vals)//4]:4.2f}  max {vals[-1]:4.2f}")


def main():
    all_disp, one_disp, one_audio = [], [], []
    notation, ordinary = [], []
    multi_disp = []

    for g, disp, audio in grouped():
        all_disp.append(disp)
        if len(g['words']) == 1:
            one_disp.append(disp)
            one_audio.append(audio)
            (notation if is_notation(g['text']) else ordinary).append((g['text'], disp))
        else:
            multi_disp.append(disp)

    print(f"groups: {len(all_disp)}   one-word: {len(one_disp)} "
          f"({len(one_disp)/len(all_disp):.1%})")
    print()
    print("ON-SCREEN seconds (display_end - display_start), which is what a viewer gets:")
    describe("all groups", all_disp)
    describe("2+ word groups", multi_disp)
    describe("one-word groups", one_disp)
    print()
    print("AUDIO span for the same one-word groups, for contrast:")
    describe("one-word, audio", one_audio)
    print()
    print(f"one-word split: notation {len(notation)}  ordinary {len(ordinary)}")
    describe("notation on-screen", [d for _, d in notation])
    describe("ordinary on-screen", [d for _, d in ordinary])
    print(f"   notation tokens: {sorted({t for t, _ in notation})}")
    print()
    for floor in (0.8, 1.0):
        short = [d for d in one_disp if d < floor]
        short_all = [d for d in all_disp if d < floor]
        print(f"below {floor:.1f}s on screen:  one-word {len(short):3d}/{len(one_disp)} "
              f"({len(short)/len(one_disp):.0%})   all groups {len(short_all):3d}/{len(all_disp)} "
              f"({len(short_all)/len(all_disp):.0%})")


if __name__ == "__main__":
    main()

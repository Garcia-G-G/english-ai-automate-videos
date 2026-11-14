#!/usr/bin/env python3
"""6b step 1: how often does grouping cut in a bad place?

    python3 _audit/layout/measure_grouping.py

One bad frame is a bug report. This counts, over every educational fixture
with real word timestamps, how many groups:

  - lead or trail with a 1-2 character orphan
  - straddle a sentence boundary (. ? ! on a word that is not the last)
  - straddle a language switch (is_english changes inside the group)

The language column is computed against WHISPER'S flags, not the ones the
renderer ends up with. video/__init__.py rebuilds is_english from
english_phrases and drops any phrase longer than three words, so the flags
the grouper actually sees are not the flags the audio has. Both are
reported, because the gap between them is the finding.

Grouping is reached only from the educational branch of generate_video, so
there is nothing to report for the other five types.
"""

import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from animations.subtitle_processor import SubtitleProcessor  # noqa: E402
from tts_common import SPANISH_FILTER                        # noqa: E402
from video.educational import add_sentence_boundaries        # noqa: E402

SENT_END = ('.', '!', '?')


def sanitized_flags(words, english_phrases):
    """Exactly what video/__init__.py:229-262 does to is_english."""
    english_set = set()
    for phrase in english_phrases or []:
        pw = phrase.lower().split()
        if len(pw) > 3:                       # the filter that drops phrases
            continue
        for w in pw:
            c = re.sub(r'[^\w]', '', w)
            if any(ch in c for ch in 'áéíóúñü'):
                continue
            if c and c not in SPANISH_FILTER and len(c) > 1:
                english_set.add(c)
    out = []
    for w in words:
        c = re.sub(r'[^\w]', '', w['word']).lower()
        out.append(c in english_set)
    return out


def analyse(groups, truth_by_id):
    """Counts of the three defects over a list of groups."""
    lead = trail = sent = lang = 0
    for g in groups:
        ws = g['words']
        if not ws:
            continue
        first = ws[0]['word'].strip('.,!?¿¡:;\'"')
        last = ws[-1]['word'].strip('.,!?¿¡:;\'"')
        if len(ws) > 1 and 1 <= len(first) <= 2:
            lead += 1
        if len(ws) > 1 and 1 <= len(last) <= 2:
            trail += 1
        # a sentence terminator on any word that is not the last one
        if any(w['word'].rstrip().endswith(SENT_END) for w in ws[:-1]):
            sent += 1
        flags = [truth_by_id.get(id(w)) for w in ws]
        flags = [f for f in flags if f is not None]
        if len(set(flags)) > 1:
            lang += 1
    return lead, trail, sent, lang


def main():
    paths = sorted(glob.glob(str(ROOT / "output/audio/educational/*.json"))) + \
        sorted(glob.glob(str(ROOT / "output/step3_verify/edu*_FRESH.json")))

    tot = dict(files=0, groups=0, lead=0, trail=0, sent=0,
               lang_shipped=0, lang_truth=0, en_whisper=0, en_after=0, words=0)

    for p in paths:
        try:
            d = json.load(open(p))
        except Exception:
            continue
        words = d.get('words') or []
        if len(words) <= 10 or not d.get('full_script'):
            continue
        eph = d.get('english_phrases')
        if eph is None:
            continue

        whisper_flags = [bool(w.get('is_english')) for w in words]
        after = sanitized_flags(words, eph)

        # Group exactly as the renderer does: sanitized flags, then boundaries.
        for w, f in zip(words, after):
            w['is_english'] = f
        truth = {id(w): whisper_flags[i] for i, w in enumerate(words)}
        prepared = add_sentence_boundaries(words, d['full_script'])
        groups = SubtitleProcessor().group_words(prepared)

        lead, trail, sent, lang_truth = analyse(groups, truth)
        shipped = {id(w): bool(w.get('is_english')) for g in groups for w in g['words']}
        _, _, _, lang_shipped = analyse(groups, shipped)

        tot['files'] += 1
        tot['groups'] += len(groups)
        tot['lead'] += lead
        tot['trail'] += trail
        tot['sent'] += sent
        tot['lang_truth'] += lang_truth
        tot['lang_shipped'] += lang_shipped
        tot['en_whisper'] += sum(whisper_flags)
        tot['en_after'] += sum(after)
        tot['words'] += len(words)

    g = tot['groups'] or 1
    print(f"educational fixtures analysed : {tot['files']}")
    print(f"groups                        : {tot['groups']}")
    print()
    print(f"  leading 1-2 char orphan     : {tot['lead']:5d}  ({tot['lead']/g:.1%})")
    print(f"  trailing 1-2 char orphan    : {tot['trail']:5d}  ({tot['trail']/g:.1%})")
    print(f"  straddles a sentence end    : {tot['sent']:5d}  ({tot['sent']/g:.1%})")
    print(f"  straddles a language switch : {tot['lang_truth']:5d}  ({tot['lang_truth']/g:.1%})"
          f"   [by Whisper's flags]")
    print(f"                              : {tot['lang_shipped']:5d}  ({tot['lang_shipped']/g:.1%})"
          f"   [by the flags the grouper saw]")
    print()
    w = tot['words'] or 1
    print(f"  words flagged English by Whisper : {tot['en_whisper']:5d} / {tot['words']}"
          f"  ({tot['en_whisper']/w:.1%})")
    print(f"  still flagged after sanitize     : {tot['en_after']:5d} / {tot['words']}"
          f"  ({tot['en_after']/w:.1%})")
    lost = tot['en_whisper'] - tot['en_after']
    if tot['en_whisper']:
        print(f"  lost by the >3-word phrase filter: {lost:5d}"
              f"  ({lost/tot['en_whisper']:.0%} of Whisper's English words)")


if __name__ == "__main__":
    main()

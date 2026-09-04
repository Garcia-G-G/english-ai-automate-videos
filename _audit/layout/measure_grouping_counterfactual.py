#!/usr/bin/env python3
"""6b step 2: what would grouping do with Whisper's flags left alone?

    python3 _audit/layout/measure_grouping_counterfactual.py

MEASUREMENT OF A HYPOTHETICAL. Nothing here changes what ships. It runs
group_words twice over the same corpus:

  today          is_english rebuilt from english_phrases, dropping any
                 phrase longer than three words — what the renderer does
  counterfactual is_english exactly as Whisper produced it

and reports the same four rates for each. The English branch at
subtitle_processor.py:303 explicitly pulls one or two preceding Spanish words
into an English group as a prefix, so if the flags survive it should move the
leading-orphan rate and the language-straddle rate together. If only one
moves, the orphan case needs its own rule.

Both columns score the language straddle against WHISPER's flags, because
that is the ground truth of what the audio does; scoring "today" against its
own blanked flags would flatter it.
"""

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from animations.subtitle_processor import SubtitleProcessor  # noqa: E402
from measure_grouping import sanitized_flags                 # noqa: E402
from video.educational import add_sentence_boundaries        # noqa: E402

SENT_END = ('.', '!', '?')


def rates(groups, truth):
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
        if any(w['word'].rstrip().endswith(SENT_END) for w in ws[:-1]):
            sent += 1
        flags = [truth[id(w)] for w in ws if id(w) in truth]
        if len(set(flags)) > 1:
            lang += 1
    return lead, trail, sent, lang


def main():
    paths = sorted(glob.glob(str(ROOT / "output/audio/educational/*.json"))) + \
        sorted(glob.glob(str(ROOT / "output/step3_verify/edu*_FRESH.json")))

    acc = {'today': [0, 0, 0, 0], 'counter': [0, 0, 0, 0]}
    n_groups = {'today': 0, 'counter': 0}
    files = 0

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
        files += 1

        whisper = [bool(w.get('is_english')) for w in words]
        after = sanitized_flags(words, eph)

        for mode, flags in (('today', after), ('counter', whisper)):
            ws = json.loads(json.dumps(words))       # fresh copy per run
            for w, f in zip(ws, flags):
                w['is_english'] = f
                w.pop('segment_id', None)
                w.pop('segment_end', None)
            truth = {id(w): whisper[i] for i, w in enumerate(ws)}
            groups = SubtitleProcessor().group_words(
                add_sentence_boundaries(ws, d['full_script']))
            r = rates(groups, truth)
            acc[mode] = [a + b for a, b in zip(acc[mode], r)]
            n_groups[mode] += len(groups)

    labels = ['leading 1-2 char orphan', 'trailing 1-2 char orphan',
              'straddles a sentence end', 'language straddle (Whisper)']
    gt = n_groups['today'] or 1
    gc = n_groups['counter'] or 1

    print(f"educational fixtures : {files}")
    print(f"groups               : today {n_groups['today']}   "
          f"counterfactual {n_groups['counter']}")
    print()
    print(f"{'':30s} {'today':>16s} {'counterfactual':>16s} {'delta':>11s}")
    print("-" * 78)
    for i, lab in enumerate(labels):
        a = acc['today'][i] / gt
        b = acc['counter'][i] / gc
        print(f"{lab:30s} {acc['today'][i]:5d} {a:8.1%} "
              f"{acc['counter'][i]:5d} {b:8.1%} {100*(b-a):+8.1f} pp")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""max_words_per_group at 8, 6 and 4, with the English flags restored.

    python3 _audit/layout/measure_max_words.py

max_words went 4 -> 8 in de81e7f, the same commit that added the >3-word
english_phrases filter, for the reason in its subject line: "text grouping
too small". Part of why grouping looked too small is that the English branch
never fired, so runs of English were chopped by the word counter instead of
being kept whole. Removing the filter changes that input, so 8 has to earn
its place again rather than be inherited.

Reported with the decomposition, because the aggregate straddle rate hides
the thing that matters: whether a straddle is the deliberate Spanish-prefix
shape or a cut through the middle of a phrase.
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
PATHS = sorted(glob.glob(str(ROOT / "output/audio/educational/*.json"))) + \
    sorted(glob.glob(str(ROOT / "output/step3_verify/edu*_FRESH.json")))


def fixtures():
    for p in PATHS:
        try:
            d = json.load(open(p))
        except Exception:
            continue
        w = d.get('words') or []
        if len(w) <= 10 or not d.get('full_script') or d.get('english_phrases') is None:
            continue
        yield d


def run(max_words, use_whisper_flags):
    n = lead = trail = sent = 0
    es_en = en_es = multi = 0
    sizes = []
    for d in fixtures():
        words = d['words']
        whisper = [bool(x.get('is_english')) for x in words]
        flags = whisper if use_whisper_flags else sanitized_flags(words, d['english_phrases'])
        ws = json.loads(json.dumps(words))
        for x, f in zip(ws, flags):
            x['is_english'] = f
            x.pop('segment_id', None)
            x.pop('segment_end', None)
        truth = {id(x): whisper[i] for i, x in enumerate(ws)}
        groups = SubtitleProcessor(max_words_per_group=max_words).group_words(
            add_sentence_boundaries(ws, d['full_script']))
        for g in groups:
            gw = g['words']
            if not gw:
                continue
            n += 1
            sizes.append(len(gw))
            first = gw[0]['word'].strip('.,!?¿¡:;\'"')
            last = gw[-1]['word'].strip('.,!?¿¡:;\'"')
            if len(gw) > 1 and 1 <= len(first) <= 2:
                lead += 1
            if len(gw) > 1 and 1 <= len(last) <= 2:
                trail += 1
            if any(x['word'].rstrip().endswith(SENT_END) for x in gw[:-1]):
                sent += 1
            fs = [truth[id(x)] for x in gw if id(x) in truth]
            if len(set(fs)) < 2:
                continue
            tr = [(a, b) for a, b in zip(fs, fs[1:]) if a != b]
            if len(tr) == 1 and tr[0] == (False, True):
                es_en += 1
            elif len(tr) == 1 and tr[0] == (True, False):
                en_es += 1
            else:
                multi += 1
    avg = sum(sizes) / len(sizes) if sizes else 0
    return dict(groups=n, lead=lead, trail=trail, sent=sent,
                es_en=es_en, en_es=en_es, multi=multi, avg=avg,
                bad=en_es + multi)


def main():
    rows = [("today (filter on, mw=8)", run(8, False))]
    for mw in (8, 6, 4):
        rows.append((f"filter off, mw={mw}", run(mw, True)))

    print(f"{'':26s} {'groups':>7s} {'avg n':>6s} {'lead':>8s} {'trail':>8s} "
          f"{'sent':>6s} {'ES>EN':>7s} {'EN>ES':>7s} {'multi':>7s} {'BAD':>8s}")
    print("-" * 100)
    for label, r in rows:
        g = r['groups'] or 1
        print(f"{label:26s} {r['groups']:7d} {r['avg']:6.1f} "
              f"{r['lead']:4d}{r['lead']/g:6.1%} {r['trail']:4d}{r['trail']/g:6.1%} "
              f"{r['sent']:6d} {r['es_en']:7d} {r['en_es']:7d} {r['multi']:7d} "
              f"{r['bad']:4d}{r['bad']/g:5.1%}")
    print()
    print("BAD = EN>ES tail + 2-or-more transitions, i.e. groups that cut")
    print("      through a language change rather than prefixing one.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Would pulling a leading orphan back to the previous group work?

    python3 _audit/layout/measure_orphan_rule.py

SIMULATION ONLY. Nothing here changes what ships.

127 leading orphans survive the flag fix by design — the English branch
promotes a one- or two-word group to a PREFIX on the following English run,
which trades an orphan group for an orphan at the head of a group. Another
128 sit inside pure Spanish and no language rule touches them.

The obvious rule is: never start a group with a 1-2 character word, move it
to the end of the previous group. Its cost is that the previous group grows,
and max_words is what stops groups growing, so the two rules fight. Three
variants are measured:

  unguarded   always pull back
  guarded     pull back only if the previous group has room under max_words
  guarded+1   pull back if the previous group would land at max_words + 1,
              i.e. allow a single word of overflow to buy an orphan

A pull-back is never made across a segment boundary, because that is the one
boundary grouping already gets right and it is not worth spending.
"""

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from animations.subtitle_processor import SubtitleProcessor  # noqa: E402
from video.educational import add_sentence_boundaries        # noqa: E402

SENT_END = ('.', '!', '?')
MAX_WORDS = 8
PATHS = sorted(glob.glob(str(ROOT / "output/audio/educational/*.json"))) + \
    sorted(glob.glob(str(ROOT / "output/step3_verify/edu*_FRESH.json")))


def is_orphan(word):
    w = word['word'].strip('.,!?¿¡:;\'"')
    return 1 <= len(w) <= 2


def pull_back(groups, mode):
    """Move a leading 1-2 char word onto the previous group, per `mode`."""
    moved = overflow = blocked = 0
    out = [dict(g, words=list(g['words'])) for g in groups]
    for i in range(1, len(out)):
        cur, prev = out[i], out[i - 1]
        if len(cur['words']) < 2 or not is_orphan(cur['words'][0]):
            continue
        if not prev['words']:
            continue
        # never across a sentence: the previous group ends one
        if prev['words'][-1]['word'].rstrip().endswith(SENT_END):
            blocked += 1
            continue
        if prev['words'][-1].get('segment_id') != cur['words'][0].get('segment_id'):
            blocked += 1
            continue
        room = len(prev['words']) < MAX_WORDS
        if mode == 'guarded' and not room:
            blocked += 1
            continue
        if mode == 'guarded1' and len(prev['words']) > MAX_WORDS:
            blocked += 1
            continue
        prev['words'].append(cur['words'].pop(0))
        moved += 1
        if len(prev['words']) > MAX_WORDS:
            overflow += 1
    out = [g for g in out if g['words']]
    for g in out:
        g['text'] = ' '.join(w['word'] for w in g['words'])
        g['start'] = g['words'][0]['start']
        g['end'] = g['words'][-1]['end']
    return out, moved, overflow, blocked


def rates(groups, truth):
    lead = trail = es_en = en_es = multi = 0
    sizes = []
    for g in groups:
        gw = g['words']
        sizes.append(len(gw))
        if len(gw) > 1 and is_orphan(gw[0]):
            lead += 1
        if len(gw) > 1 and is_orphan(gw[-1]):
            trail += 1
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
    return dict(groups=len(groups), lead=lead, trail=trail,
                es_en=es_en, bad=en_es + multi,
                avg=sum(sizes) / len(sizes) if sizes else 0,
                over=sum(1 for s in sizes if s > MAX_WORDS),
                biggest=max(sizes) if sizes else 0)


def main():
    acc = {}
    counters = {}
    for mode in ('none', 'unguarded', 'guarded', 'guarded1'):
        acc[mode] = None
        counters[mode] = [0, 0, 0]

    for p in PATHS:
        try:
            d = json.load(open(p))
        except Exception:
            continue
        words = d.get('words') or []
        if len(words) <= 10 or not d.get('full_script') or d.get('english_phrases') is None:
            continue
        whisper = [bool(x.get('is_english')) for x in words]
        ws = json.loads(json.dumps(words))
        for x, f in zip(ws, whisper):
            x['is_english'] = f
            x.pop('segment_id', None)
            x.pop('segment_end', None)
        truth = {id(x): whisper[i] for i, x in enumerate(ws)}
        base = SubtitleProcessor().group_words(add_sentence_boundaries(ws, d['full_script']))

        for mode in acc:
            groups = base if mode == 'none' else pull_back(base, mode)[0]
            if mode != 'none':
                _, m, o, b = pull_back(base, mode)
                counters[mode][0] += m
                counters[mode][1] += o
                counters[mode][2] += b
            r = rates(groups, truth)
            if acc[mode] is None:
                acc[mode] = {k: 0 for k in r}
                acc[mode]['_n'] = 0
            for k, v in r.items():
                acc[mode][k] += v
            acc[mode]['_n'] += 1

    print(f"{'variant':12s} {'groups':>7s} {'avg':>5s} {'lead orphan':>14s} "
          f"{'trail orphan':>14s} {'BAD':>5s} {'>8 words':>9s} {'max':>4s}")
    print("-" * 82)
    for mode in ('none', 'unguarded', 'guarded', 'guarded1'):
        a = acc[mode]
        g = a['groups'] or 1
        n = a['_n'] or 1
        print(f"{mode:12s} {a['groups']:7d} {a['avg']/n:5.1f} "
              f"{a['lead']:5d}{a['lead']/g:8.1%} {a['trail']:5d}{a['trail']/g:8.1%} "
              f"{a['bad']:5d} {a['over']:9d} {a['biggest']//n if n else 0:4d}")
    print()
    print(f"{'variant':12s} {'pulled back':>12s} {'caused >8':>10s} {'blocked':>9s}")
    print("-" * 46)
    for mode in ('unguarded', 'guarded', 'guarded1'):
        m, o, b = counters[mode]
        print(f"{mode:12s} {m:12d} {o:10d} {b:9d}")


if __name__ == "__main__":
    main()

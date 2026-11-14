#!/usr/bin/env python3
"""Does english_phrases still leak Spanish, now that the scraper is fixed?

    python3 _audit/layout/measure_english_phrases.py

The >3-word filter in video/__init__.py was added by de81e7f (2026-03-24)
with the reason "Skip phrases with 4+ words in english_phrases (likely
Spanish sentences)". d14a28b (2026-07-30) fixed the scraper at its root — the
apostrophe desync that made it capture the Spanish narration between phrases.

If the source is clean now, the filter costs 73% of the English flags and
buys nothing. If it still leaks, the filter is load-bearing and 6b is a
different job. Split at the scraper fix so the two populations are visible
separately.

"Spanish" here is a strict majority of stoplist tokens, the same test the
fixed scraper settled on, with ties resolving to English for the reason
recorded in that commit: several stoplist words are ambiguous across both
languages and rejecting on a tie throws out the two-word lesson phrases the
pipeline exists to teach.
"""

import glob
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tts_common import SPANISH_FILTER  # noqa: E402

SCRAPER_FIX = datetime(2026, 7, 30, 12, 45).timestamp()
STAMP = re.compile(r"_(\d{8})_(\d{6})")


def fixture_time(path: str) -> float:
    """Prefer the timestamp in the filename; fall back to mtime."""
    m = STAMP.search(os.path.basename(path))
    if m:
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
        except ValueError:
            pass
    return os.path.getmtime(path)


def looks_spanish(phrase: str) -> bool:
    toks = [re.sub(r"[^\w]", "", w).lower() for w in phrase.split()]
    toks = [t for t in toks if t]
    if not toks:
        return False
    if any(ch in phrase.lower() for ch in "áéíóúñü¿¡"):
        return True
    es = sum(1 for t in toks if t in SPANISH_FILTER)
    return es > len(toks) - es          # strict majority, ties -> English


def main():
    seen = {}
    for p in glob.glob(str(ROOT / "output/scripts/educational/*.json")) + \
             glob.glob(str(ROOT / "output/audio/educational/*.json")) + \
             glob.glob(str(ROOT / "output/step3_verify/edu*_FRESH.json")):
        try:
            d = json.load(open(p))
        except Exception:
            continue
        ep = d.get("english_phrases")
        if not ep:
            continue
        seen.setdefault(os.path.basename(p), (fixture_time(p), ep))

    for label, keep in (("BEFORE the scraper fix (< 2026-07-30)", lambda t: t < SCRAPER_FIX),
                        ("AFTER  the scraper fix (>= 2026-07-30)", lambda t: t >= SCRAPER_FIX)):
        rows = [(n, ep) for n, (t, ep) in seen.items() if keep(t)]
        total = sum(len(ep) for _, ep in rows)
        long_ = [x for _, ep in rows for x in ep if len(x.split()) > 3]
        span = [x for _, ep in rows for x in ep if looks_spanish(x)]
        span_long = [x for x in long_ if looks_spanish(x)]
        print(f"── {label} ──")
        print(f"   fixtures {len(rows):3d}   phrases {total:4d}")
        if total:
            print(f"   >3 words        : {len(long_):4d}  ({len(long_)/total:.0%}) "
                  f"— these are what the filter discards")
            print(f"   look Spanish    : {len(span):4d}  ({len(span)/total:.0%})")
            print(f"   >3 AND Spanish  : {len(span_long):4d}  "
                  f"— the only phrases the filter is actually FOR")
            for x in span[:6]:
                print(f"       Spanish leak: {x!r}")
        print()


if __name__ == "__main__":
    main()

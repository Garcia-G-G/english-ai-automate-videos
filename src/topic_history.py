#!/usr/bin/env python3
"""Which topics have already been made into videos, and how often.

    from topic_history import usage_counts, coverage
    usage_counts()               -> Counter{("social", "so008"): 22, ...}
    coverage(["pronunciation"])  -> {"total": 56, "used": 9, "unused": 47, ...}

WHY THIS EXISTS. Garcia: "ya se me han repetido como 4 videos con el mismo
tema". Measured over every script on disk when he said it:

    720 topics on disk
    178 ever used (25%)          542 never touched (75%)
    164 of those 178 used more than once
    social/so008 "Giving Compliments" used 22 TIMES

Nothing in the codebase remembered anything. A grep for used_topic,
topic_history, exclude_topic and seen_topic returned no hits: every video drew
from all 720 as if it were the first.

THE RECORD IS THE SCRIPTS, not a new ledger file. script_generator stamps
`_meta.topic_id` and `_meta.category` on everything it writes
(script_generator.py:1107), so the history already exists and cannot drift from
what was actually generated. A separate counter file would be a second source
of truth for a fact the first one already holds — and this repo has paid for
that mistake before.

It counts GENERATED, not published. A topic whose video was rejected still
burned that topic's novelty for the audience only if it shipped, but it burned
the generation cost either way, and re-drawing it is what Garcia is seeing.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "output" / "scripts"

#: THE SECOND PLACE A PRODUCED SCRIPT LANDS, and the reason this module was
#: half blind. `run_pipeline_with_tracking` writes to output/scripts/; the
#: Studio door (main.py --script, --batch, --workspace) writes the script
#: inside the artifact and NOWHERE ELSE. So an owner-supplied script -- the
#: whole queue route -- produced a video this module could not see, and the
#: topic stayed "unused" forever. Counting one root was counting one door.
ARTIFACTS_DIR = ROOT / "output" / "artifacts"

#: Scripts waiting to be produced. NOT usage: a queued topic has not been made
#: into anything yet. Named here so the queue guard and this module agree on
#: where the queue lives instead of each holding its own copy.
QUEUE_DIR = ROOT / "content" / "queue"

#: (category, topic_id)
TopicKey = Tuple[str, str]


def usage_counts(scripts_dir: Path = None) -> Counter:
    """How many times each topic has been generated.

    Never raises. A malformed or unreadable script is skipped with a log line
    rather than taking down a generation run — the history is an optimisation,
    and a video must not fail because an old file on disk is broken.
    """
    if scripts_dir is not None:
        roots = [Path(scripts_dir)]
    else:
        roots = [SCRIPTS_DIR, ARTIFACTS_DIR]

    counts: Counter = Counter()
    # A script that lands in BOTH roots must not count twice. The two doors do
    # not overlap today, so this is a guard rather than a fix -- and a guard is
    # cheap next to a repeat the owner sees on screen.
    seen: set = set()

    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            try:
                with open(path, encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:                                   # noqa: BLE001
                logger.debug("topic_history: could not read %s", path)
                continue
            if not isinstance(data, dict):
                continue
            meta = data.get("_meta") or {}
            topic_id = meta.get("topic_id")
            category = meta.get("category")
            if not topic_id or not category or topic_id == "unknown":
                continue
            fingerprint = (str(category), str(topic_id),
                           str(meta.get("generated_at") or path.name))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            counts[(str(category), str(topic_id))] += 1
    return counts


def coverage(allowed_categories: Optional[Iterable[str]] = None,
             scripts_dir: Path = None) -> Dict:
    """Used / unused across the topic files, optionally within a category set.

    Shaped for a screen: totals first, then the per-category rows a dashboard
    would list, then the repeat offenders — which are the ones that answer
    "why do I keep seeing the same video".
    """
    from script_generator import list_categories, load_topics

    cats = list(allowed_categories) if allowed_categories else list_categories()
    counts = usage_counts(scripts_dir)

    rows: List[Dict] = []
    total = used = 0
    for category in sorted(cats):
        try:
            topics = load_topics(category)
        except Exception:                                       # noqa: BLE001
            logger.warning("topic_history: no topic file for %r", category)
            continue
        ids = [str(t.get("id")) for t in topics if t.get("id")]
        seen = sum(1 for i in ids if counts.get((category, i)))
        total += len(ids)
        used += seen
        rows.append({
            "category": category,
            "total": len(ids),
            "used": seen,
            "unused": len(ids) - seen,
        })

    repeats = sorted(
        ({"category": c, "topic_id": i, "times": n}
         for (c, i), n in counts.items() if n > 1 and c in set(cats)),
        key=lambda r: -r["times"],
    )

    return {
        "total": total,
        "used": used,
        "unused": total - used,
        "by_category": rows,
        "repeats": repeats,
    }


def partition(pool: List[Tuple[str, dict]],
              counts: Counter = None) -> Tuple[List, List]:
    """Split a flat (category, topic) pool into never-used and used.

    Returns (fresh, stale). `stale` is ordered least-used first, so a caller
    that has exhausted the fresh list still degrades to the topic seen least
    rather than to a uniform draw that can hand back the one seen 22 times.
    """
    counts = usage_counts() if counts is None else counts
    fresh, stale = [], []
    for category, topic in pool:
        key = (str(category), str(topic.get("id", "")))
        n = counts.get(key, 0)
        (fresh if n == 0 else stale).append((n, category, topic))
    stale.sort(key=lambda row: row[0])
    return ([(c, t) for _, c, t in fresh],
            [(c, t) for _, c, t in stale])

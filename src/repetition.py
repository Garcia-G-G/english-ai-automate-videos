"""STEP 81 §0.1: a how_do_you_say / phrases_level script may not repeat more than MAX_REPEATS English
items already published (content/queue/_done) or queued ahead of it, compared case-insensitively.

«Ahead of it» is name order: of two queued scripts that overlap, the later one is the repeat, so the
first stays producible. Enforced by tools/queue_guard.py (queue time), jobs.py (generation time).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
QUEUE_DIR = ROOT / "content" / "queue"
DONE_DIR = QUEUE_DIR / "_done"
GUARDED = ("how_do_you_say", "phrases_level")
MAX_REPEATS = 3
SHELVES = ("_done", "_skipped", "_rewrite", "hecho_con_claude")


def words(data: dict) -> Set[str]:
    """The lowercase English items of a guarded script (empty for any other)."""
    if (data or {}).get("type") not in GUARDED:
        return set()
    return {str(i.get("english", "")).strip().lower() for i in data.get("items") or [] if i.get("english")}


def _read(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def corpus(vtype: str, queue_dir: Path = None, done_dir: Path = None) -> List[Tuple[Path, Set[str], bool]]:
    """[(path, words, published)] of every script of this type: published first, then queued by name."""
    queue_dir, done_dir = queue_dir or QUEUE_DIR, done_dir or DONE_DIR
    out = []
    if done_dir.exists():
        for p in sorted(done_dir.rglob("*.json")):
            d = _read(p)
            if d.get("type") == vtype:
                out.append((p, words(d), True))
    if queue_dir.exists():
        for p in sorted(queue_dir.rglob("*.json")):
            if set(p.relative_to(queue_dir).parts[:-1]) & set(SHELVES):
                continue
            d = _read(p)
            if d.get("type") == vtype:
                out.append((p, words(d), False))
    return out


def repeated(data: dict, path: Optional[Path] = None, known: Optional[list] = None) -> List[str]:
    """The words this script repeats from published scripts and from queued ones that sort before
    it. `known` is a precomputed corpus (one per audit); `path` is this script's own file."""
    mine = words(data)
    if not mine:
        return []
    known = known if known is not None else corpus(data["type"])
    hit: Set[str] = set()
    for p, ws, published in known:
        if path is not None and p.resolve() == Path(path).resolve():
            continue
        if not published and path is not None and p.name >= Path(path).name:
            continue                                   # a queued script after this one is the repeat, not this
        hit |= mine & ws
    return sorted(hit)


def problem(data: dict, path: Optional[Path] = None, known: Optional[list] = None) -> Optional[str]:
    hit = repeated(data, path, known)
    if len(hit) > MAX_REPEATS:
        return (f"REPEATS WORDS: {len(hit)} of its {len(words(data))} English items are already published or "
                f"queued ahead (max {MAX_REPEATS}): {', '.join(hit)}")
    return None

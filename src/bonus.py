"""STEP 81 §3.1: a one-word question at the end of every how_do_you_say / phrases_level Short.

«Bonus: ¿cómo se dice "puerta"? Escríbelo en los comentarios.» The Spanish word is one that is NOT in the
list: `_meta.bonus` (a Spanish word, with `_meta.bonus_answer` for the English) if the script has it, else
the first item of the next queued sequel, else the curated `bonus_words` in config.yaml (Spanish: English).
The line is appended to the script's outro at render time, so Garcia's click voices it under the
per-video cap; the chosen pair is kept in `_meta.bonus_used` so the comments page can confirm the answer.
"""
from __future__ import annotations

import copy
import zlib
from typing import Dict, List, Optional, Tuple

GUARDED = ("how_do_you_say", "phrases_level")
MARKER = "Bonus:"


def line(spanish: str) -> str:
    return f'{MARKER} ¿cómo se dice "{spanish}"? Escríbelo en los comentarios.'


def _spanish_and_english(script: Dict) -> set:
    out = set()
    for i in script.get("items") or []:
        out |= {str(i.get("spanish", "")).strip().lower(), str(i.get("english", "")).strip().lower()}
    return out


def pick(script: Dict, queued: List[Dict], curated: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """(spanish, english) for the bonus question, or None when nothing fits."""
    meta = script.get("_meta") or {}
    have = _spanish_and_english(script)
    if meta.get("bonus"):
        return str(meta["bonus"]), str(meta.get("bonus_answer") or "")
    for q in queued:
        if (q.get("_meta") or {}).get("sequel_of") and q is not script:
            for i in q.get("items") or []:
                es, en = str(i.get("spanish", "")).strip(), str(i.get("english", "")).strip()
                if es and en and es.lower() not in have and en.lower() not in have:
                    return es, en
    options = [(es, en) for es, en in sorted(curated.items()) if es.lower() not in have and en.lower() not in have]
    if not options:
        return None
    return options[zlib.crc32(str(meta.get("topic_id") or script.get("theme") or "").encode()) % len(options)]


def apply(script: Dict, queued: Optional[List[Dict]] = None, curated: Optional[Dict[str, str]] = None) -> Dict:
    """The script with the bonus line at the end of its outro (a copy). Unchanged for other types, when it
    already has the line, or when no word fits."""
    if script.get("type") not in GUARDED or MARKER in str(script.get("outro") or ""):
        return script
    if curated is None:
        import queue_priority
        curated = queue_priority._config().get("bonus_words") or {}
    found = pick(script, queued or [], curated)
    if not found:
        return script
    out = copy.deepcopy(script)
    out["outro"] = f"{str(out.get('outro') or '').rstrip()} {line(found[0])}".strip()
    out.setdefault("_meta", {})["bonus_used"] = {"es": found[0], "en": found[1]}
    if out.get("full_script"):
        out["full_script"] = f"{out['full_script'].rstrip()} {line(found[0])}"
    return out

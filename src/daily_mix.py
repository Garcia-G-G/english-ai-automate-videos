"""STEP 81 §1.3: the day's upload mix. At most 4 uploads a day: 3 from how_do_you_say (sequels included)
and 1 «other». The other slot rotates: phrases_level, then the comic «RETO» series (hecho_con_claude), then a
level_test on a tier-A topic; grammar formats only take a slot nobody else can fill.

Pure functions over the ledger rows; jobs.next_best reads them to choose what to make next.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Optional

MAX_PER_DAY = 4
MAIN_TYPE = "how_do_you_say"
MAIN_SLOTS = 3
OTHER_ROTATION = ("phrases_level", "hecho_con_claude", "level_test")
GRAMMAR = ("choose_level", "fill_level", "true_false_level", "true_false", "fill_blank")


def uploads_on(rows: Iterable[Dict], day: date, platform: str = "youtube") -> List[str]:
    """The video types published on `day` to `platform`, from ledger rows."""
    return [str(r.get("video_type") or "") for r in rows
            if r.get("platform") == platform and str(r.get("published_at") or "")[:10] == day.isoformat()]


def next_slot(types_today: List[str], other_done: int = 0) -> Dict:
    """{slot: main|other|full, types: [type, ...] in order of preference, tier_a_only: bool}.
    `other_done` is how many «other» uploads the channel has made in all: it drives the rotation."""
    main = sum(1 for t in types_today if t == MAIN_TYPE)
    if len(types_today) >= MAX_PER_DAY:
        return {"slot": "full", "types": [], "tier_a_only": False}
    if main < MAIN_SLOTS:
        return {"slot": "main", "types": [MAIN_TYPE], "tier_a_only": False}
    k = other_done % len(OTHER_ROTATION)
    order = list(OTHER_ROTATION[k:] + OTHER_ROTATION[:k]) + list(GRAMMAR)
    return {"slot": "other", "types": order, "tier_a_only": True}


def explain(plan: Dict) -> str:
    if plan["slot"] == "full":
        return "Hoy ya hay 4 subidas: el siguiente hueco es mañana."
    if plan["slot"] == "main":
        return "Hueco de hoy: «Cómo se dice» (3 de las 4 subidas del día)."
    return "Hueco de hoy: «otro» (1 de las 4): " + ", ".join(plan["types"][:3]) + "."

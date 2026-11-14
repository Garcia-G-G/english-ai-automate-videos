"""STEP 82 §4: Tablero against the notebook, a measured switch.

Tablero is the default for «¿Cómo se dice…?». Until `design_ab.until`, 1 of every `control_every`
NEW topics keeps the notebook as a control; a topic keeps the design it was first given, so a
re-render stays in its group. Each assignment is one line of output/stats/design_ab.jsonl;
channel_stats copies the group onto every published video and «Rendimiento» compares them within
topic tier A once each group has MIN_PER_GROUP videos older than MATURE_DAYS.

shortcut: «views at day 3» is the video's current views (the snapshot keeps no per-day series);
fine while both groups are compared at the same age filter, upgrade if a daily series is stored.
"""
from __future__ import annotations

import json
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
AB_LOG = ROOT / "output" / "stats" / "design_ab.jsonl"
AB_TYPE = "how_do_you_say"
TABLERO, CUADERNO = "tablero", "cuaderno"
MIN_PER_GROUP = 6
MATURE_DAYS = 3
LOSS = 0.20                  # Tablero below the notebook by more than this is a loss


def settings() -> Dict:
    import queue_priority
    cfg = queue_priority._config().get("design_ab") or {}
    return {"enabled": bool(cfg.get("enabled", True)), "control_every": max(2, int(cfg.get("control_every", 4))),
            "until": str(cfg.get("until", "2026-11-26"))}


def _rows() -> List[Dict]:
    if not AB_LOG.exists():
        return []
    out = []
    for line in AB_LOG.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _topic(script: Dict) -> str:
    return (script.get("theme") or script.get("topic_id") or "").strip().lower()


def assign(artifact: str, script: Dict, today: Optional[date] = None) -> Optional[Dict]:
    """This render's design, logged: {variant, why}. None outside the type."""
    if script.get("type") != AB_TYPE or not script.get("items"):
        return None
    cfg, rows, topic = settings(), _rows(), _topic(script)
    earlier = next((r for r in reversed(rows) if r.get("topic") == topic), None)
    if earlier:
        out = {"variant": earlier["variant"], "why": "el tema ya tenía diseño"}
    elif not cfg["enabled"] or (today or date.today()).isoformat() > cfg["until"]:
        out = {"variant": TABLERO, "why": "control terminado"}
    else:
        turn = len({r.get("topic") for r in rows})
        control = (turn + 1) % cfg["control_every"] == 0
        out = {"variant": CUADERNO if control else TABLERO,
               "why": f"tema nuevo n.º {turn + 1}" + (": control" if control else "")}
    AB_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AB_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"artifact": artifact, "topic": topic, **out,
                            "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")
    return out


def variants() -> Dict[str, str]:
    return {r["artifact"]: r["variant"] for r in _rows() if r.get("artifact") and r.get("variant")}


def compare(videos: List[Dict]) -> Dict:
    """Median views and % viewed per design, tier A topics only. `loses` once ready when Tablero's
    median views fall more than LOSS under the notebook's."""
    import queue_priority
    cfg = queue_priority.settings()
    groups: Dict[str, List[Dict]] = {TABLERO: [], CUADERNO: []}
    for v in videos:
        g = v.get("design_variant")
        if g in groups and (v.get("days") or 0) > MATURE_DAYS \
                and queue_priority.a1_word({"title": v.get("title")}, cfg):
            groups[g].append(v)

    def med(values):
        values = [x for x in values if x is not None]
        return round(statistics.median(values), 1) if values else None

    out = {g: {"n": len(vs), "views": med([int(v.get("views", 0)) for v in vs]),
               "viewed_pct": med([v.get("avg_view_pct") for v in vs])} for g, vs in groups.items()}
    ready = all(len(vs) >= MIN_PER_GROUP for vs in groups.values())
    t, c = out[TABLERO]["views"], out[CUADERNO]["views"]
    return {"ready": ready, "groups": out, "loses": bool(ready and t is not None and c and t < c * (1 - LOSS))}

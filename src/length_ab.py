"""The short «¿Cómo se dice…?» A/B (owner, 2026-10-28): 5 words instead of 10, no recap.

The most-viewed Shorts on our topics across YouTube run 11-23 s (market_research); ours run ~76 s.
Every other NEW topic gets the short variant; a topic keeps the variant it was first given, so a
re-render after a gate reject stays in its group. The page still shows the whole list from frame 1.

Measured 2026-10-28 on a real render: an item is ~5.1 s (Spanish 0.9 + think 1.8 + English twice
2.0 + gap 0.4), so 5 words are ~25 s on their own and the short video is ~33 s plus the 4 s end
card. Getting to ~20 s would mean a shorter think or one English take: config.yaml `length_ab`.

Each assignment is one line of output/stats/length_ab.jsonl; channel_stats copies the group onto
every published video and «Rendimiento» compares views and average % viewed once each group has
MIN_PER_GROUP videos older than MATURE_DAYS.
"""

from __future__ import annotations

import copy
import json
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
AB_LOG = ROOT / "output" / "stats" / "length_ab.jsonl"
AB_TYPE = "how_do_you_say"
SHORT, LONG = "short", "long"
MIN_PER_GROUP = 8
MATURE_DAYS = 3

#: Number words the long script says about its own length («Reto rápido: diez palabras»).
_TEN = re.compile(r"\b(diez|10)\b", re.I)


def settings() -> Dict:
    import queue_priority
    cfg = queue_priority._config().get("length_ab") or {}
    return {"enabled": bool(cfg.get("enabled", True)), "short_items": int(cfg.get("short_items", 5))}


def _log_rows() -> List[Dict]:
    if not AB_LOG.exists():
        return []
    rows = []
    for line in AB_LOG.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _topic(script: Dict) -> str:
    return (script.get("theme") or script.get("topic_id") or "").strip().lower()


def assign(artifact: str, script: Dict) -> Optional[Dict]:
    """This render's group, logged: {variant, why}. None outside the A/B (another type, or off).
    A topic seen before keeps its group; a new one takes the turn (short first, then long…)."""
    if script.get("type") != AB_TYPE or not script.get("items") or not settings()["enabled"]:
        return None
    rows, topic = _log_rows(), _topic(script)
    earlier = next((r for r in reversed(rows) if r.get("topic") == topic), None)
    if earlier:
        out = {"variant": earlier["variant"], "why": "el tema ya tenía grupo"}
    else:
        topics = {r.get("topic") for r in rows}
        turn = len(topics)
        out = {"variant": SHORT if turn % 2 == 0 else LONG, "why": f"tema nuevo n.º {turn + 1}"}
    AB_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AB_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"artifact": artifact, "topic": topic, **out,
                            "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")
    return out


def apply(script: Dict, variant: Optional[str]) -> Dict:
    """The script as the variant says it: short keeps the first N words and drops the recap, and
    its intro/outro/description stop promising ten. Long (or None) is returned unchanged."""
    if variant != SHORT:
        return script
    n = settings()["short_items"]
    out = copy.deepcopy(script)
    out["items"] = out["items"][:n]
    out["recap"] = ""
    out["variant"] = SHORT
    for key in ("intro", "outro", "video_description"):
        if isinstance(out.get(key), str):
            out[key] = _TEN.sub(lambda m: "5" if m.group(1) == "10" else _case("cinco", m.group(1)), out[key])
    kept = {i["english"] for i in out["items"]}
    if isinstance(out.get("english_phrases"), list):
        out["english_phrases"] = [p for p in out["english_phrases"] if p in kept]
    if isinstance(out.get("translations"), dict):
        out["translations"] = {k: v for k, v in out["translations"].items() if k in kept}
    out["full_script"] = " ".join([out.get("intro", "")]
                                  + [f"{i['spanish']}... {i['english']}. {i['english']}." for i in out["items"]]
                                  + [out.get("outro", "")]).strip()
    return out


def _case(word: str, like: str) -> str:
    return word.capitalize() if like[:1].isupper() else word


def variants() -> Dict[str, str]:
    """{artifact: variant} from the A/B log."""
    return {r["artifact"]: r["variant"] for r in _log_rows() if r.get("artifact") and r.get("variant")}


def compare(videos: List[Dict], mature_days: int = MATURE_DAYS) -> Dict:
    """Views and average % viewed per group (videos older than mature_days). `ready` once each
    group has MIN_PER_GROUP."""
    groups: Dict[str, List[Dict]] = {SHORT: [], LONG: []}
    for v in videos:
        g = v.get("length_variant")
        if g in groups and (v.get("days") or 0) > mature_days:
            groups[g].append(v)

    def median(values):
        values = [x for x in values if x is not None]
        return round(statistics.median(values), 1) if values else None
    return {"ready": all(len(vs) >= MIN_PER_GROUP for vs in groups.values()),
            "groups": {g: {"n": len(vs), "views": median([int(v.get("views", 0)) for v in vs]),
                           "viewed_pct": median([v.get("avg_view_pct") for v in vs])}
                       for g, vs in groups.items()}}

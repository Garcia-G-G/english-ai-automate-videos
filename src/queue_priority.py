"""STEP 80 §2: the queue ordered by what works, and why.

A video type's score is the median views of its videos older than MATURE_DAYS in the latest
statistics (channel_stats); until a type has MIN_VIDEOS of them, its prior from config.yaml
(`queue_priority.prior_views`, Claude's reading of the channel on 26 Oct) stands in. A queued
script's priority is its type's score, ×A1_BOOST when its topic is a basic A1 category
(`queue_priority.a1_categories`). Every priority carries the sentence the panel shows.
"""
from __future__ import annotations

import json
import statistics
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
MATURE_DAYS = 3
MIN_VIDEOS = 3
A1_BOOST = 1.5


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text).casefold())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def settings() -> Dict:
    import yaml
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}
    block = cfg.get("queue_priority") or {}
    return {"prior_views": dict(block.get("prior_views") or {}), "a1": [_fold(w) for w in block.get("a1_categories") or []],
            "default_prior": float(block.get("default_prior", 100))}


def type_scores(stats: Optional[Dict], cfg: Optional[Dict] = None) -> Dict[str, Dict]:
    """{type: {score, source, n}}: the measured median when there is enough, else the prior."""
    cfg = cfg or settings()
    mature: Dict[str, List[int]] = {}
    for v in (stats or {}).get("videos", []):
        if (v.get("days") or 0) > MATURE_DAYS:
            mature.setdefault(v.get("type") or "", []).append(int(v.get("views", 0)))
    out = {}
    for vtype in set(mature) | set(cfg["prior_views"]):
        views = mature.get(vtype, [])
        if len(views) >= MIN_VIDEOS:
            out[vtype] = {"score": float(statistics.median(views)), "source": "medida", "n": len(views)}
        else:
            out[vtype] = {"score": float(cfg["prior_views"].get(vtype, cfg["default_prior"])), "source": "previa",
                          "n": len(views)}
    return out


def a1_word(script: Dict, cfg: Optional[Dict] = None) -> Optional[str]:
    """The basic A1 category a script's topic names, if any («fruta», «casa»…)."""
    cfg = cfg or settings()
    topic = _fold(" ".join(str(script.get(k) or "") for k in ("theme", "title", "video_title")))
    return next((w for w in cfg["a1"] if w and w in topic), None)


def priority(script: Dict, scores: Dict[str, Dict], cfg: Optional[Dict] = None) -> Tuple[float, str]:
    """(priority, why) — why is what the panel shows."""
    cfg = cfg or settings()
    vtype = script.get("type") or ""
    s = scores.get(vtype) or {"score": cfg["default_prior"], "source": "previa", "n": 0}
    base = f"{vtype}: {s['score']:.0f} vistas ({'mediana de ' + str(s['n']) + ' vídeos de más de 3 días' if s['source'] == 'medida' else 'estimación previa'})"
    word = a1_word(script, cfg)
    if word:
        return s["score"] * A1_BOOST, f"{base} × {A1_BOOST} por categoría A1 «{word}»"
    return s["score"], base


def ranked(paths: List[Path], stats: Optional[Dict] = None, cfg: Optional[Dict] = None) -> List[Tuple[Path, float, str]]:
    """[(path, priority, why)], best first; ties keep the queue's own order."""
    cfg = cfg or settings()
    if stats is None:
        import channel_stats
        stats = channel_stats.latest()
    scores = type_scores(stats, cfg)
    out = []
    for k, path in enumerate(paths):
        try:
            script = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        p, why = priority(script, scores, cfg)
        out.append((path, p, why, k))
    out.sort(key=lambda r: (-r[1], r[3]))
    return [(p, pr, why) for p, pr, why, _k in out]

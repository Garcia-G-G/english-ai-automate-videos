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


_CFG: Dict = {}


def _config() -> Dict:
    """config.yaml, parsed once per change (27 ms a parse; the panel asks on every click)."""
    import yaml
    path = ROOT / "config.yaml"
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    if _CFG.get("key") != key:
        _CFG.update(key=key, cfg=yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    return _CFG["cfg"]


def settings() -> Dict:
    cfg = _config()
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


_RANKED: Dict[tuple, list] = {}


def _fingerprint(paths: List[Path]) -> Optional[tuple]:
    """Every input ranked() reads, by mtime and size: the scripts, the stats snapshots, config.yaml."""
    import channel_stats
    try:
        files = [Path(p) for p in paths] + sorted(channel_stats.STATS_DIR.glob("youtube_*.json")) + [ROOT / "config.yaml"]
        return tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for f in files if f.exists())
    except OSError:
        return None


def ranked(paths: List[Path], stats: Optional[Dict] = None, cfg: Optional[Dict] = None) -> List[Tuple[Path, float, str]]:
    """[(path, priority, why)], best first; ties keep the queue's own order. With neither stats
    nor cfg given (the panel's every click), the answer is cached until one of its files changes."""
    key = _fingerprint(paths) if stats is None and cfg is None else None
    if key is not None and key in _RANKED:
        return list(_RANKED[key])
    out = _ranked(paths, stats, cfg)
    if key is not None:
        _RANKED.clear()                                     # one entry: the queue as it is now
        _RANKED[key] = out
    return list(out)


def _ranked(paths: List[Path], stats: Optional[Dict], cfg: Optional[Dict]) -> List[Tuple[Path, float, str]]:
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

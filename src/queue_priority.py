"""STEP 80 §2: the queue ordered by what works, and why.

A video type's score is the median views of its videos older than MATURE_DAYS in the latest
statistics (channel_stats); until a type has MIN_VIDEOS of them, its prior from config.yaml
(`queue_priority.prior_views`, Claude's reading of the channel on 26 Oct) stands in. A queued
script's priority is its type's score, ×A1_BOOST when its topic is a basic A1 category
(`queue_priority.a1_categories`). Every priority carries the sentence the panel shows.
"""
from __future__ import annotations

import json
import re
import statistics
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
MATURE_DAYS = 3
MIN_VIDEOS = 3
A1_BOOST = 1.5
# STEP 81 §1: priority = format_score × topic_score × freshness (scaled so 1000 = the how_do_you_say median)
BASE = 1000
MIN_FORMAT_VIDEOS = 5
FRESH_DAYS = 3
FRESH_FACTOR = 0.5
SEQUEL_PARENT_MIN = 800
DEFAULT_TOPIC_SCORES = {"a": 1.0, "sequel": 0.85, "c": 0.35, "other": 0.6}


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
            "default_prior": float(block.get("default_prior", 100)),
            "tier_c": [_fold(w) for w in block.get("tier_c") or []],
            "topic_scores": {**DEFAULT_TOPIC_SCORES, **(block.get("topic_scores") or {})}}


def type_scores(stats: Optional[Dict], cfg: Optional[Dict] = None) -> Dict[str, Dict]:
    """{type: {score, source, n}}: the measured median when there is enough, else the prior."""
    cfg = cfg or settings()
    mature: Dict[str, List[int]] = {}
    by_bucket: Dict[tuple, List[int]] = {}
    for v in (stats or {}).get("videos", []):
        if (v.get("days") or 0) > MATURE_DAYS:
            mature.setdefault(v.get("type") or "", []).append(int(v.get("views", 0)))
            bucket = (v.get("type") or "", bool(a1_word({"title": v.get("title")}, cfg)))
            by_bucket.setdefault(bucket, []).append(int(v.get("views", 0)))
    out = {}
    for vtype in set(mature) | set(cfg["prior_views"]):
        views = mature.get(vtype, [])
        if len(views) >= MIN_VIDEOS:
            out[vtype] = {"score": float(statistics.median(views)), "source": "medida", "n": len(views)}
            # Measured apart when both kinds of topic have enough videos: then no ×A1_BOOST guess is needed.
            a1, other = by_bucket.get((vtype, True), []), by_bucket.get((vtype, False), [])
            if len(a1) >= MIN_VIDEOS and len(other) >= MIN_VIDEOS:
                out[vtype]["a1"] = {"score": float(statistics.median(a1)), "n": len(a1)}
                out[vtype]["other"] = {"score": float(statistics.median(other)), "n": len(other)}
        else:
            out[vtype] = {"score": float(cfg["prior_views"].get(vtype, cfg["default_prior"])), "source": "previa",
                          "n": len(views)}
    return out


def a1_word(script: Dict, cfg: Optional[Dict] = None) -> Optional[str]:
    """The basic A1 category a script's topic names, if any («fruta», «casa»…)."""
    cfg = cfg or settings()
    topic = _fold(" ".join(str(script.get(k) or "") for k in ("theme", "title", "video_title")))
    # Whole words, an optional plural: «cara» is not in «carácter» nor «cocina» in «cocinar».
    return next((w for w in cfg["a1"] if w and re.search(rf"\b{re.escape(w)}s?\b", topic)), None)


def priority(script: Dict, scores: Dict[str, Dict], cfg: Optional[Dict] = None) -> Tuple[float, str]:
    """(priority, why) — why is what the panel shows."""
    cfg = cfg or settings()
    vtype = script.get("type") or ""
    s = scores.get(vtype) or {"score": cfg["default_prior"], "source": "previa", "n": 0}
    base = f"{vtype}: {s['score']:.0f} vistas ({'mediana de ' + str(s['n']) + ' vídeos de más de 3 días' if s['source'] == 'medida' else 'estimación previa'})"
    word = a1_word(script, cfg)
    apart = s.get("a1" if word else "other")
    if apart:
        kind = f"temas A1 como «{word}»" if word else "temas que no son A1"
        return apart["score"], f"{vtype}: {apart['score']:.0f} vistas (mediana de {apart['n']} vídeos de {kind})"
    if word:
        return s["score"] * A1_BOOST, f"{base} × {A1_BOOST} por categoría A1 «{word}»"
    return s["score"], base


def _median_views(videos: List[Dict], vtype: str) -> Tuple[Optional[float], int]:
    views = [int(v.get("views", 0)) for v in videos if v.get("type") == vtype and (v.get("days") or 0) >= MATURE_DAYS]
    return (float(statistics.median(views)) if views else None), len(views)


def format_score(vtype: str, stats: Optional[Dict], cfg: Dict) -> Tuple[float, str]:
    """This format's median views (videos aged 3 days or more) over how_do_you_say's; a format with
    fewer than MIN_FORMAT_VIDEOS uses its config prior instead."""
    videos = (stats or {}).get("videos", [])
    priors = cfg["prior_views"]
    prior_base = float(priors.get("how_do_you_say") or cfg["default_prior"])
    base, n_base = _median_views(videos, "how_do_you_say")
    base = base if n_base >= MIN_FORMAT_VIDEOS else prior_base
    med, n = _median_views(videos, vtype)
    if n >= MIN_FORMAT_VIDEOS:
        return med / base, f"mediana {med:.0f} de {n} vídeos"
    return float(priors.get(vtype, cfg["default_prior"])) / prior_base, "estimación previa"


def family(script: Dict, cfg: Dict) -> str:
    """The topic family: its A1 category word, else the theme without its article."""
    word = a1_word(script, cfg)
    if word:
        return word
    theme = _fold(script.get("theme") or script.get("title") or "")
    return re.sub(r"^(el|la|los|las|mas)\s+", "", theme).strip()


def topic_score(script: Dict, stats: Optional[Dict], cfg: Dict) -> Tuple[float, str]:
    ts = cfg["topic_scores"]
    meta = script.get("_meta") or {}
    parent = meta.get("sequel_of")
    if parent:
        views = [int(v.get("views", 0)) for v in (stats or {}).get("videos", [])
                 if v.get("type") == "how_do_you_say" and _fold(v.get("category") or "") == _fold(parent)]
        if views and max(views) >= SEQUEL_PARENT_MIN:
            return ts["sequel"], f"secuela de «{parent}» ({max(views)} vistas)"
    word = a1_word(script, cfg)
    if word:
        return ts["a"], f"tema A «{word}»"
    topic = _fold(" ".join(str(script.get(k) or "") for k in ("theme", "title", "video_title")))
    hit = next((w for w in cfg["tier_c"] if w and re.search(rf"\b{re.escape(w)}s?\b", topic)), None)
    if hit:
        return ts["c"], f"subtema o situación «{hit}»"
    return ts["other"], "tema sin categoría A1"


def freshness(script: Dict, stats: Optional[Dict], cfg: Dict) -> Tuple[float, str]:
    """×0.5 when this topic family was published in the last 3 days: two kitchen videos never go out in a row."""
    fam = family(script, cfg)
    for v in (stats or {}).get("videos", []):
        if v.get("days") is not None and v["days"] <= FRESH_DAYS and fam and \
                (fam == _fold(v.get("category") or "") or re.search(rf"\b{re.escape(fam)}", _fold(v.get("title") or ""))):
            return FRESH_FACTOR, f"familia «{fam}» publicada hace {v['days']} d"
    return 1.0, "familia sin publicar esta semana"


def score(script: Dict, stats: Optional[Dict], cfg: Optional[Dict] = None) -> Tuple[float, str]:
    """(priority, why): format_score × topic_score × freshness, with one Spanish sentence."""
    cfg = cfg or settings()
    cfg = {**cfg, "tier_c": cfg.get("tier_c", []), "topic_scores": {**DEFAULT_TOPIC_SCORES, **cfg.get("topic_scores", {})}}
    vtype = script.get("type") or ""
    f, f_why = format_score(vtype, stats, cfg)
    t, t_why = topic_score(script, stats, cfg)
    fr, fr_why = freshness(script, stats, cfg)
    return BASE * f * t * fr, (f"{vtype}: formato ×{f:.2f} ({f_why}) × tema ×{t:.2f} ({t_why}) "
                                f"× frescura ×{fr:.2f} ({fr_why})")


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
    out = []
    for k, path in enumerate(paths):
        try:
            script = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        p, why = score(script, stats, cfg)
        out.append((path, p, why, k))
    out.sort(key=lambda r: (-r[1], r[3]))
    return [(p, pr, why) for p, pr, why, _k in out]

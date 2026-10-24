"""«Hecho con Claude» (STEP 78): the series' scripts, its queue and its upload metadata.

    content/hecho_con_claude/drafts/hc_{m,e,p,c}NNN.json   the 108 scripts, as written
    content/queue/hecho_con_claude/                          the queue (STEP 78 §7 fills it)

A series script is not a ScriptBase: it has no full_script and no type of the main registry.
Its narration is `voice`, one line per beat (see script_schema.HechoConClaudeScript).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from script_schema import SERIES_LEVELS, SERIES_STYLES, validate_series

ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = ROOT / "content" / "hecho_con_claude" / "drafts"
QUEUE_DIR = ROOT / "content" / "queue" / "hecho_con_claude"
DONE_DIR = ROOT / "content" / "queue" / "_done"

#: What the panel calls the type.
PANEL_LABEL = "Hecho con Claude"
#: The panel's level filter, as the viewer reads it.
LEVEL_NAMES = {"principiante": "Principiante", "medio": "Medio", "dificil": "Difícil"}


def load(path: Path) -> Dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def drafts() -> List[Path]:
    return sorted(DRAFTS_DIR.glob("hc_*.json"))


def queued(style: Optional[str] = None, level: Optional[str] = None) -> List[Path]:
    """The queued series scripts, optionally of one style and/or one level, in id order."""
    if style is not None and style not in SERIES_STYLES:
        raise ValueError(f"unknown style {style!r}; one of {', '.join(SERIES_STYLES)}")
    if level is not None and level not in SERIES_LEVELS:
        raise ValueError(f"unknown level {level!r}; one of {', '.join(SERIES_LEVELS)}")
    out = []
    for path in sorted(QUEUE_DIR.glob("hc_*.json")):
        data = load(path)
        if (style is None or data.get("style") == style) and (level is None or data.get("level") == level):
            out.append(path)
    return out


def pick(style: Optional[str] = None, level: Optional[str] = None) -> Optional[tuple]:
    """(path, script) of the next queued script that validates, or None."""
    for path in queued(style, level):
        data = load(path)
        try:
            validate_series(data)
        except Exception:                                   # noqa: BLE001 — never hand out a bad one
            continue
        return path, data
    return None


def upload_metadata(script: Dict) -> Dict:
    """What the publishers get: title = title, description = caption, the 5 hashtags as they are."""
    return {"title": script["title"], "description": script.get("caption") or "",
            "hashtags": list(script.get("hashtags") or [])}


def counts() -> Dict[str, Dict[str, int]]:
    """{style: {level: queued}} for the panel."""
    out = {s: {lv: 0 for lv in SERIES_LEVELS} for s in SERIES_STYLES}
    for path in QUEUE_DIR.glob("hc_*.json"):
        data = load(path)
        if data.get("style") in out and data.get("level") in out[data["style"]]:
            out[data["style"]][data["level"]] += 1
    return out


OUTPUT = ROOT / "output"


def queue_drafts() -> Dict[str, Dict[str, int]]:
    """Copy every validated draft into the queue (STEP 78 §7), leaving the drafts in place. A
    draft already queued or done is skipped; a draft that does not validate stops the copy before
    anything is written. Returns {style: {level: copied}}."""
    plan = []
    for path in drafts():
        data = load(path)
        validate_series(data)                                # raises: nothing half-copied
        if not (QUEUE_DIR / path.name).exists() and not (DONE_DIR / path.name).exists():
            plan.append((path, data))
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    out = {s: {lv: 0 for lv in SERIES_LEVELS} for s in SERIES_STYLES}
    for path, data in plan:
        (QUEUE_DIR / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        out[data["style"]][data["level"]] += 1
    return out


def render_one(style: Optional[str] = None, level: Optional[str] = None, *, progress=None) -> Dict:
    """Pick, render, gate. PASS: output/pending/hecho_con_claude/<id>.mp4 with its sidecar
    (upload metadata, gate, spend), and the script moves to _done. REJECT: output/rejected/…, the
    script stays queued. Raises when the queue has nothing for the filters."""
    import shutil
    from datetime import datetime
    from video.series import gate as G
    from video.series.render import render_series
    picked = pick(style, level)
    if picked is None:
        raise RuntimeError(f"no queued «{PANEL_LABEL}» script for style={style or 'any'}, level={level or 'any'}")
    path, script = picked
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work = OUTPUT / "rendering" / "series" / f"{script['id']}_{stamp}"
    work.mkdir(parents=True, exist_ok=True)
    mp4 = work / f"{script['id']}_{stamp}.mp4"
    if progress:
        progress(f"Rendering {script['id']} ({script['style']}, {script['level']})…")
    info = render_series(script, mp4, work)
    if progress:
        progress("Quality gate…")
    report = G.check(script, mp4, info, work / f"{script['id']}.narration.wav")
    dest = OUTPUT / ("pending" if report["gate"] == "PASS" else "rejected") / "hecho_con_claude"
    dest.mkdir(parents=True, exist_ok=True)
    final = dest / mp4.name
    shutil.move(str(mp4), final)
    sidecar = {"artifact": final.stem, "video_type": "hecho_con_claude", "script_id": script["id"],
               "style": script["style"], "level": script["level"], **upload_metadata(script),
               # the house sidecar shape (admin.gate_record): a verdict string and its blocking flags
               "gate": report["gate"], "blocking_flags": report["flags"], "gate_checks": report["checks"],
               "tts_usd": info.get("tts_usd", 0.0), "duration": info["duration"],
               "outro_variant": info["outro_variant"]}
    final.with_suffix(".json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8")
    if report["gate"] == "PASS":
        DONE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), DONE_DIR / path.name)
    return {"video": str(final), **sidecar}

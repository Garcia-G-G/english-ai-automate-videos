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

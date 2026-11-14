"""STEP 85 §2: admin.find_script_for without Streamlit: the script that produced an artifact."""
from __future__ import annotations

import json
from pathlib import Path

import jobs


def script_for(video_path: Path) -> dict:
    """output/scripts/<type>/<stem>.json (else the newest <stem>_*.json), parsed; {} when none is on disk."""
    type_dir = jobs.SCRIPTS_DIR / Path(video_path).parent.name
    if not type_dir.is_dir():
        return {}
    exact = type_dir / f"{Path(video_path).stem}.json"
    found = exact if exact.exists() else next(iter(sorted(type_dir.glob(f"{Path(video_path).stem}_*.json"), reverse=True)), None)
    try:
        return json.loads(found.read_text(encoding="utf-8")) if found else {}
    except (OSError, ValueError):
        return {}

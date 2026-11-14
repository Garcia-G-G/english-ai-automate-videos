"""STEP 85 §1: the STEP 85b thumbnail paths of a video, UI-free (the API serves them; no image is made here)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


def thumb_paths(mp4: Path) -> Optional[Dict]:
    """{jpg, webp270, webp540, placeholder, chosen, candidates: [{label, webp, note}]}; a path is None when the
    file is not there; None as a whole when the video has no `<stem>.thumb/` folder."""
    from thumbs import thumb_dir
    folder = thumb_dir(mp4)
    try:
        info = json.loads((folder / "thumb.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    have = lambda p: p if p.exists() else None                                  # noqa: E731
    return {"jpg": have(folder / "thumb.jpg"), "webp270": have(folder / "thumb_270.webp"),
            "webp540": have(folder / "thumb_540.webp"), "placeholder": info.get("placeholder"),
            "chosen": info.get("chosen"),
            "candidates": [{"label": k, "webp": have(folder / "cands" / f"{k}.webp"), "note": v}
                           for k, v in sorted((info.get("metrics") or {}).items())]}

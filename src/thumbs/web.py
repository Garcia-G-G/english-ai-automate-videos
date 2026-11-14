"""STEP 85b §5: the panel's pictures, made at render time (never while a page draws).

From the CHOSEN candidate: `thumb_270.webp` (a list row) and `thumb_540.webp` (a large view), quality 82; from every
candidate `cands/<L>.webp` at 180x320 (Revisar shows it at 90x160, 2x). The placeholder is 2x3 blurred pixels as 6 RGB
triples, 24 base64 characters, drawn as a CSS gradient so nothing pops in.
"""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Dict, Optional

from PIL import Image

SIZES = (270, 540)
CAND_SIZE = 180
QUALITY = 82
PLACEHOLDER = (2, 3)


def _webp(im: Image.Image, width: int, out: Path) -> None:
    im.convert("RGB").resize((width, width * 16 // 9), Image.LANCZOS).save(out, "WEBP", quality=QUALITY, method=4)


def placeholder(im: Image.Image) -> str:
    return base64.b64encode(im.convert("RGB").resize(PLACEHOLDER, Image.BOX).tobytes()).decode("ascii")


def make_web(folder: Path) -> Optional[Dict]:
    """Write the WebPs for the folder's chosen candidate (and every candidate's small one); store the placeholder."""
    info_path = folder / "thumb.json"
    info = json.loads(info_path.read_text(encoding="utf-8"))
    for png in (folder / "cands").glob("*.png"):
        small = png.with_suffix(".webp")
        if not small.exists() or small.stat().st_mtime < png.stat().st_mtime:
            _webp(Image.open(png), CAND_SIZE, small)
    chosen = Image.open(folder / "cands" / f"{info['chosen']}.png")
    for w in SIZES:
        _webp(chosen, w, folder / f"thumb_{w}.webp")
    info["placeholder"] = placeholder(chosen)
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


def _gradient(b64: str) -> str:
    try:
        raw = base64.b64decode(b64)
        rows = [tuple((raw[r * 6 + c] + raw[r * 6 + 3 + c]) // 2 for c in range(3)) for r in range(3)]
        return "linear-gradient(" + ",".join(f"rgb{row}" for row in rows) + ")"
    except Exception:                                       # noqa: BLE001 — a bad placeholder is just a plain box
        return "none"


def _uri(path: Path) -> str:
    return "data:image/webp;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def row_img(mp4: Path, css_class: str = "art-thumb", width: int = 45, height: int = 80) -> Optional[str]:
    """`<img>` for a list row from the 270 WebP: fixed size (no layout shift), lazy, async decode, the blurred
    placeholder behind it. None when this video has no WebP yet (the caller falls back to the old still)."""
    folder = Path(mp4).with_name(Path(mp4).stem + ".thumb")
    small = folder / "thumb_270.webp"
    if not small.exists():
        return None
    try:
        ph = json.loads((folder / "thumb.json").read_text(encoding="utf-8")).get("placeholder", "")
    except (OSError, ValueError):
        ph = ""
    return (f'<img class="{css_class}" src="{_uri(small)}" width="{width}" height="{height}" loading="lazy" decoding="async" '
            f'alt="" style="background:{html.escape(_gradient(ph), quote=True)}">')

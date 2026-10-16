#!/usr/bin/env python3
"""Which emoji the vendored font can actually draw. Read from its cmap.

    from emoji_font import emoji_problem
    emoji_problem("👪")        -> None                 (one glyph, in the font)
    emoji_problem("👨‍👩‍👧")      -> "ZWJ sequence ..."    (refused)

WHY THE CMAP AND NOT A HAND LIST. how_do_you_say draws one emoji per row with
Noto Color Emoji. A code point the font lacks renders as an empty box, and a
ZWJ sequence the font lacks renders as two or three separate emoji side by
side -- both look like a finished frame and neither is one. A hand-written
allow-list drifts the moment the font is updated; the font's own character
map cannot.

STDLIB ONLY, ON PURPOSE. script_schema validates every script through this,
and script_schema is imported by tools that never render. Pulling PIL or
fontTools in to read one table would make every one of them pay for it, so
the two cmap formats the font uses (4 and 12) are parsed here with struct.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import FrozenSet, Optional

FONT_PATH = (Path(__file__).resolve().parent.parent
             / "assets" / "fonts" / "NotoColorEmoji.ttf")

#: VARIATION SELECTOR-16. "Draw this as an emoji." Allowed after the one
#: glyph because many emoji are written with it, and it adds no glyph.
VS16 = 0xFE0F

#: ZERO WIDTH JOINER. Its presence means a multi-glyph sequence.
ZWJ = 0x200D

_CODEPOINTS: Optional[FrozenSet[int]] = None


def _parse_cmap(blob: bytes) -> FrozenSet[int]:
    """Every code point mapped by a Unicode cmap subtable (formats 4 and 12)."""
    num_tables = struct.unpack(">H", blob[4:6])[0]
    cmap_off = None
    for i in range(num_tables):
        tag, _sum, off, _len = struct.unpack(">4sIII", blob[12 + 16 * i: 28 + 16 * i])
        if tag == b"cmap":
            cmap_off = off
            break
    if cmap_off is None:
        raise ValueError("font has no cmap table")

    n_sub = struct.unpack(">H", blob[cmap_off + 2: cmap_off + 4])[0]
    points = set()
    for i in range(n_sub):
        plat, enc, sub_off = struct.unpack(
            ">HHI", blob[cmap_off + 4 + 8 * i: cmap_off + 12 + 8 * i])
        if plat not in (0, 3):                     # Unicode / Windows only
            continue
        base = cmap_off + sub_off
        fmt = struct.unpack(">H", blob[base: base + 2])[0]
        if fmt == 12:
            n_groups = struct.unpack(">I", blob[base + 12: base + 16])[0]
            for g in range(n_groups):
                start, end, _gid = struct.unpack(
                    ">III", blob[base + 16 + 12 * g: base + 28 + 12 * g])
                points.update(range(start, end + 1))
        elif fmt == 4:
            seg_x2 = struct.unpack(">H", blob[base + 6: base + 8])[0]
            ends_at = base + 14
            starts_at = ends_at + seg_x2 + 2
            for s in range(seg_x2 // 2):
                end = struct.unpack(">H", blob[ends_at + 2 * s: ends_at + 2 * s + 2])[0]
                start = struct.unpack(">H", blob[starts_at + 2 * s: starts_at + 2 * s + 2])[0]
                if start != 0xFFFF:
                    points.update(range(start, end + 1))
    return frozenset(points)


def codepoints() -> FrozenSet[int]:
    """The font's mapped code points, read once."""
    global _CODEPOINTS
    if _CODEPOINTS is None:
        _CODEPOINTS = _parse_cmap(FONT_PATH.read_bytes())
    return _CODEPOINTS


def emoji_problem(text: str) -> Optional[str]:
    """Why `text` is not ONE emoji this font draws, or None when it is."""
    points = [ord(c) for c in (text or "")]
    if not points:
        return "emoji is empty"
    if ZWJ in points:
        return (f"{text!r} is a ZWJ sequence; it renders as separate emoji "
                f"wherever the font lacks the sequence, so it is refused")
    if points[-1] == VS16:
        points = points[:-1]
    if len(points) != 1:
        return (f"{text!r} is {len(points)} code points; exactly one glyph "
                f"(optionally + U+FE0F) is allowed")
    if points[0] not in codepoints():
        return (f"{text!r} (U+{points[0]:04X}) is not in "
                f"{FONT_PATH.name}; it would draw as an empty box")
    return None

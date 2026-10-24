"""STEP 79 §4: a lesson's YouTube thumbnail, 1280×720, made with PIL from the lesson itself.

The hook is the lesson's first wrong → right pair, in beat order: a `transform` (from → to), a
`sentence` with a `fix`, or a sentence with a red highlight followed by the next sentence. The
wrong form is struck through in red, the right form big in green under it, Bubi on the right, the
lesson's title in at most 5 words on the yellow marker. Everything is sized to read at 320 px wide.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BRAND_DIR = REPO / "assets" / "branding" / "english-unlimited"
FONT = REPO / "assets" / "fonts" / "Fredoka-Bold.ttf"
SIZE = (1280, 720)
TEXT_W = 740                    # the left column (x 70..810); Bubi has the right, from x 860
BUBI_W = 360
MIN_PX = 64                     # 16 px at 320 wide


def hook(lesson: dict) -> Optional[Tuple[str, str]]:
    """(wrong, right) — the pair the lesson corrects first, looked for in this order: a
    `transform` (from → to); a `sentence` with a `fix`; a sentence with a red highlight. The right
    form of a sentence is the closest later sentence, or [[English]] a narration says, that is
    this one corrected: a script's `fix` changes one chip («more» → «taller») and is not a whole
    sentence, so it is never applied. `lesson["thumbnail"] = {"wrong", "right"}` overrides."""
    if lesson.get("thumbnail"):
        return lesson["thumbnail"]["wrong"], lesson["thumbnail"]["right"]
    beats = lesson["beats"]
    for b in beats:
        if b["type"] == "transform" and b.get("from") and b.get("to"):
            return b["from"], b["to"]
    for wants in (lambda b: b.get("fix"), lambda b: "red" in (b.get("highlight") or {}).values()):
        shown = None                                      # a `same` sentence repeats the one shown
        for k, b in enumerate(beats):
            if b["type"] != "sentence":
                continue
            shown = b.get("text") or shown
            if not shown or not wants(b):
                continue
            later = [x["text"] for x in beats[k + 1:] if x["type"] in ("sentence", "transform") and x.get("text")]
            later += [m for x in beats[k:] for m in re.findall(r"\[\[(.+?)\]\]", x.get("narration", ""))]
            later = [t for t in later if _sentence_like(t, shown)]
            best = max(later, key=lambda t: _alike(shown, t), default=None)
            if best is not None and _alike(shown, best) >= ALIKE:
                return shown, best[0].upper() + best[1:]
    return None


def _sentence_like(right: str, wrong: str) -> bool:
    """A whole corrected sentence: not the same, one sentence, not a cut-off piece of the wrong."""
    r, w = right.rstrip(".!?").casefold().split(), wrong.rstrip(".!?").casefold().split()
    return (_alike(wrong, right) < 1.0 and len(r) >= max(2, len(w) - 2) and not re.search(r"[.!?]\s", right)
            and not " ".join(w).startswith(" ".join(r)))


#: How much of two sentences' words must be shared to call one the other corrected.
ALIKE = 0.5


def _alike(a: str, b: str) -> float:
    x, y = ({w.strip(".,!?¿¡").casefold() for w in t.split()} for t in (a, b))
    return len(x & y) / max(1, len(x | y))


def short_title(title: str, words: int = 5) -> str:
    """The title before its colon, at most `words` words: «Make y do: dos verbos…» → «Make y do»."""
    head = re.split(r"[:—–]", title)[0].strip()
    parts = head.split()
    return " ".join(parts[:words])


def _font(px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), px)


def _fit(draw, text: str, width: int, start: int, floor: int = MIN_PX, one_line_floor: int = 72):
    """(font, lines): one line at the largest size down to `one_line_floor`, else two lines at
    the largest size that fits `width`."""
    for px in range(start, one_line_floor - 1, -4):
        if draw.textlength(text, font=_font(px)) <= width:
            return _font(px), [text]
    for px in range(start, floor - 1, -4):
        f = _font(px)
        words = text.split()
        for cut in range(len(words) - 1, 0, -1):
            a, b = " ".join(words[:cut]), " ".join(words[cut:])
            if draw.textlength(a, font=f) <= width and draw.textlength(b, font=f) <= width:
                return f, [a, b]
    f = _font(floor)
    return f, [text]


def _colour(hex_: str) -> tuple:
    hex_ = hex_.lstrip("#")
    return tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))


def _draw_text(img, title, wrong, right, scale, ink, red, green, yellow) -> float:
    """The title, the struck wrong form and the right form at `scale`; returns the bottom y."""
    d = ImageDraw.Draw(img)
    x0, px = 70, lambda v: max(40, int(v * scale))

    # the title on the yellow marker, top left
    tf, tlines = _fit(d, title, TEXT_W, px(76), px(56), px(56))
    y = 56
    for line in tlines:
        w = d.textlength(line, font=tf)
        box = d.textbbox((x0, y), line, font=tf)
        d.rectangle([x0 - 10, box[1] + (box[3] - box[1]) * 0.45, x0 + w + 10, box[3] + 8], fill=yellow)
        d.text((x0, y), line, font=tf, fill=ink)
        y = box[3] + 18

    # the wrong form, struck through in red
    y += 34 * scale
    wf, wlines = _fit(d, wrong, TEXT_W, max(MIN_PX, px(96)), MIN_PX, max(MIN_PX, px(72)))     # never under 16 px at 320
    for line in wlines:
        box = d.textbbox((x0, y), line, font=wf)
        d.text((x0, y), line, font=wf, fill=red)
        mid = (box[1] + box[3]) / 2
        d.line([box[0] - 8, mid + 6, box[2] + 8, mid - 6], fill=ink, width=16)
        d.line([box[0] - 8, mid + 6, box[2] + 8, mid - 6], fill=red, width=10)
        y = box[3] + 22

    # the right form, big, in green, a tick before its first line
    y += 18 * scale
    rf, rlines = _fit(d, right, TEXT_W - 90, max(MIN_PX, px(112)), MIN_PX, max(MIN_PX, px(72)))
    for k, line in enumerate(rlines):
        box = d.textbbox((x0 + 90, y), line, font=rf)
        d.text((x0 + 90, y), line, font=rf, fill=green)
        if k == 0:
            cy = (box[1] + box[3]) / 2
            d.line([(x0 + 4, cy), (x0 + 30, cy + 28), (x0 + 74, cy - 34)], fill=green, width=16, joint="curve")
        y = box[3] + 22
    return y


def make(lesson: dict, out: Path) -> Optional[Path]:
    """Write the thumbnail to `out` (a .jpg), or return None when the lesson has no wrong → right."""
    pair = hook(lesson)
    if pair is None:
        return None
    wrong, right = pair
    brand = json.loads((BRAND_DIR / "brand.json").read_text(encoding="utf-8"))
    sand = brand["manim"]["themes"]["sand"]
    bg, ink = _colour(sand["bg"]), _colour(brand["color"]["ink"])
    red, green, yellow = _colour(sand["red"]), _colour(sand["green"]), _colour(brand["color"]["brand_yellow"])
    for scale in (1.0, 0.9, 0.8, 0.72, 0.64):
        img = Image.new("RGB", SIZE, bg)
        bottom = _draw_text(img, short_title(lesson["title"]), wrong, right, scale, ink, red, green, yellow)
        if bottom <= SIZE[1] - 30:
            break

    # Bubi on the right, celebrating
    bubi = Image.open(BRAND_DIR / "expresiones" / "lo_lograste.png").convert("RGBA")
    bubi = bubi.crop(bubi.getchannel("A").getbbox())
    h = 430
    bubi = bubi.resize((int(bubi.width * h / bubi.height), h), Image.LANCZOS)
    if bubi.width > BUBI_W:
        bubi = bubi.resize((BUBI_W, int(bubi.height * BUBI_W / bubi.width)), Image.LANCZOS)
    img.paste(bubi, (SIZE[0] - bubi.width - 60, (SIZE[1] - bubi.height) // 2 + 20), bubi)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)
    return out

"""STEP 85b §3: the 16:9 thumbnail of every long video, 1280x720, one template for all of them.

The REAL frame of the lesson's first `sentence` beat on the right as a card with the ink outline; on the left at
most 4 words of the title in Fredoka Bold, white on the family gradient, one word in yellow (the word the lesson
corrects, when it has one); Bubi bottom left; the learningroutes.com mark. No arrows, no shocked faces, no word the
video does not say, nothing in the bottom-right 220x70 px (YouTube's duration badge).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional, Tuple

import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BRAND_DIR = REPO / "assets" / "branding" / "english-unlimited"
FONT = REPO / "assets" / "fonts" / "Fredoka-Bold.ttf"
SIZE = (1280, 720)
BADGE = (1280 - 220, 720 - 70, 1280, 720)       # YouTube's duration badge: keep it empty
CARD = (660, 150, 1240, 476)                     # 580x326, 16:9
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


def _colour(hex_: str) -> tuple:
    hex_ = hex_.lstrip("#")
    return tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))


WORDS_MAX = 4
TEXT_BOX = (60, 70, 580)                         # x, y, width of the left column
XHEIGHT_MIN_320 = 7.0
YELLOW = "#F2D66B"


def words(lesson: dict) -> list:
    """At most 4 words, the title's own (short_title), never invented."""
    return short_title(lesson["title"], WORDS_MAX).split()


def highlight(lesson: dict, ws: list) -> int:
    """Index of the yellow word: one the lesson corrects (in the right form, not in the wrong one), else the longest."""
    pair = hook(lesson)
    if pair:
        clean = lambda t: {w.strip(".,!?").casefold() for w in t.split()}          # noqa: E731
        diff = clean(pair[1]) - clean(pair[0])
        for k, w in enumerate(ws):
            if w.casefold() in diff:
                return k
    return max(range(len(ws)), key=lambda k: len(ws[k]))


def first_sentence_time(timeline: dict) -> Optional[float]:
    b = next((b for b in timeline.get("beats") or [] if b.get("type") == "sentence"), None)
    return float(b["start"]) if b else None


def _extract(video: Path, t: float, size: Tuple[int, int]) -> Optional[Image.Image]:
    import tempfile
    out = Path(tempfile.mkdtemp()) / "f.png"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-accurate_seek", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={size[0]}:{size[1]}:flags=lanczos", str(out)], capture_output=True, timeout=60)
    return Image.open(out).convert("RGB") if r.returncode == 0 and out.exists() else None


def real_frame(video: Path, timeline: dict) -> Tuple[Optional[Image.Image], Optional[float]]:
    """A frame of the first sentence beat once it has drawn (1.5 s on, then later): the first that is not blank."""
    import numpy as np
    sys.path.insert(0, str(REPO / "src"))
    import thumbs
    t0 = first_sentence_time(timeline)
    if t0 is None:
        return None, None
    for dt in (1.5, 2.5, 3.5, 5.0):
        im = _extract(video, t0 + dt, (CARD[2] - CARD[0], CARD[3] - CARD[1]))
        if im is None:
            continue
        luma, edges = thumbs.luminance_and_edges(np.asarray(im))
        if luma >= thumbs.LUMA_RANGE[0] and edges >= 0.005:      # a paper-coloured lesson is bright: no upper bound
            return im, t0 + dt
    return None, None


def _gradient(top: str, bottom: str) -> Image.Image:
    a, b = _colour(top), _colour(bottom)
    im = Image.new("RGB", SIZE)
    d = ImageDraw.Draw(im)
    for y in range(SIZE[1]):
        q = y / (SIZE[1] - 1)
        d.line([(0, y), (SIZE[0], y)], fill=tuple(round(a[i] + (b[i] - a[i]) * q) for i in range(3)))
    return im


def _family(title: str) -> Tuple[str, str]:
    """The topic family's gradient, only if white AND yellow text clear 4.5:1 on both stops; else «vida real»."""
    sys.path.insert(0, str(REPO / "src"))
    from video.tablero import kit
    from thumbs.checks import contrast
    fam = kit.families()
    for name in (kit.family_for(title), "vida real"):
        top, bottom = fam[name]
        if all(contrast(fg, _colour(stop)) >= 4.5 for stop in (top, bottom) for fg in ((255, 255, 255), _colour(YELLOW))):
            return top, bottom
    return fam["vida real"]


def _layout(d, ws: list):
    """The biggest size (down to 80 px: 20 px at 320 wide) whose wrapped lines fit the column."""
    for px in range(136, 79, -8):
        f = _font(px)
        lines, cur = [], ""
        for w in ws:
            trial = (cur + " " + w).strip()
            if d.textlength(trial, font=f) <= TEXT_BOX[2] or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        if len(lines) * px * 1.12 <= 300 and all(d.textlength(l, font=f) <= TEXT_BOX[2] for l in lines):
            return f, lines
    return _font(80), [" ".join(ws[:2]), " ".join(ws[2:])]


def measurements(f: ImageFont.FreeTypeFont, top: str, bottom: str) -> dict:
    """Contrast of white and yellow on the gradient, x-height at 320x180."""
    from thumbs.checks import contrast
    bb = f.getbbox("x")
    return {"white_contrast": min(contrast((255, 255, 255), _colour(c)) for c in (top, bottom)),
            "yellow_contrast": min(contrast(_colour(YELLOW), _colour(c)) for c in (top, bottom)),
            "xheight_320": round((bb[3] - bb[1]) * 320 / 1280, 1), "font_px": f.size}


def make(lesson: dict, out: Path, video: Optional[Path] = None, timeline: Optional[dict] = None) -> Optional[Path]:
    """Write the thumbnail to `out` (a .jpg), or None when there is no real frame to show (no render, no `sentence`
    beat): an honest thumbnail needs a real frame."""
    if video is None or not Path(video).exists():
        return None
    card, t = real_frame(Path(video), timeline or {})
    if card is None:
        return None
    top, bottom = _family(lesson["title"])
    img = _gradient(top, bottom)
    d = ImageDraw.Draw(img)
    ws = words(lesson)
    hi = highlight(lesson, ws)
    f, lines = _layout(d, ws)
    y, k = TEXT_BOX[1], 0
    for line in lines:
        x = TEXT_BOX[0]
        for w in line.split():
            d.text((x, y), w, font=f, fill=_colour(YELLOW) if k == hi else (255, 255, 255))
            x += d.textlength(w + " ", font=f)
            k += 1
        y += int(f.size * 1.12)
    x0, y0, x1, y1 = CARD                                                # the real frame: ink outline, hard shadow
    d.rounded_rectangle((x0 + 10, y0 + 12, x1 + 10, y1 + 12), 18, fill=(0, 0, 0))
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, card.width - 1, card.height - 1), 14, fill=255)
    img.paste(card, (x0, y0), mask)
    d.rounded_rectangle((x0 - 3, y0 - 3, x1 + 3, y1 + 3), 18, outline=_colour("#1C1812"), width=8)
    bubi = Image.open(BRAND_DIR / "expresiones" / "wow.png").convert("RGBA")
    bubi = bubi.crop(bubi.getchannel("A").getbbox())
    h = 270
    bubi = bubi.resize((int(bubi.width * h / bubi.height), h), Image.LANCZOS)
    img.paste(bubi, (40, SIZE[1] - h - 20), bubi)
    d.text((660, 640), "learningroutes.com", font=_font(30), fill=(255, 255, 255))      # away from the duration badge
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    for q in (92, 88, 84, 80):                                           # YouTube takes up to 2 MB
        img.save(out, quality=q, subsampling=0, optimize=True, progressive=True)
        if out.stat().st_size <= 2_000_000:
            break
    out.with_suffix(".json").write_text(json.dumps({"frame_t": round(t, 2), "words": ws, "yellow": ws[hi], "gradient": [top, bottom],
                                                    **measurements(f, top, bottom)}, ensure_ascii=False), encoding="utf-8")
    return out


def remake_all(studio: Path = HERE) -> list:
    """Re-make the thumbnail of every lesson's newest render from the render itself ($0). Returns [(lesson, path|None)]."""
    sys.path.insert(0, str(studio))
    import lesson as L
    done = []
    for folder in sorted((studio / "renders").iterdir()):
        mp4s = sorted(folder.glob("*.mp4"))
        lp = studio / "lessons" / f"{folder.name}.json"
        tl = mp4s[-1].with_suffix(".timeline.json") if mp4s else None
        if not mp4s or not lp.exists():
            continue
        if not tl.exists():
            done.append((folder.name, None))
            continue
        done.append((folder.name, make(L.load(lp), mp4s[-1].with_suffix(".thumb.jpg"), mp4s[-1], json.loads(tl.read_text(encoding="utf-8")))))
    return done


if __name__ == "__main__":
    for name, path in remake_all():
        print(name, path or "no thumbnail (no real frame)")

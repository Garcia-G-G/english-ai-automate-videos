"""The look of a lesson: brand.json → manim.themes, the colours derived from the tokens,
WCAG contrast, and the paper behind everything — a soft radial vignette and a faint
static grain, generated once with numpy and cached as a PNG per theme and size.

    sand (default) warm paper · stone cooler grey paper · dark the ink stage

Yellow is a fill or a highlighter on paper, never text: on the paper themes the places
that were yellow text on the dark stage use ink, and yellow strokes use a darker gold.
Pure Python + numpy + Pillow; no Manim, so the tests can check the tokens.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRAND_PATH = HERE.parent.parent / "assets" / "branding" / "english-unlimited" / "brand.json"
TOKENS = ("bg", "card", "card2", "text", "muted", "yellow", "blue", "green", "red")
# (foreground, background, minimum ratio): text must read on the ground and on a card;
# the grammar colours carry meaning as strokes, fills and large type, so 3:1 (WCAG non-text).
# The notebook page (STEP 63) is a ground too, so it gets the same rules.
CONTRAST_RULES = (("text", "bg", 4.5), ("text", "card", 4.5), ("blue", "bg", 3.0), ("green", "bg", 3.0),
                  ("red", "bg", 3.0), ("text", "page", 4.5), ("blue", "page", 3.0), ("green", "page", 3.0),
                  ("red", "page", 3.0))
VIGNETTE_CENTRE, VIGNETTE_EDGE, GRAIN = 0.03, -0.04, 0.02      # lightness, as fractions of full scale


def manim_block() -> dict:
    return json.loads(BRAND_PATH.read_text(encoding="utf-8"))["manim"]


def tokens(name: str) -> dict:
    themes = manim_block()["themes"]
    if name not in themes:
        raise SystemExit(f"THEME {name!r} is not one of {sorted(themes)} (brand.json → manim.themes)")
    return {k: themes[name][k] for k in TOKENS}


def rgb(color: str) -> tuple:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def mix(a: str, b: str, k: float) -> str:
    """`b` laid over `a` at strength k, as an opaque hex colour."""
    return "#" + "".join(f"{round(x * (1 - k) + y * k):02X}" for x, y in zip(rgb(a), rgb(b)))


def luminance(color: str) -> float:
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def contrast_table() -> list:
    """[{theme, fg, bg, ratio, minimum, ok}] for every theme and rule."""
    rows = []
    for name in manim_block()["themes"]:
        t = palette(name)
        for fg, bg, minimum in CONTRAST_RULES:
            ratio = contrast(t[fg], t[bg])
            rows.append({"theme": name, "fg": fg, "bg": bg, "ratio": round(ratio, 2), "minimum": minimum,
                         "ok": ratio >= minimum})
    return rows


def palette(name: str) -> dict:
    """The tokens plus what the scene derives from them."""
    t = tokens(name)
    dark = luminance(t["bg"]) < 0.2
    p = dict(t, name=name, dark=dark)
    p["surface"] = t["card"]                                       # chips, cards, the caption band
    p["line"] = t["card2"] if dark else mix(t["card2"], t["text"], 0.15)
    p["soft"] = mix(t["bg"], t["text"], 0.70)                      # glosses
    p["dim"] = mix(t["bg"], t["text"], 0.40)                       # captions not yet spoken
    p["en_dim"] = mix(t["bg"], t["blue"], 0.50)
    p["accent_text"] = t["yellow"] if dark else t["text"]         # where the dark stage had yellow type
    p["accent_line"] = t["yellow"] if dark else mix(t["yellow"], t["text"], 0.45)   # rings, «ahora», gold lanes
    # the notebook page (STEP 63): a paper a shade lighter than the ground, an ink outline and
    # a hard ink shadow; on the dark stage a card-coloured page with a light outline
    p["page"] = t["card"] if dark else mix(t["bg"], t["card"], 0.6)
    p["page_line"] = mix(t["card"], t["text"], 0.6) if dark else t["text"]
    p["page_shadow"] = mix(t["bg"], "#000000", 0.6) if dark else t["text"]
    return p


def ink_on(fill: str, p: dict) -> str:
    """The text colour for a word on a coloured chip: ink or paper, whichever reads better."""
    light, ink = (p["text"], p["bg"]) if p["dark"] else (p["card"], p["text"])
    return light if contrast(light, fill) >= contrast(ink, fill) else ink


def background_png(name: str, width: int, height: int, out_dir: Path = HERE / "media" / "backgrounds") -> Path:
    """The theme's paper at this pixel size: lightness +3 % at the centre easing to −4 % at
    the corners, plus a ±2 % grain from a fixed seed — the same file every render."""
    out = Path(out_dir) / f"{name}_{width}x{height}.png"
    if out.exists():
        return out
    import numpy as np
    from PIL import Image
    out.parent.mkdir(parents=True, exist_ok=True)
    base = np.array(rgb(tokens(name)["bg"]), dtype=np.float32)
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    r = np.hypot((x - width / 2) / (width / 2), (y - height / 2) / (height / 2)) / np.sqrt(2)   # 0 centre, 1 corner
    lift = VIGNETTE_CENTRE + (VIGNETTE_EDGE - VIGNETTE_CENTRE) * r ** 2
    grain = np.random.default_rng(7).uniform(-GRAIN, GRAIN, (height, width)).astype(np.float32)
    img = base[None, None, :] + 255 * (lift + grain)[..., None]
    Image.fromarray(np.clip(np.rint(img), 0, 255).astype(np.uint8), "RGB").save(out)
    return out

"""STEP 77 §1: one notebook kit, every mark drawn at 4× and anti-aliased; every mode renders."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video.notebook import kit  # noqa: E402


def _layer():
    return Image.new("RGBA", (420, 320), (0, 0, 0, 0))


def _drawn(fn):
    layer = _layer()
    fn(layer)
    return layer


SPRITES = {
    "page": lambda L: kit.page(L, 20.5, 20.25, 300, 200),
    "rings": lambda L: kit.rings(L, 80.0, 30.0, 280.0, n=5),
    "rule": lambda L: kit.rule(L, 20.0, 380.0, 150.4, 3, kit.colour("sky")),
    "marker": lambda L: kit.marker_stroke(L, [(30 + 8 * k, 100 + 6 * np.sin(k / 3)) for k in range(40)], 18,
                                          kit.colour("brand_yellow")),
    "tick": lambda L: kit.tick(L, 60.3, 120.7, 1.0),
    "tick_drawing": lambda L: kit.tick(L, 60.3, 120.7, 1.0, progress=0.6),
    "cross": lambda L: kit.cross(L, 60.0, 120.0, 1.0),
    "circle": lambda L: kit.circle(L, (100.5, 80.25, 300.0, 140.0), 1.0),
    "strike": lambda L: kit.strike(L, 100.0, 300.0, 150.5, 1.0),
    "dots": lambda L: kit.dots(L, 100.2, 150.6, 0.4),
    "highlighter": lambda L: kit.highlighter(L, (20.4, 60.2, 380.0, 160.0), 0.7),
    "pencil": lambda L: L.alpha_composite(kit.pencil()[0].crop((280, 280, 700, 600))),
    "pill": lambda L: L.alpha_composite(kit.pill(36, 200, kit.colour("correct")), (100, 40)),
    "note": lambda L: L.alpha_composite(kit.note_card(300, 200), (40, 40)),
    "bubi_sticker": lambda L: L.alpha_composite(kit.bubi_sticker(150), (40, 40)),
    "footer": lambda L: L.alpha_composite(kit.footer(), (20, 100)),
}


@pytest.mark.parametrize("name", sorted(SPRITES))
def test_every_sprite_has_anti_aliased_edges(name):
    """The audit's check: an aliased shape has only 0 and 255 on its edge; a supersampled
    one has a ramp. At least 8 distinct partial-alpha values on the edge."""
    alpha = np.asarray(_drawn(SPRITES[name]))[:, :, 3]
    edge = alpha[(alpha > 0) & (alpha < 255)]
    assert len(np.unique(edge)) >= 8, f"{name}: {len(np.unique(edge))} partial alpha values"


def test_an_ellipse_edge_is_smooth_where_pil_alone_steps():
    """The audit's own sample: PIL's ellipse edge versus the kit's dot."""
    from PIL import ImageDraw
    raw = _layer()
    ImageDraw.Draw(raw).ellipse([100, 100, 160, 160], outline=(0, 0, 0, 255), width=4)
    raw_vals = np.unique(np.asarray(raw)[:, :, 3])
    kit_vals = np.unique(np.asarray(_drawn(lambda L: kit.dots(L, 100, 130, 1.0)))[:, :, 3])
    assert len(raw_vals) <= 2 and len(kit_vals) > 16


def test_identical_marks_come_from_the_cache():
    before = len(kit._SPRITES)
    for _ in range(5):
        kit.tick(_layer(), 33.0, 44.0, 0.5)
    assert len(kit._SPRITES) == before + 1


def test_one_paper_for_the_page_and_the_outro_card():
    from video import outro as O
    img = np.asarray(O.outro_still(O.load_variants()["variants"][0]))
    x, y = 1080 // 2, (1920 - O.CARD_H) // 2 + O.CARD_DY + 40
    assert tuple(img[y, 40]) != tuple(kit.PAPER[:3])           # outside the card: sand
    assert tuple(img[y + 20, x - 300]) == tuple(kit.PAPER[:3])


def test_the_notebook_module_draws_only_through_the_kit():
    src = (ROOT / "src" / "video" / "how_do_you_say.py").read_text(encoding="utf-8")
    for call in ("draw.line(", "draw.polygon(", "draw.ellipse(", "draw.arc(", "draw.rounded_rectangle(",
                 "draw.rectangle(", "def ease_out_cubic", "def ease_in_out", "def emoji_image"):
        assert call not in src, call


def test_motion_is_the_one_easing_module():
    from video import motion
    import animations.easing as old
    for name in ("ease_out_cubic", "ease_in_out", "ease_out_back", "ease_out_expo", "spring", "stagger"):
        assert callable(getattr(motion, name))
    assert old.ease_out_back is motion.ease_out_back and old.ease_out_cubic is motion.ease_out_cubic


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("vtype", ["how_do_you_say", "level_test", "say_it_level", "true_false_level",
                                   "fill_level", "choose_level", "phrases_level"])
def test_a_still_of_every_mode_renders(vtype):
    import video.how_do_you_say as H
    if vtype == "how_do_you_say":
        T = _load("t_hdys", ROOT / "tests" / "test_how_do_you_say.py")
        data, dur = T._timeline(T._script())
        frame = H.create_frame_how_do_you_say(dur * 0.4, data, dur)
    else:
        T = _load("t_step63", ROOT / "tests" / "test_level_step63_fixes.py")
        data, dur = T._timeline(vtype)
        frame = H.create_frame_level(dur * 0.4, data, dur)
    assert frame.shape[:2] == (1920, 1080) and frame.std() > 10

"""STEP 77 §5: emoji on a sticker disc, and one distinct, literal emoji per item."""
import copy
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video.notebook import kit  # noqa: E402


def test_the_emoji_sits_inside_a_white_disc_with_an_ink_outline_and_a_hard_shadow():
    img = kit.emoji_sticker("⬜", 76)
    a = np.asarray(img).astype(int)
    assert len(set(a[:, :, 3].ravel()) - {0, 255}) >= 8                       # anti-aliased edge
    r = 76 / 2
    cx = cy = 1 + r
    ys, xs = np.nonzero(a[:, :, 3] > 0)
    # nothing of the emoji (a square, its corners the farthest out) crosses the disc
    e = kit.emoji("⬜", round(76 * kit.EMOJI_IN_DISC))
    assert np.hypot(e.width / 2, e.height / 2) < r - kit.DISC_OUTLINE
    # the shadow: ink below-right of the disc, nothing above-left of it
    assert np.abs(a[int(cy + r + 2), int(cx), :3] - np.array(kit.colour("ink")[:3])).sum() < 20
    assert a[0, 0, 3] == 0
    ink = np.array(kit.colour("ink")[:3])
    ring = a[int(cy), 2:5, :3]                                                # the outline, left edge
    assert (np.abs(ring - ink).sum(axis=1) < 60).any()


def test_how_do_you_say_draws_its_emoji_as_stickers(monkeypatch):
    import video.how_do_you_say as H
    T = __import__("importlib").util
    spec = T.spec_from_file_location("t_h5", ROOT / "tests" / "test_how_do_you_say.py")
    m = T.module_from_spec(spec)
    spec.loader.exec_module(m)
    data, dur = m._timeline(m._script())
    drawn = []
    real = kit.emoji_sticker
    monkeypatch.setattr(kit, "emoji_sticker", lambda c, s: drawn.append(c) or real(c, s))
    H.create_frame_how_do_you_say(dur * 0.5, data, dur)
    assert drawn == [it["emoji"] for it in data["items"]]


def test_the_schema_refuses_the_same_emoji_twice_on_a_page():
    import script_schema
    data = json.loads((ROOT / "content" / "queue" / "_done" / "bv026_dormitorio.json").read_text(encoding="utf-8"))
    script_schema.SCRIPT_MODELS["how_do_you_say"].model_validate(data)
    twice = copy.deepcopy(data)
    twice["items"][9]["emoji"] = twice["items"][1]["emoji"] + "️"         # VS16 does not make it new
    with pytest.raises(ValueError, match="duplicate emoji"):
        script_schema.SCRIPT_MODELS["how_do_you_say"].model_validate(twice)


def test_the_generator_asks_for_one_distinct_literal_emoji_per_item():
    src = (ROOT / "src" / "script_generator.py").read_text(encoding="utf-8")
    assert "Un emoji DISTINTO por item" in src and "objeto" in src and "literal" in src


def test_every_queued_how_do_you_say_page_has_distinct_emoji_and_the_dormitorio_picks_are_fixed():
    import script_schema
    paths = glob.glob(str(ROOT / "content" / "queue" / "how_do_you_say" / "*.json"))
    for path in paths:
        script_schema.SCRIPT_MODELS["how_do_you_say"].model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
    bv026 = json.loads((ROOT / "content" / "queue" / "_done" / "bv026_dormitorio.json").read_text(encoding="utf-8"))
    picks = {it["spanish"]: it["emoji"] for it in bv026["items"]}
    assert picks["Manta"] != "🧣" and picks["Alfombra"] != "🧶" and picks["Sábana"] != picks["Colchón"]

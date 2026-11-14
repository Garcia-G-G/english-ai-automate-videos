"""STEP 78 §6: the comic's countdown, stamps and Bubi's expressions."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video.series import comic as C  # noqa: E402
from video.series import render as R  # noqa: E402


def _script(sid="hc_c001"):
    return json.loads((ROOT / "content" / "hecho_con_claude" / "drafts" / f"{sid}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["wow", "lo_lograste", "bien_hecho"])
def test_bubis_expressions_are_cut_out_of_the_brand_guide_on_transparent_ground(name):
    img = Image.open(C.EXPRESSIONS / f"{name}.png").convert("RGBA")
    a = np.asarray(img)[:, :, 3]
    assert img.width > 200 and a[0, 0] == 0 and a[-1, -1] == 0          # the paper is gone
    assert (a == 255).mean() > 0.4                                     # Bubi is solid


def test_the_countdown_runs_in_the_timelines_three_seconds_then_the_reveal():
    s = _script()
    tl = R.estimated_timeline(s)
    tm = C.times(s, tl)
    assert (tm["count0"], tm["reveal"]) == tuple(tl["countdown"])
    assert tm["options"] == sorted(tm["options"]) and tm["options"][-1] < tm["count0"]


def test_the_stamps_go_on_the_wrong_options_and_the_ring_on_the_right_one(monkeypatch):
    s = _script()
    tl = R.estimated_timeline(s)
    tm = C.times(s, tl)
    stamped, ringed = [], []
    real_place, real_ring = C._place, C.K.ring
    stamp = C._stamp()
    monkeypatch.setattr(C, "_place", lambda img, sprite, cx, cy, *a: (stamped.append(cy) if sprite is stamp else None)
                        or real_place(img, sprite, cx, cy, *a))
    monkeypatch.setattr(C.K, "ring", lambda img, box, p, colour, *a: ringed.append((box, colour)) or real_ring(img, box, p, colour, *a))
    C.frame(tm["reveal"] + 0.6, s, tl)
    lay = C.layout(s)
    wrong = [k for k in range(3) if k != s["quiz"]["answer"]]
    assert sorted(stamped) == sorted((lay["opt_boxes"][k][1] + lay["opt_boxes"][k][3]) / 2 for k in wrong)
    right = lay["opt_boxes"][s["quiz"]["answer"]]
    assert any(c == C.GREEN and b[1] < right[1] and b[3] > right[3] for b, c in ringed)


def test_bubi_is_surprised_before_the_reveal_and_happy_after(monkeypatch):
    s = _script()
    tl = R.estimated_timeline(s)
    tm = C.times(s, tl)
    seen = []
    real = C._expression
    monkeypatch.setattr(C, "_expression", lambda name, w: seen.append(name) or real(name, w))
    C.frame(tm["reveal"] - 0.5, s, tl)
    C.frame(tm["reveal"] + 0.5, s, tl)
    assert seen == ["wow", "lo_lograste"]

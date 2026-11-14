"""STEP 79 §0: mensajes, the leftover from the 78b review: frame 0 is the whole chat under the
hook card, and the example cards stack in the lower half, under the rule, never over the chat."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video.series import mensajes as M  # noqa: E402
from video.series import render as R  # noqa: E402
from video.series import series_kit as K  # noqa: E402

DRAFTS = ROOT / "content" / "hecho_con_claude" / "drafts"
ALL = [p.stem for p in sorted(DRAFTS.glob("hc_m*.json"))]


def _draft(sid):
    return json.loads((DRAFTS / f"{sid}.json").read_text(encoding="utf-8"))


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@pytest.mark.parametrize("sid", ["hc_m001", "hc_m010", "hc_m021"])
def test_frame_zero_shows_every_bubble_the_error_included(sid):
    s = _draft(sid)
    tl = R.estimated_timeline(s)
    f0 = np.asarray(M.frame(0.0, s, tl).convert("RGB")).astype(int)
    empty = np.asarray(M.frame(0.0, dict(s, chat=dict(s["chat"], messages=[["them", " "]])), tl).convert("RGB")).astype(int)
    for b in M.layout(s)["bubbles"]:
        x0, y0, x1, y1 = (int(v) for v in b["box"])
        assert np.abs(f0[y0:y1, x0:x1] - empty[y0:y1, x0:x1]).mean() > 15, b["lines"]


@pytest.mark.parametrize("sid", ALL)
def test_the_hook_card_does_not_cover_the_chat(sid):
    s = _draft(sid)
    hook = dict(M.text_boxes(s))["hook"]
    assert all(not _overlap(hook, b["box"]) for b in M.layout(s)["bubbles"])
    assert K.in_safe_area(hook)


@pytest.mark.parametrize("sid", ALL)
def test_the_stack_is_in_the_lower_half_under_the_rule_and_off_the_chat(sid):
    s = _draft(sid)
    tl = R.estimated_timeline(s)
    lay, plan = M.layout(s), M.scroll_plan(s, tl)
    lift = plan["lift"]
    if not M.examples(s, tl):                                       # nothing to stack: no scroll
        assert lift == 0
        return
    rule = lay["rule"][2]
    assert plan["stack_top"] >= rule[3] - lift                      # under the rule as it ends up
    assert plan["stack_top"] >= K.H * 0.45                          # the lower half
    bottom = plan["stack_top"] + plan["slots"] * (M.EX_H + M.EX_GAP) - M.EX_GAP
    assert bottom <= K.SAFE_BOTTOM                                  # out of the bottom 22 %
    for b in lay["bubbles"]:
        x0, y0, x1, y1 = b["box"]
        assert y1 - lift <= plan["stack_top"]                       # the chat stays above the stack


@pytest.mark.parametrize("sid", ALL)
def test_scrolling_never_hides_the_error_under_the_header(sid):
    s = _draft(sid)
    err = next(b for b in M.layout(s)["bubbles"] if b["error"])
    assert err["box"][1] - 16 - M.layout(s)["max_lift"] >= M.HEADER_Y1 + 20     # its ring too

#!/usr/bin/env python3
"""STEP 63 §0: three fixes from the STEP 62 renders. No render, no API.

1. the pencil covers no text in the last frames of any level type;
2. choose_level's circles and strikes keep 8 px from the tier dividers;
3. the level types get a 1800 s render limit, every other type keeps 1200 s.
"""
import copy
import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FIXTURES = ROOT / "tests" / "fixtures" / "scripts"
LEVEL_FIXTURES = {
    "level_test": "level_test_lv001.json",
    "say_it_level": "say_it_level_sy001.json",
    "true_false_level": "true_false_level_tf001.json",
    "fill_level": "fill_level_fc001.json",
    "choose_level": "choose_level_ec001.json",
    "phrases_level": "phrases_level_vf001.json",
}


def _timeline(vtype):
    """segment_times shaped like generate_level_audio_segmented's; phrases_level has no
    tiers and no verdict."""
    import video.how_do_you_say as H
    data = json.loads((FIXTURES / LEVEL_FIXTURES[vtype]).read_text(encoding="utf-8"))
    tiers = H.LEVEL_MODES[vtype].get("tiers", True)
    st = {"intro": {"start": 0.0, "end": 4.0}}
    t = 4.5
    for i in range(1, len(data["items"]) + 1):
        if tiers and i in (4, 8):
            st[f"tier_{i}"] = {"start": t, "end": t + 1.5}; t += 1.8
        st[f"think_{i}"] = {"start": t, "end": t + 3.0}; t += 3.0
        st[f"answer_{i}"] = {"start": t, "end": t + 1.5}; t += 1.9
    if tiers:
        st["verdict"] = {"start": t, "end": t + 6.0}; t += 6.5
    st["outro"] = {"start": t, "end": t + 3.0}
    data = copy.deepcopy(data)
    data["segment_times"] = st
    return data, t + 3.0


def _overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_the_pencil_box_constant_is_the_pencil_image():
    import video.how_do_you_say as H
    img, (c, _c) = H.pencil_image()
    assert tuple(v - c for v in img.getbbox()) == H.PENCIL_BOX


@pytest.mark.parametrize("vtype", sorted(LEVEL_FIXTURES))
def test_in_the_last_frames_the_pencil_covers_no_text(vtype):
    """After the last answer (the frame the viewer is left reading) and in the video's
    final frame, the pencil's box intersects no text box of any row on the last page."""
    import video.how_do_you_say as H
    data, dur = _timeline(vtype)
    kind = H.LEVEL_MODES[vtype].get("kind", "write")
    items = data["items"]
    tl = H.LevelTimeline(data, dur)
    layout = H.level_layout(vtype, items)
    boxes = H.level_text_boxes(vtype, items, layout)
    last = layout.rows_on(len(layout.pages) - 1)
    for t in (tl.verdict[0] - 0.01, dur - 0.01):
        x, y = H.level_pencil_position(t, tl, items, layout, kind)
        sprite, (tx, ty) = H._pencil_cropped(int(round(H.level_pencil_angle(t, tl, kind) / 6) * 6))
        pencil = (x - tx, y - ty, x - tx + sprite.width, y - ty + sprite.height)
        hit = [(i + 1, b) for i in last for b in boxes[i] if _overlaps(pencil, b)]
        assert not hit, f"{vtype} t={t:.2f}: pencil {pencil} covers rows {hit}"


def test_the_pencil_still_writes_the_last_answer_before_it_parks():
    """The park starts when the last answer is written, not before."""
    import video.how_do_you_say as H
    data, dur = _timeline("fill_level")
    items = data["items"]
    tl = H.LevelTimeline(data, dur)
    layout = H.level_layout("fill_level", items)
    spans = H.fill_spans(items, layout)
    end = tl.answer[-1][1]
    assert H.level_pencil_position(end, tl, items, layout, "fill") == \
        pytest.approx((spans[-1][1], spans[-1][2]))


def test_level_text_boxes_hold_the_longest_drawn_line():
    """The boxes the pencil avoids are as wide as the drawn text: every translation line of
    fc001, measured on its own strip, ends inside its box."""
    import video.how_do_you_say as H
    data, _dur = _timeline("fill_level")
    items = data["items"]
    layout = H.level_layout("fill_level", items)
    boxes = H.level_text_boxes("fill_level", items, layout)
    for row, row_boxes in zip(layout.rows, boxes):
        for (text, _y), box in zip(row.l2, row_boxes[len(row.l1):]):
            strip = H._line_image(text, layout.size, (0, 0, 0, 255))
            assert H.LINE_X - 2 + strip.getbbox()[2] <= box[2]


# ── 2. choose_level: 8 px between a circle or strike and a tier divider ──

def _longest_pair_everywhere():
    import video.how_do_you_say as H
    data = json.loads((FIXTURES / LEVEL_FIXTURES["choose_level"]).read_text(encoding="utf-8"))
    longest = max(data["items"], key=lambda it: len(H.choice_line(it)))
    data["items"] = [dict(it, options=list(longest["options"])) for it in data["items"]]
    return data["items"]


@pytest.mark.parametrize("right", [0, 1])
def test_choose_circles_and_strikes_keep_8px_from_the_tier_dividers(right):
    import video.how_do_you_say as H
    items = [dict(it, answer=right) for it in _longest_pair_everywhere()]
    layout = H.level_layout("choose_level", items)
    # a divider is drawn where a tier starts on the same page (see _static_level_page)
    dividers = [(layout.rows[s - 1].page, layout.rows[s - 1].bottom - 4 + H.TIER_GAP / 2)
                for s in H.TIER_STARTS if layout.rows[s].page == layout.rows[s - 1].page]
    half = 11 / 2                                   # the ink under the tier colour
    for i, spans in enumerate(H.choice_spans(items, layout)):
        cy = layout.rows[i].l2[0][1]
        layer = Image.new("RGBA", (H.LAYER_W, H.LAYER_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer, "RGBA")
        H._hand_circle(draw, H.circle_box(spans, right, cy, layout.size), 1.0)
        H._strike(draw, *spans[1 - right], cy, 1.0)
        top, bottom = layer.getbbox()[1] - H.PAD, layer.getbbox()[3] - H.PAD
        for page, d in dividers:
            if page != layout.rows[i].page:
                continue
            gap = (d - half) - bottom if d > cy else top - (d + half)
            assert gap >= 8, f"row {i + 1}: {gap:.1f} px from the divider at {d}"


@pytest.mark.parametrize("vtype", sorted(LEVEL_FIXTURES))
def test_the_rows_fit_the_band_at_42px_or_more_and_8_to_a_page(vtype):
    """STEP 77 §4: one size ≥ LINE_FONT_MIN; every row inside the page's band; ≤ 8 rows a page."""
    import video.how_do_you_say as H
    data, _dur = _timeline(vtype)
    layout = H.level_layout(vtype, data["items"])
    assert H.LINE_FONT_MIN == 42 and layout.size >= 42
    assert all(H.ROWS_TOP - 1e-6 <= r.top and r.bottom <= H.ROWS_BOTTOM + 1e-6 for r in layout.rows)
    assert all(b - a <= H.ROWS_PER_PAGE for a, b in layout.pages)
    f = H.fredoka(layout.size)
    for r in layout.rows:
        assert all(H._line_w(t, f, layout.blank) <= H.LINE1_W for t, _y in r.l1)
        assert all(f.getlength(t) <= H.LINE_W for t, _y in r.l2)


# ── 3. the render limit ─────────────────────────────────────────────

def test_a_level_type_gets_1800s_and_the_others_keep_1200s():
    import pipeline
    from video.how_do_you_say import LEVEL_MODES
    from video_types import LEVEL_TYPES, VIDEO_TYPES
    assert LEVEL_TYPES == set(LEVEL_MODES)
    for vtype in VIDEO_TYPES:
        assert pipeline.render_timeout(vtype) == (1800 if vtype in LEVEL_TYPES else 1200), vtype
    assert pipeline.render_timeout(None) == 1200


def test_the_dashboard_render_uses_the_per_type_limit():
    src = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    assert "timeout=pipeline.render_timeout(video_type)" in src
    assert "timeout=pipeline.RENDER_TIMEOUT_S" not in src

"""STEP 77 §4: the notebook Shorts' frame layer and the platforms' safe areas.

TikTok, Reels and Shorts put their top tabs over the first ~190 px, their button rail right
of x 940 from y 950 down, and captions over the bottom ~22 % (below y 1450). Nothing the
viewer reads may sit there; the brand moves from the frame onto the page's footer.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import video.how_do_you_say as H  # noqa: E402
from video.notebook import kit  # noqa: E402

LEVELS = ("level_test", "say_it_level", "true_false_level", "fill_level", "choose_level", "phrases_level")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _hdys():
    T = _load("t_hdys_s", ROOT / "tests" / "test_how_do_you_say.py")
    return T._timeline(T._script())


def _level(vtype):
    return _load("t_s63_s", ROOT / "tests" / "test_level_step63_fixes.py")._timeline(vtype)


def _in_safe_area(box):
    """box: page-local (x0, y0, x1, y1). Every corner, tilted onto the frame, is readable there."""
    for x, y in ((box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])):
        fx, fy = H.page_to_frame(x, y)
        if fy > 1450 or (fy > 950 and fx > 940) or fy < 190:
            return False
    return True


def test_notebook_frames_draw_no_progress_bar_and_no_watermark(monkeypatch):
    import video.brand as brand
    import video.utils as utils
    monkeypatch.setattr(brand, "draw_watermark", lambda *a, **k: pytest.fail("watermark drawn"))
    monkeypatch.setattr(utils, "draw_progress_bar", lambda *a, **k: pytest.fail("progress bar drawn"))
    data, dur = _hdys()
    H.create_frame_how_do_you_say(dur * 0.5, data, dur)
    d, ldur = _level("choose_level")
    H.create_frame_level(ldur * 0.5, d, ldur)


def test_the_brand_footer_is_on_the_page_inside_the_safe_area():
    foot = kit.footer(H.FOOTER_SIZE)
    cx = (64 + H.PAGE_W) / 2
    box = (cx - foot.width / 2, H.FOOTER_CY - foot.height / 2, cx + foot.width / 2, H.FOOTER_CY + foot.height / 2)
    assert _in_safe_area(box)                                       # addendum B4: out of the caption zone
    assert box[3] < H.PAGE_H - 8 and H.ROWS_BOTTOM <= box[1]        # on the paper, under the rows
    page = np.asarray(H._static_page(tuple((it["spanish"], it["emoji"]) for it in _hdys()[0]["items"]), "x"))
    x0, y0 = (int(v) for v in H._p(box[0], box[1]))
    assert (page[y0:y0 + foot.height, x0:x0 + foot.width, :3].astype(int).sum(axis=2) < 400).sum() > 200


def test_the_title_sits_below_the_top_tabs():
    assert H.TITLE_Y >= 90
    assert H.page_to_frame(H.PAGE_W / 2, H.TITLE_Y)[1] >= 190


def test_every_word_and_tick_of_how_do_you_say_is_in_the_safe_area():
    data, _dur = _hdys()
    for it, cy in zip(data["items"], H.row_centres(len(data["items"]))):
        f, _s, w = H.fit_word(it["english"], H.ENGLISH_W)
        top, bottom = cy - 30, cy + 30
        assert _in_safe_area((H.ENGLISH_X, top, H.ENGLISH_X + w + H.TICK_GAP + H.TICK_SIZE + 6, bottom)), it
        _f, _s, ws = H.fit_word(it["spanish"], H.SPANISH_W)
        assert _in_safe_area((H.SPANISH_X, top, H.SPANISH_X + ws, bottom)), it


@pytest.mark.parametrize("vtype", LEVELS)
def test_every_line_of_a_level_page_is_in_the_safe_area(vtype):
    d, _dur = _level(vtype)
    layout = H.level_layout(vtype, d["items"])
    for i, boxes in enumerate(H.level_text_boxes(vtype, d["items"], layout)):
        for box in boxes:
            assert _in_safe_area(box), (vtype, i + 1, box)


def test_nothing_the_viewer_reads_is_under_42px_and_tier_labels_are_32():
    assert min(H.LINE_FONT_MIN, H.NUM_SIZE, H.NOTE_FONT, H.THEME_SIZE, H.WORD_FONT_MIN) >= 42
    assert H.LABEL_SIZE >= 32


def test_the_pencil_is_200px_with_a_soft_shadow():
    assert kit.PENCIL_LENGTH == 200
    plain, _tip = kit.pencil()
    sprite, _tip = H._pencil_cropped()
    soft = np.asarray(sprite)[:, :, 3]
    assert ((soft > 0) & (soft < 60)).sum() > 1500                     # the blurred shadow's ramp
    assert sprite.width > plain.getbbox()[2] - plain.getbbox()[0]      # it reaches past the pencil


@pytest.mark.parametrize("vtype", LEVELS)
def test_while_the_viewer_thinks_the_pencil_stands_in_the_margin_over_no_text(vtype):
    d, dur = _level(vtype)
    tl = H.LevelTimeline(d, dur)
    layout = H.level_layout(vtype, d["items"])
    kind = H.LEVEL_MODES[vtype].get("kind", "write")
    boxes = H.level_text_boxes(vtype, d["items"], layout)
    for i in range(len(d["items"])):
        th0, th1 = tl.think[i]
        t = (th0 + th1) / 2
        x, y = H.level_pencil_position(t, tl, d["items"], layout, kind)
        angle = H.level_pencil_angle(t, tl, kind)
        assert angle == H.PENCIL_PARK_ANGLE and x == H.PENCIL_WAIT_X > H.CONTENT_R
        sprite, (tx, ty) = H._pencil_cropped(int(round(angle / 6) * 6))
        a = np.asarray(sprite)[:, :, 3] > 60                              # the pencil, not its shadow
        ys, xs = np.nonzero(a)
        pencil = (x - tx + xs.min(), y - ty + ys.min(), x - tx + xs.max(), y - ty + ys.max())
        for j in layout.rows_on(layout.rows[i].page):
            for b in boxes[j]:
                assert not (pencil[0] < b[2] and b[0] < pencil[2] and pencil[1] < b[3] and b[1] < pencil[3]), \
                    (vtype, i + 1, j + 1, b)


def test_a_level_video_turns_the_page_when_its_rows_do_not_fit_one():
    d, dur = _level("choose_level")
    tl = H.LevelTimeline(d, dur)
    layout = H.level_layout("choose_level", d["items"])
    assert len(layout.pages) == 2
    enters = H.page_enters(tl, layout)
    second = layout.pages[1][0]
    assert tl.answer[second - 1][1] < enters[1] <= tl.answer[second][0]
    assert H.current_page(enters[1] - 0.01, enters) == 0 and H.current_page(enters[1], enters) == 1
    # the old page leaves through the top before the new one rises
    leaving = H.page_motion(enters[1] - 0.01, 0.0, enters[1], (1e9, 1e9))[0]
    assert H.PAGE_Y - H.PAD + leaving + H.LAYER_H < 100
    assert H.page_motion(enters[1], enters[1], dur, (1e9, 1e9))[0] == H.RISE_FROM

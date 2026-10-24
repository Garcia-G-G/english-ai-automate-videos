"""STEP 77 §3: the notebook Shorts move — opening, writing, recap, CTA, hand-off, outro —
plus the stills-review fixes (tick gap, unclipped pencil, no background seam)."""
import copy
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import video.how_do_you_say as H  # noqa: E402
from video.notebook import kit  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _hdys():
    T = _load("t_hdys_m", ROOT / "tests" / "test_how_do_you_say.py")
    return T._timeline(T._script())


def _level(vtype):
    return _load("t_s63_m", ROOT / "tests" / "test_level_step63_fixes.py")._timeline(vtype)


@pytest.fixture
def flat(monkeypatch):
    monkeypatch.setattr(H, "create_base_frame", lambda t: (lambda f: (f, ImageDraw.Draw(f, "RGBA")))(
        Image.new("RGBA", (1080, 1920), (40, 60, 90, 255))))


def _alpha_box(img):
    return Image.Image.getbbox(img.getchannel("A"))


# ── opening ──────────────────────────────────────────────────────────

def test_the_page_rises_with_an_overshoot_pushes_over_the_recap_and_leaves_through_the_top():
    push = (50.0, 60.0)
    assert H.page_motion(0.0, 0.0, 70.0, push) == (float(H.RISE_FROM), 1.0)
    rise = [H.page_motion(k / 100, 0.0, 70.0, push)[0] for k in range(0, 51)]
    assert min(rise) < 0 and rise[-1] == 0.0                   # overshoots, then settles
    assert H.page_motion(55.0, 0.0, 70.0, push)[1] == pytest.approx(1.02, abs=0.004)
    assert H.page_motion(60.0, 0.0, 70.0, push)[1] == H.PUSH_TO
    assert H.page_motion(30.0, 30.0, 70.0, push)[0] == float(H.RISE_FROM)   # a later page rises too
    dy, _s = H.page_motion(70.0, 0.0, 70.0, push)
    assert H.PAGE_Y - H.PAD + dy + H.LAYER_H <= 0               # the page is out of the frame


def test_rows_cascade_in_fifty_ms_apart():
    assert H.cascade(0, 0.2) == 0 and H.cascade(1, 0.25) == 0
    assert H.cascade(0, 0.35) == pytest.approx(H.cascade(1, 0.40))
    assert all(H.cascade(i, 1.0) == 1.0 for i in range(10))


def test_the_hook_comes_from_the_script_or_the_theme_and_leaves_with_the_intro():
    data, _dur = _hdys()
    assert H.hook_text(dict(data, theme="el restaurante")) == "¿Sabes decir estas 10 palabras del restaurante?"
    assert H.hook_text(dict(data, hook="¿Lo sabías?")) == "¿Lo sabías?"
    end = H.hook_end(data, 4.5)
    assert end == data["segment_times"]["intro"]["end"]
    assert H.hook_state(0.3, end) == (0.0, 0.0)
    s, a = H.hook_state(1.0, end)
    assert a == 1.0 and 0.95 <= s <= 1.05
    assert H.hook_state(end + H.HOOK_OUT, end) == (0.0, 0.0)
    assert 64 <= H.HOOK_SIZE <= 72


# ── writing ──────────────────────────────────────────────────────────

def test_the_highlighter_swipes_left_to_right():
    boxes = []
    for dt in (0.04, 0.1, 0.3):
        layer = Image.new("RGBA", (H.LAYER_W, H.LAYER_H), (0, 0, 0, 0))
        H._highlight(layer, 56, 400, 10.0 + dt, 10.0, 20.0)
        boxes.append(_alpha_box(layer))
    assert boxes[0][0] == boxes[1][0] == boxes[2][0]               # one left edge
    assert boxes[0][2] < boxes[1][2] < boxes[2][2] or boxes[1][2] == boxes[2][2]
    assert boxes[2][2] - boxes[0][2] > 100


def test_the_emoji_pop_peaks_at_1_15():
    peak = max(H.EMOJI_POP_FROM + (1 - H.EMOJI_POP_FROM) * H.ease_out_back(k / 200, H.EMOJI_OVERSHOOT)
               for k in range(201))
    assert peak == pytest.approx(1.15, abs=0.01)


def test_a_tick_is_drawn_along_its_stroke():
    def ink(p):
        layer = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        kit.tick(layer, 50, 100, 1.0, 34, progress=p)
        return np.asarray(layer)[:, :, 3].astype(int).sum()
    assert 0 < ink(0.3) < ink(0.7) < ink(1.0)


def test_the_word_being_written_has_a_12px_feathered_edge():
    word = H._word_image("grandmother", H.ENGLISH_W, H._color("english_blue"))
    part = H._written(word, 0.5)
    cut = round(word.width * 0.5)
    assert part.width == cut + H.FEATHER // 2
    a = np.asarray(part)[:, :, 3].astype(float)
    full = np.asarray(word.crop((0, 0, part.width, word.height)))[:, :, 3].astype(float)
    k = full.sum(axis=0) > 0
    ratio = a.sum(axis=0)[k] / full.sum(axis=0)[k]
    cols = np.arange(part.width)[k]
    assert np.all(ratio[cols < cut - 6] == 1.0)
    edge = ratio[cols >= cut - 6]
    assert np.all(np.diff(edge) <= 1e-9) and edge[-1] < 0.2   # falls off over the last 12 px


def test_the_pencil_wobbles_while_writing_and_lifts_between_rows():
    assert max(abs(v) for k in range(300) for v in H.wobble(k / 30)) <= H.WOBBLE
    a, b = (100, 400), (300, 600)
    mid = H._glide(a, b, 0.5 * H.PENCIL_MOVE, 0.0)
    assert mid[1] == pytest.approx(500 - H.LIFT, abs=0.5)
    assert H._glide(a, b, H.PENCIL_MOVE, 0.0) == b


# ── recap, CTA ───────────────────────────────────────────────────────

def test_the_recap_re_sweeps_each_row_as_the_voice_reaches_it(flat):
    data, dur = _hdys()
    tl = H.Timeline(data, dur)
    pulses = H._recap_word_times(data["recap"], data["items"], tl.recap)
    k = next(i for i, p in enumerate(pulses) if p is not None and i > 0)
    cy = H.row_centres(len(data["items"]))[k]
    _x, fy = H.page_to_frame(300, cy)

    def yellow(t):
        f = H.create_frame_how_do_you_say(t, copy.deepcopy(data), dur)
        band = f[int(fy) - 30:int(fy) + 30, 700:900].astype(int)
        y = np.array(H._color("brand_yellow")[:3])
        return (np.abs(band - y).sum(axis=2) < 60).sum()
    assert yellow(pulses[k] + 0.2) > 3 * yellow(pulses[k] - 0.6) + 100


def test_the_cta_pops_with_an_overshoot_on_the_spoken_outro_and_covers_the_title():
    assert H.cta_scale(9.9, 10.0) == 0.0
    curve = [H.cta_scale(10.0 + k / 100, 10.0) for k in range(60)]
    assert max(curve) > 1.0 and curve[-1] == 1.0
    for title in ("How do you say?", "¿Verdadero o falso?", "Elige la correcta"):
        f, *_ = H.fit_word(title, H.PAGE_W - 140, H.TITLE_SIZE, 56)
        assert H.cta_width(f.getlength(title)) >= f.getlength(title) + 2 * 8 + 24   # its marker stroke, and air


# ── stills review (addendum B) ───────────────────────────────────────

def _ink_right(img, x):
    return x + _alpha_box(img)[2]


def _tick_ink_left(x, cy):
    layer = Image.new("RGBA", (H.LAYER_W, H.LAYER_H), (0, 0, 0, 0))
    H._draw_tick(layer, x, cy, 1.0)
    return _alpha_box(layer)[0] - H.PAD


def test_the_tick_keeps_14px_from_the_word_in_how_do_you_say_and_the_writing_modes():
    data, _dur = _hdys()
    for it, cy in zip(data["items"], H.row_centres(len(data["items"]))):
        word = H._word_image(it["english"], H.ENGLISH_W, H._color("english_blue"))
        _f, _s, w = H.fit_word(it["english"], H.ENGLISH_W)
        assert _tick_ink_left(H.ENGLISH_X + w + H.TICK_GAP, cy) - _ink_right(word, H.ENGLISH_X - 2) >= 14
    for vtype in ("level_test", "say_it_level", "phrases_level", "fill_level", "true_false_level"):
        d, _ = _level(vtype)
        layout = H.level_layout(vtype, d["items"])
        for i, row in enumerate(layout.rows):
            text, _y = row.l2[-1]
            line = H._line_image(text, layout.size, H._color("ink"))
            x, _y = H._line_end(layout, i)
            assert _tick_ink_left(x + H.TICK_GAP, 600) - _ink_right(line, H.LINE_X - 2) >= 14, vtype


def test_the_tick_keeps_14px_from_the_circle_and_the_strike_in_choose_level():
    d, _ = _level("choose_level")
    layout = H.level_layout("choose_level", d["items"])
    for it, spans, row in zip(d["items"], H.choice_spans(d["items"], layout), layout.rows):
        cy = row.l2[0][1]
        right = it["answer"]
        layer = Image.new("RGBA", (H.LAYER_W, H.LAYER_H), (0, 0, 0, 0))
        H._hand_circle(layer, H.circle_box(spans, right, cy, layout.size), 1.0)
        H._strike(layer, *spans[1 - right], cy, 1.0)
        marks_right = _alpha_box(layer)[2] - H.PAD
        assert _tick_ink_left(H.choose_tick_x(spans, right), cy) - marks_right >= 14


@pytest.mark.parametrize("vtype", ["choose_level", "fill_level", "say_it_level", "true_false_level"])
def test_the_pencil_is_never_cut_by_the_page_or_the_frame(vtype):
    """Every 0.25 s, at every angle it takes, the pencil sprite (with its shadow) lies inside
    the frame; on row 6 every pixel of it lands (addendum B2)."""
    d, dur = _level(vtype)
    tl = H.LevelTimeline(d, dur)
    layout = H.level_layout(vtype, d["items"])
    kind = H.LEVEL_MODES[vtype].get("kind", "write")
    enters = H.page_enters(tl, layout)
    t = H.RISE
    while t < dur - H.HANDOFF:
        page = H.current_page(t, enters)
        leave = enters[page + 1] if page + 1 < len(enters) else dur
        if not (enters[page] + H.RISE <= t <= leave - H.HANDOFF):
            t += 0.25
            continue                                     # the page itself is moving in or out
        at = H.level_pencil_position(t, tl, d["items"], layout, kind)
        angle = H.level_pencil_angle(t, tl, kind)
        sprite, (tx, ty) = H._pencil_cropped(int(round(angle / 6) * 6))
        fx, fy = H.page_to_frame(*at, H.page_motion(t, enters[page], leave, (tl.answer[-1][1], tl.outro[0])))
        assert 0 <= fx - tx and fx - tx + sprite.width <= 1080, (vtype, t)
        assert 0 <= fy - ty and fy - ty + sprite.height <= 1920, (vtype, t)
        t += 0.25
    row6 = tl.think[5][0] + 0.5                              # waiting by row 6, standing in the margin
    angle = int(round(H.level_pencil_angle(row6, tl, kind) / 6) * 6)
    sprite, _tip = H._pencil_cropped(angle)
    frame = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    H._place_pencil(frame, *H.level_pencil_position(row6, tl, d["items"], layout, kind), H.STILL, angle)
    assert np.asarray(frame)[:, :, 3].astype(int).sum() == pytest.approx(
        np.asarray(sprite)[:, :, 3].astype(int).sum(), rel=0.01)   # every pixel of it landed


def test_the_fallback_background_has_no_seam():
    from video import backgrounds as B
    B.reset_background()
    for t in (0.0, 7.3, 21.0, 40.0):
        g = B.gradient(1080, 1920, t).astype(int)
        assert np.abs(np.diff(g, axis=0)).max() < 40, t


# ── outro ────────────────────────────────────────────────────────────

def test_the_outro_card_enters_with_an_overshoot_and_bubi_waves():
    from video import outro as O
    dys = [O.card_dy(k / 100) for k in range(0, 51)]
    assert dys[0] == O.ENTER_FROM and min(dys) < 0 and O.card_dy(O.ENTER) == 0
    poses = [O.wave_pose(O.ENTER + (k + 0.5) * O.WAVE_STEP) for k in range(O.WAVE_SWINGS + 2)]
    assert poses[:O.WAVE_SWINGS] == [1, -1] * (O.WAVE_SWINGS // 2) and poses[-1] == 0
    variant = O.load_variants()["variants"][0]
    rest = O._make_frame_fn(variant)(3.0)
    assert np.abs(rest.astype(int) - np.asarray(O.outro_still(variant)).astype(int)).max() <= 1

"""STEP 78 §0: polish from the review of the STEP 77 §9 proofs."""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import video.how_do_you_say as H  # noqa: E402

#: The four STEP 77 §9 proofs, read from their cached artifacts (skipped where they are absent).
PROOFS = {"choose_level": "elige_la_correcta_20261022_020511", "fill_level": "completa_la_frase_20261022_020722",
          "true_false_level": "verdadero_o_falso_20261022_020921", "phrases_level": "cómo_se_dice_20261022_021147"}


def _proof(vtype):
    path = ROOT / "output" / "audio" / vtype / f"{PROOFS[vtype]}.json"
    if not path.exists():
        pytest.skip(f"no cached artifact {path.name}")
    d = json.loads(path.read_text(encoding="utf-8"))
    return d, d["duration"]


def _fixture(vtype):
    spec = importlib.util.spec_from_file_location("t_s63_78", ROOT / "tests" / "test_level_step63_fixes.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m._timeline(vtype)


@pytest.fixture
def flat_untilted(monkeypatch):
    """Frames on a flat ground with the page not tilted, so page-local x/y read off the frame."""
    monkeypatch.setattr(H, "create_base_frame", lambda t: (lambda f: (f, ImageDraw.Draw(f, "RGBA")))(
        Image.new("RGBA", (1080, 1920), (40, 60, 90, 255))))
    monkeypatch.setattr(H, "_rotate", lambda layer, scale=1.0: layer)
    monkeypatch.setattr(H, "TILT_DEG", 0.0)
    H._PAGES.clear()
    yield
    H._PAGES.clear()


def _page_px(frame, x, y):
    """Frame pixel of page-local (x, y) on an untilted, unmoved page."""
    return int(round(x + H.PAGE_X)), int(round(y + H.PAGE_Y))


# ── 1. the pencil stands clear of every text box while the viewer thinks ──

@pytest.mark.parametrize("vtype", sorted(PROOFS))
@pytest.mark.parametrize("source", ["proof", "fixture"])
def test_while_the_viewer_thinks_the_pencil_covers_no_text(vtype, source):
    d, dur = _proof(vtype) if source == "proof" else _fixture(vtype)
    tl = H.LevelTimeline(d, dur)
    layout = H.level_layout(vtype, d["items"])
    kind = H.LEVEL_MODES[vtype].get("kind", "write")
    boxes = H.level_text_boxes(vtype, d["items"], layout)
    for i in range(tl.n):
        th0, th1 = tl.think[i]
        end = th1 - H.PENCIL_MOVE if kind != "tf" else th1     # the last 0.35 s it comes in to write
        for k in range(9):
            t = th0 + (end - th0) * k / 8
            x, y = H.level_pencil_position(t, tl, d["items"], layout, kind)
            sprite, (tx, ty) = H._pencil_cropped(int(round(H.level_pencil_angle(t, tl, kind) / 6) * 6))
            ys, xs = np.nonzero(np.asarray(sprite)[:, :, 3] > 60)
            pb = (x - tx + xs.min(), y - ty + ys.min(), x - tx + xs.max(), y - ty + ys.max())
            for j in layout.rows_on(layout.rows[i].page):
                for b in boxes[j]:
                    assert not (pb[0] < b[2] and b[0] < pb[2] and pb[1] < b[3] and b[1] < pb[3]), \
                        (vtype, source, f"row {i + 1} at {t:.2f}s covers row {j + 1}", b)


# ── 2. a filled blank closes up to normal word spacing ──

@pytest.mark.parametrize("source", ["proof", "fixture"])
def test_a_filled_line_has_normal_word_spacing(flat_untilted, source):
    d, dur = _proof("fill_level") if source == "proof" else _fixture("fill_level")
    tl = H.LevelTimeline(d, dur)
    layout = H.level_layout("fill_level", d["items"])
    f = H.fredoka(layout.size)
    space = f.getlength(" ")
    for i in (0, 3, 6, 7, 8):                     # rows on both pages (10 is under the closing push)
        t = tl.answer[i][1] + H.REFLOW + 0.05
        frame = H.create_frame_level(t, copy.deepcopy(d), dur)
        bx, y1 = H.blank_at(layout, i)
        x0, ya = _page_px(frame, H.LINE_X - 4, y1 - layout.size * 0.32)
        x1, yb = _page_px(frame, H.CONTENT_R + 4, y1 + layout.size * 0.2)
        band = frame[ya:yb, x0:x1].astype(int)
        inked = (band.sum(axis=2) < 360).any(axis=0)                 # ink and blue, not the marker
        cols = np.nonzero(inked)[0]
        runs, gap = [], 0
        for c in range(cols.min(), cols.max() + 1):
            if inked[c]:
                if gap:
                    runs.append(gap)
                gap = 0
            else:
                gap += 1
        assert max(runs) <= 1.6 * space, (source, i + 1, max(runs), space)


# ── 3. a tier tab's label fits inside its tab ──

@pytest.mark.parametrize("rows", [1, 2, 3, 4, 5])
def test_the_tab_label_fits_its_tab(rows):
    for word, colour, _a, _b in H.TIERS:
        for pitch in (126, 150, 180):              # the shortest row (2 lines at 42 px) and taller
            height = rows * pitch - 8                   # top + 4 .. bottom - 4
            label, size = H.tier_label(word, height)
            assert size >= H.LABEL_MIN
            assert H.fredoka(size).getlength(label) <= height - 2 * H.LABEL_PAD, (word, rows, pitch)
            pill = H._tier_pill(word, colour, height)
            assert pill.getbbox() is not None
    assert H.tier_label("INTERMEDIO", 120)[0] == "MEDIO"


# ── 4. a row enters as one unit ──

def test_a_row_that_has_not_started_its_cascade_draws_nothing_at_all(flat_untilted, monkeypatch):
    # The cascade now ends before frame 1 (whole list on frame 1); its mechanics are tested at
    # the old start, where a frame can still catch it.
    monkeypatch.setattr(H, "CASCADE_START", 0.2)
    d, dur = _fixture("choose_level")
    layout = H.level_layout("choose_level", d["items"])
    t = H.CASCADE_START + 4 * H.CASCADE_STAGGER - 0.01          # row 5 has not started
    assert H.cascade(4, t) == 0 and H.cascade(0, t) > 0
    frame = H.create_frame_level(t, copy.deepcopy(d), dur)
    row = layout.rows[4]
    x0, ya = _page_px(frame, H.LINE_X, row.top + 6)
    x1, yb = _page_px(frame, H.CONTENT_R, row.bottom - 8)
    band = frame[ya:yb, x0:x1].astype(int)
    dark = (np.abs(band - np.array(H.PAPER[:3])).sum(axis=2) > 200).sum()
    assert dark == 0, f"row 5 drew {dark} ink pixels before its turn (blank line, options…)"


def test_during_the_cascade_every_part_of_a_row_goes_through_one_band(monkeypatch):
    monkeypatch.setattr(H, "CASCADE_START", 0.2)                # see the test above
    d, dur = _fixture("choose_level")
    seen = {}
    real = H._rows_in
    monkeypatch.setattr(H, "_rows_in", lambda layer, img, rows, t: seen.setdefault("img", img) and real(layer, img, rows, t))
    targets = []
    real_choose = H._draw_choose_answers
    monkeypatch.setattr(H, "_draw_choose_answers", lambda target, *a: targets.append(target) or real_choose(target, *a))
    H.create_frame_level(0.4, copy.deepcopy(d), dur)
    assert "img" in seen and isinstance(targets[0], H._PageRecorder) and targets[0].ops[0][0] is H._blank_layer()


# ── 5. footage of the theme's place, or one calm set ──

def test_a_place_theme_gets_that_place_and_an_abstract_theme_the_calm_set():
    import topic_clips as T
    assert T.place_queries("en un restaurante")[0].startswith("restaurant")
    assert T.place_queries("el aeropuerto")[0].startswith("airport")
    assert T.place_queries("entrenar en casa") == [] and T.place_queries("10 kilómetros") == []
    for theme in ("say o tell", "verbos irregulares en pasado", "phrasal verbs"):
        q = T.footage_themes({"type": "choose_level", "theme": theme})
        assert q[0] in T.CALM_FOOTAGE and len(q) >= T.MAX_CLIPS
    q = T.footage_themes({"type": "phrases_level", "theme": "en un restaurante"})
    built = T.build_queries("x", "everyday_expressions", count=T.MAX_CLIPS, themes=q)
    assert built == q[:T.MAX_CLIPS]                                   # no category landscape mixed in
    assert all("restaurant" in x or x in T.CALM_FOOTAGE for x in built)


def test_the_sidecar_logs_each_clips_query_and_id(tmp_path, monkeypatch):
    import topic_clips as T
    src = tmp_path / "cache" / "slot"
    src.mkdir(parents=True)
    (src / "pexels_123.mp4").write_bytes(b"x" * 10)
    (src / "query.json").write_text(json.dumps({"pexels_id": 123}), encoding="utf-8")
    monkeypatch.setattr(T, "fetch_query", lambda q, key=None: src / "pexels_123.mp4")
    out = T.fetch_for_topic("en un restaurante", "everyday_expressions", duration=40, out_dir=tmp_path / "clips",
                            themes=T.footage_themes({"type": "phrases_level", "theme": "en un restaurante"}))
    assert out["clips"][0]["query"].startswith("restaurant") and out["clips"][0]["pexels_id"] == 123

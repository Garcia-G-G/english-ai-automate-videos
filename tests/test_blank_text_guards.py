"""Pins for the small guards kept in STEP 68 §2: blank text draws nothing, a pinned
band survives an empty measurement, and length_spec.FIELDS is populated."""
from PIL import Image, ImageDraw


def _canvas():
    frame = Image.new("RGBA", (1080, 1920), (0, 0, 0, 255))
    return frame, ImageDraw.Draw(frame, "RGBA")


def test_a_blank_pill_badge_draws_nothing():
    from video.utils import draw_pill_badge
    frame, draw = _canvas()
    # max_width is what the live fill_blank caller passes; it is the path that wraps
    assert draw_pill_badge(frame, draw, "   ", 540, 900, font_size=30, max_width=900) == (0, 0)


def test_a_blank_vocabulary_cell_draws_nothing():
    import video.vocabulary as voc
    frame, draw = _canvas()
    before = frame.tobytes()
    voc._draw_cell(draw, " ", col_w=400, budget=voc._ROW_TEXT_BUDGET, row_y=500,
                   align_left_from=540, color=(255, 255, 255), alpha=255)
    assert frame.tobytes() == before


def test_a_blank_fill_blank_option_does_not_raise():
    import video.fill_blank as fb
    frame, draw = _canvas()
    fb._draw_option_cards(99.0, draw, frame, ["short", " ", "medio", "otro"],
                          "short", True, 0.0, 1.0)


def test_a_pinned_band_survives_an_empty_directory(tmp_path):
    import clip_contrast as cc
    assert cc.treatment_for_dir(tmp_path, "quiz", band_strength=0.4)["strength"] == 0.4
    assert cc.treatment_for_dir(tmp_path, "quiz")["strength"] == 0.0


def test_length_spec_fields_are_populated():
    import length_spec
    assert length_spec.FIELDS and list(length_spec.FIELDS) == sorted(length_spec.FIELDS)

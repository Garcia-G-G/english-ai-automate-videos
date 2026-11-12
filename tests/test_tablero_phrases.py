"""STEP 82 §6: phrases_level in the Tablero look: one column, English revealed in the done state."""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from video.tablero import frame as F, kit  # noqa: E402
import video.how_do_you_say as H  # noqa: E402


def _data():
    spec = importlib.util.spec_from_file_location("t63", ROOT / "tests" / "test_level_step63_fixes.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m._timeline("phrases_level")


def _phrases():
    out = []
    for p in (ROOT / "content").rglob("phrases_level/*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        out += [(i["spanish"], i["english"]) for i in d.get("items", [])]
    return sorted(set(out))


@pytest.mark.parametrize("spanish,english", _phrases())
def test_every_queued_phrase_fits_two_lines_in_its_column(spanish, english):
    for text, width in ((spanish, kit.PHRASE_COL1_W), (english, kit.PHRASE_COL2_W)):
        size, lines = kit.phrase_lines(text, width)
        assert len(lines) <= 2 and all(kit.fredoka(size).getlength(x) <= width for x in lines), text


def test_ten_tiles_stay_in_the_safe_band():
    h = kit.phrase_height(10)
    assert kit.phrase_origin(0, 10)[1] >= kit.TILE_TOP_LIMIT
    assert kit.phrase_origin(9, 10)[1] + h <= kit.TILE_LIMIT_Y and h >= 90 and kit.phrase_origin(0, 10)[1] >= 410
    assert kit.phrase_height(8) <= 132


def test_the_three_states_differ_and_english_only_shows_when_done():
    a = kit.phrase_tile(0, 10, "¿Cuál es la trampa?", "What's the catch?", "blank")
    b = kit.phrase_tile(0, 10, "¿Cuál es la trampa?", "What's the catch?", "active")
    c = kit.phrase_tile(0, 10, "¿Cuál es la trampa?", "What's the catch?", "done")
    d = kit.phrase_tile(0, 10, "¿Cuál es la trampa?", "Other words", "blank")
    assert len({a.tobytes(), b.tobytes(), c.tobytes()}) == 3 and a.tobytes() == d.tobytes()   # blank leaks nothing


def test_frames_render_through_the_whole_video_and_the_counter_counts():
    data, dur = _data()
    tl_dur = dur
    for t in (0.0, 5.0, 12.0, dur * 0.5, dur - 1.0, dur - 0.05):
        fr = F.create_frame_tablero_phrases(t, data, tl_dur)
        assert fr.shape == (1920, 1080, 3) and fr.dtype == np.uint8
    beats = data["_tablero_beats"]
    assert beats.done_count(0) == 0 and beats.done_count(dur) == len(data["items"])


def test_every_moment_of_a_flip_renders_and_sfx_follow_the_rows():
    data, dur = _data()
    F.create_frame_tablero_phrases(0.0, data, dur)
    tl = data["_tablero_timeline"]
    for k in range(11):
        F.create_frame_tablero_phrases(tl.answer[0][0] + F.FLIP_DUR * k / 10, data, dur)
    events, _ = H.sfx_events(data, dur)
    assert [e[0] for e in events].count("pop") == tl.n and [e[0] for e in events].count("swish") == tl.n


def test_the_dispatch_uses_tablero_for_phrases_level_only():
    from video.tablero import frame
    assert frame.variant({"type": "phrases_level"}) == "tablero"

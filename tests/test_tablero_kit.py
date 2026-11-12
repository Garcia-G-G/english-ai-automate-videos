"""STEP 82 §1: the Tablero kit. Contrast, fit, geometry and a smoke render of every state."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from video.tablero import kit  # noqa: E402

LONGEST = [("toilet paper", "Papel higiénico"), ("dental floss", "Hilo dental"), ("hair dryer", "Secadora de pelo")]


def _queue_items():
    out = []
    for p in (ROOT / "content" / "queue").rglob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if d.get("type") == "how_do_you_say":
            out += [(i["english"], i["spanish"]) for i in d.get("items", [])]
    return out


def test_there_are_nine_families_and_white_text_is_aa_on_each():
    fams = kit.families()
    assert len(fams) == 9
    for name, (_top, bottom) in fams.items():
        assert kit.contrast_with_white(bottom) >= 4.5, name


def test_a_theme_finds_its_family_and_unknown_ones_are_vida_real():
    assert kit.family_for("la casa") == "casa" and kit.family_for("las frutas tropicales") == "comida"
    assert kit.family_for("los saludos") == "vida real" and set(kit.families()) >= {"vida real"}


@pytest.mark.parametrize("english,spanish", LONGEST + sorted(set(_queue_items())))
def test_the_text_stays_inside_its_tile(english, spanish):
    avail = kit.TILE_W - kit.TEXT_PAD_R - kit.TEXT_X
    sp_size, lines = kit.spanish_lines(spanish)
    assert len(lines) <= 2 and all(kit.fredoka(sp_size).getlength(x) <= kit.SPANISH_W for x in lines), spanish
    en_w, _ = kit.tile_english_extent(english, None)
    assert en_w <= avail, english


def test_no_tile_sits_below_1475_or_above_150():
    assert all(kit.TILE_TOP_LIMIT <= kit.tile_origin(i)[1] and kit.tile_bottom(i) <= kit.TILE_LIMIT_Y for i in range(10))


def test_the_grid_matches_the_mock():
    assert kit.tile_origin(0) == (36, 430) and kit.tile_origin(1) == (540, 430) and kit.tile_origin(9) == (540, 1278)


@pytest.mark.parametrize("state", ["blank", "active", "done"])
def test_every_state_draws_and_differs(state):
    im = kit.tile(0, "🏠", "Casa", "house", "jáus", state)
    assert im.size == (kit.TILE_W + 80, kit.TILE_H + 80) and im.getbbox()
    assert im.tobytes() != kit.tile(0, "🏠", "Casa", "house", "jáus", "blank" if state != "blank" else "done").tobytes()


def test_unfilled_letters_show_only_the_first_and_filling_adds_letters():
    a = kit.tile(0, "🏠", "Casa", "house", None, "active", filled=0).tobytes()
    b = kit.tile(0, "🏠", "Casa", "house", None, "active", filled=3).tobytes()
    assert a != b


def test_the_whole_board_composes_at_full_size():
    f = kit.background("casa", 1.0)
    f.alpha_composite(kit.header("🏠", "la casa"), (0, 0))
    for i in range(10):
        kit.place_tile(f, kit.tile(i, "🏠", "Casa", "house", None, "blank"), i)
    kit.place_tile(f, kit.tile(3, "🏠", "Casa", "house", None, "active", timer=0.4), 3, 1.07, -1.5, glow=True)
    kit.place_bubi(f, "simbolo", 0.5)
    kit.draw_outro(f, 1.0, True)
    assert f.size == (1080, 1920)


def test_the_dots_drift():
    assert kit.background("casa", 0).tobytes() != kit.background("casa", 3).tobytes()


@pytest.mark.parametrize("p,ok", [("jáus", True), ("báz-rum", True), ("/haʊs/", False), ("HOUSE", False),
                                  ("a" * 15, False), ("", False)])
def test_figured_pronunciation_rules(p, ok):
    assert kit.valid_pron(p) is ok


def test_the_outro_pill_depends_on_the_sequel():
    assert kit.outro_card(True).tobytes() != kit.outro_card(False).tobytes()


def test_a_pronunciation_that_cannot_fit_is_dropped_not_overflowed():
    long_tag = kit.tile(0, "🍽", "Papel", "toilet paper", "tóilet-péiper", "done")
    plain = kit.tile(0, "🍽", "Papel", "toilet paper", None, "done")
    assert long_tag.tobytes() == plain.tobytes()
    assert kit.tile(0, "🏠", "Casa", "house", "jáus", "done").tobytes() != kit.tile(0, "🏠", "Casa", "house", None, "done").tobytes()


def test_a_long_topic_shrinks_inside_the_chip():
    kit.header("💬", "preguntas del día a día")            # draws without clipping or raising
    assert kit.fredoka(36).getlength("PREGUNTAS DEL DÍA A DÍA") < kit.W - 276

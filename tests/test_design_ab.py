"""STEP 82 §4: Tablero against the notebook. The log is redirected by conftest."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import design_ab as D  # noqa: E402


def _s(theme, n=10):
    return {"type": "how_do_you_say", "theme": theme, "items": [{"english": "x"}] * n}


def test_tablero_is_the_default_and_every_fourth_new_topic_is_the_control():
    got = [D.assign(f"a{i}", _s(f"tema {i}"), date(2026, 11, 13))["variant"] for i in range(8)]
    assert got == ["tablero"] * 3 + ["cuaderno"] + ["tablero"] * 3 + ["cuaderno"]


def test_a_topic_keeps_its_design_on_a_re_render():
    first = D.assign("a1", _s("la casa"), date(2026, 11, 13))
    D.assign("a2", _s("otro"), date(2026, 11, 13))
    assert D.assign("a3", _s("la casa"), date(2026, 11, 13))["variant"] == first["variant"]


def test_after_the_control_window_everything_is_tablero():
    assert [D.assign(f"a{i}", _s(f"t{i}"), date(2026, 12, 1))["variant"] for i in range(4)] == ["tablero"] * 4


def test_other_types_are_outside_the_switch_and_the_sidecar_variants_are_logged():
    assert D.assign("q1", {"type": "quiz", "items": [1]}) is None
    D.assign("a9", _s("x"), date(2026, 11, 13))
    assert D.variants()["a9"] == "tablero"


def _v(design, views, days=10, pct=60.0, title="¿Cómo se dice CASA en inglés?"):
    return {"design_variant": design, "views": views, "days": days, "avg_view_pct": pct, "title": title}


def test_compare_waits_for_six_per_group_and_counts_tier_a_only():
    vids = [_v("tablero", 900)] * 5 + [_v("cuaderno", 1000)] * 6
    assert D.compare(vids)["ready"] is False
    vids = [_v("tablero", 900)] * 6 + [_v("cuaderno", 1000)] * 6 + [_v("tablero", 5, title="¿Cómo se dice HALLOWEEN?")] * 9
    c = D.compare(vids)
    assert c["ready"] and c["groups"]["tablero"]["n"] == 6 and c["loses"] is False


def test_tablero_losing_by_more_than_20_percent_is_flagged_and_young_videos_are_ignored():
    vids = [_v("tablero", 700)] * 6 + [_v("cuaderno", 1000)] * 6
    assert D.compare(vids)["loses"] is True
    young = [_v("tablero", 1, days=2)] * 6 + [_v("cuaderno", 1000)] * 6
    assert D.compare(young)["ready"] is False

"""STEP 78 §1: the «Hecho con Claude» schema, its 108 drafts, queue and panel door."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import series  # noqa: E402
from script_schema import SERIES_LEVELS, SERIES_STYLES, validate_series  # noqa: E402

DRAFTS = sorted((ROOT / "content" / "hecho_con_claude" / "drafts").glob("hc_*.json"))


def _draft(sid):
    return json.loads((ROOT / "content" / "hecho_con_claude" / "drafts" / f"{sid}.json").read_text(encoding="utf-8"))


def test_all_108_drafts_validate_27_per_style_9_per_level():
    assert len(DRAFTS) == 108
    seen = {}
    for p in DRAFTS:
        d = json.loads(p.read_text(encoding="utf-8"))
        validate_series(d)
        assert p.stem == d["id"]
        seen.setdefault(d["style"], []).append(d["level"])
    assert sorted(seen) == sorted(SERIES_STYLES)
    for style, levels in seen.items():
        assert len(levels) == 27 and all(levels.count(lv) == 9 for lv in SERIES_LEVELS), style


@pytest.mark.parametrize("sid, break_it, why", [
    ("hc_m001", lambda d: d.update(scene={"location": "x", "take1": "a", "take2": "b", "note": "n"}), "exactly one block"),
    ("hc_m001", lambda d: d.pop("chat"), "exactly one block"),
    ("hc_e001", lambda d: d.update(id="hc_m001"), "does not match style"),
    ("hc_p001", lambda d: d.update(hashtags=d["hashtags"][:4]), "exactly 5"),
    ("hc_c001", lambda d: d["quiz"].update(options=["a", "b"]), "at least 3"),
    ("hc_c001", lambda d: d["quiz"].update(answer=3), "less than or equal to 2"),
    ("hc_m001", lambda d: d["chat"]["messages"][2].pop(), "exactly one message"),
    ("hc_m001", lambda d: d["voice"].__setitem__(0, "Hola [[I'm 25 y nada más"), "never closed"),
    ("hc_m001", lambda d: d["voice"].__setitem__(0, "[shoutingly] Hola"), "unknown audio tag"),
    ("hc_m001", lambda d: d.update(level="avanzado"), "principiante"),
    ("hc_m001", lambda d: d.pop("challenge"), "challenge"),
])
def test_the_schema_refuses(sid, break_it, why):
    d = copy.deepcopy(_draft(sid))
    break_it(d)
    with pytest.raises(ValueError, match=why):
        validate_series(d)


def test_english_inside_markers_is_not_read_as_an_audio_tag():
    from audio_tags import unknown_tags
    assert unknown_tags("¿[[I have cold]], [[I am cold]]?") == []
    assert unknown_tags("[shoutingly] ¿[[I have cold]]?") == ["[shoutingly]"]


@pytest.fixture
def queue(tmp_path, monkeypatch):
    monkeypatch.setattr(series, "QUEUE_DIR", tmp_path)
    for sid in ("hc_m001", "hc_e001", "hc_p001", "hc_c001"):
        (tmp_path / f"{sid}.json").write_text(json.dumps(_draft(sid), ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_the_queue_filters_by_style_and_level(queue):
    assert [p.stem for p in series.queued()] == ["hc_c001", "hc_e001", "hc_m001", "hc_p001"]
    assert [p.stem for p in series.queued(style="escena")] == ["hc_e001"]
    lv = _draft("hc_p001")["level"]
    assert "hc_p001" in [p.stem for p in series.queued(level=lv)]
    assert series.pick(style="comic")[0].stem == "hc_c001"
    assert series.counts()["mensajes"][_draft("hc_m001")["level"]] == 1
    with pytest.raises(ValueError):
        series.queued(style="tiktok")


def test_a_bad_script_in_the_queue_is_never_handed_out(queue):
    bad = _draft("hc_c001")
    bad.pop("quiz")
    (queue / "hc_c001.json").write_text(json.dumps(bad), encoding="utf-8")
    assert series.pick(style="comic") is None


def test_upload_metadata_is_title_caption_and_the_five_hashtags():
    d = _draft("hc_m001")
    meta = series.upload_metadata(d)
    assert meta == {"title": d["title"], "description": d["caption"], "hashtags": d["hashtags"]}
    assert len(meta["hashtags"]) == 5


def test_the_panel_offers_the_series_with_style_and_level_filters():
    from streamlit.testing.v1 import AppTest
    import os
    os.environ.setdefault("PYTHONPATH", str(ROOT / "src"))
    at = AppTest.from_file(str(ROOT / "src" / "admin.py"), default_timeout=120)
    at.session_state["current_page"] = "Generate"
    at.run()
    vt = next(x for x in at.selectbox if x.label == "Tipo de vídeo")
    assert series.PANEL_LABEL in vt.options
    vt.set_value(series.PANEL_LABEL).run()
    labels = [x.label for x in at.selectbox]
    assert "Estilo" in labels and "Nivel" in labels and not at.exception
    style = next(x for x in at.selectbox if x.label == "Estilo")
    assert style.options == ["Todos", *SERIES_STYLES]

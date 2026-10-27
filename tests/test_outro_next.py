"""STEP 80 §6: the outro names the next topic, shows the v3 wordmark and «Link en la bio», and
stays inside the safe areas. No TTS: the per-video outro reuses the variant's cached voice."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from video import outro as O  # noqa: E402
from video.series import series_kit as K  # noqa: E402


def test_the_next_phrase_follows_the_title_formula():
    hd = {"type": "how_do_you_say", "theme": "los animales del mar", "items": [{"emoji": "🐬"}]}
    assert O._next_phrase("how_do_you_say", hd) == "¿Cómo se dicen los ANIMALES DEL MAR? 🐬"
    assert O._next_phrase("how_do_you_say", {"theme": "el médico (consulta)"}) == "¿Cómo se dice el MÉDICO?"
    assert O._next_phrase("hecho_con_claude", {"title": "RETO: ¿cómo dices «tengo frío» en inglés?"}) \
        == "¿cómo dices «tengo frío» en inglés?"


def _queue(tmp_path, monkeypatch, scripts):
    import topic_history
    q = tmp_path / "q"
    (q / "_done").mkdir(parents=True)
    for name, s in scripts.items():
        (q / name).write_text(json.dumps(s), encoding="utf-8")
    monkeypatch.setattr(topic_history, "QUEUE_DIR", q)
    return q


def test_the_next_step_is_another_topic_of_the_same_type(tmp_path, monkeypatch):
    q = _queue(tmp_path, monkeypatch, {
        "a.json": {"type": "how_do_you_say", "theme": "la casa", "items": [{"emoji": "🏠"}]},
        "b.json": {"type": "quiz", "theme": "x"},
        "c.json": {"type": "how_do_you_say", "theme": "los insectos", "items": [{"emoji": "🐜"}]}})
    (q / "_done" / "d.json").write_text(json.dumps({"type": "how_do_you_say", "theme": "la ropa"}))
    line = O.next_step("how_do_you_say", {"type": "how_do_you_say", "theme": "la casa"})
    assert line == "Mañana: ¿Cómo se dicen los INSECTOS? 🐜"


def test_an_empty_queue_says_follow_us(tmp_path, monkeypatch):
    _queue(tmp_path, monkeypatch, {})
    assert O.next_step("how_do_you_say", {"theme": "la casa"}) == O.FOLLOW == "Síguenos para el siguiente"


def _ink_box(img, region):
    """The box of what is drawn (not sand) inside a region."""
    a = np.asarray(img.convert("RGB")).astype(int)
    x0, y0, x1, y1 = region
    sub = np.abs(a[y0:y1, x0:x1] - np.array(O._sand())).sum(axis=2) > 30
    ys, xs = np.nonzero(sub)
    return (x0 + xs.min(), y0 + ys.min(), x0 + xs.max(), y0 + ys.max()) if xs.size else None


@pytest.mark.parametrize("line", ["Mañana: ¿Cómo se dicen los ANIMALES DEL MAR? 🐬", None,
                                  "Mañana: ¿cómo dices «estoy embarazada» sin decir «embarrassed»?"])
def test_everything_is_inside_the_safe_areas(line):
    v = O.load_variants()["variants"][0]
    img = O.outro_still(v, line)
    box = _ink_box(img, (0, 0, O.VIDEO_WIDTH, O.VIDEO_HEIGHT))
    assert box[1] >= K.SAFE_TOP and box[3] <= K.SAFE_BOTTOM
    # below the rail's top, nothing (the card's shadow included) reaches past x 940
    low = _ink_box(img, (K.RAIL_X + 1, K.RAIL_Y, O.VIDEO_WIDTH, K.SAFE_BOTTOM))
    assert low is None
    # the next step ends above Bubi's head
    top = _ink_box(img, (0, O.NEXT_TOP - 10, O.VIDEO_WIDTH, 530))
    assert top is not None


def test_the_outro_keeps_its_length():
    assert O.OUTRO_DURATION == 4.0


def test_a_per_video_outro_reuses_the_cached_voice(tmp_path, monkeypatch):
    import tts_elevenlabs
    monkeypatch.setattr(tts_elevenlabs, "generate_segment_audio",
                        lambda **k: pytest.fail("the outro voiced something"))
    v = O.load_variants()["variants"][0]
    if not O.outro_path(v["id"]).exists():
        pytest.skip("no cached outro clip on this machine")
    own = O.outro_for(v, "Mañana: ¿Cómo se dice la CASA? 🏠", tmp_path / "own.mp4")
    assert O._probe_params(str(own)) == O._probe_params(str(O.outro_path(v["id"])))


def test_finalize_and_the_series_pass_the_next_step():
    pipeline = (ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")
    render = (ROOT / "src" / "video" / "series" / "render.py").read_text(encoding="utf-8")
    assert "next_line=next_line" in pipeline and '"outro_next": next_line' in pipeline
    assert 'O.next_step("hecho_con_claude", script)' in render

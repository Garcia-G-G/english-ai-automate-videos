"""«Inicio» (Garcia, 27 Oct: «velocity without losing quality»): four numbers first, the next video
in words with one button, the queues in plain Spanish, and every click cheap."""
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def inicio():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "src" / "admin.py"), default_timeout=300)
    at.session_state["current_page"] = "Dashboard"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_four_numbers_come_first(inicio):
    labels = [m.label for m in inicio.metric]
    assert labels[:3] == ["Por revisar", "Por subir", "Vídeos publicados · 7 días"]
    assert labels[3].startswith("OpenRouter este mes · tope \\$")              # markdown: shows «$»
    assert inicio.metric[3].value.startswith("$")


def test_the_page_speaks_plain_spanish(inicio):
    text = " ".join(str(getattr(e, "value", "")) for e in [*inicio.markdown, *inicio.caption])
    for jargon in ("output/pending", "output/approved", "output/video", "ledger.jsonl", "generation_jobs.json",
                   "DESACUERDO", "Selecting...", "Initializing...", "queued (job"):
        assert jargon not in text, jargon


def test_the_next_video_is_named_in_words_with_one_button(inicio):
    buttons = [b.label for b in inicio.button]
    captions = [c.value for c in inicio.caption]
    if "SIGUIENTE VÍDEO" in captions:
        assert "▶ Producir ahora" in buttons
        why = next(c for c in captions if c.startswith("Por qué este: "))
        assert not why[len("Por qué este: "):].split(" ")[0].endswith(":")      # no «how_do_you_say:» key
    else:
        assert any("La cola está vacía" in m.value for m in inicio.markdown)


def test_a_click_on_inicio_stays_cheap(inicio):
    t0 = time.perf_counter()
    inicio.run()
    assert time.perf_counter() - t0 < 1.5                  # measured 0.4-0.5 s warm on Garcia's Mac


def test_the_queue_ranking_is_cached_until_a_file_changes(tmp_path):
    import queue_priority as Q
    a = tmp_path / "a.json"
    a.write_text(json.dumps({"type": "how_do_you_say", "theme": "la casa"}))
    first = Q.ranked([a])
    assert Q.ranked([a]) == first and len(Q._RANKED) == 1
    a.write_text(json.dumps({"type": "quiz", "theme": "la casa", "x": 1}))   # size changes: a new key
    assert Q.ranked([a])[0][2].startswith("quiz")


def test_the_month_spend_rereads_a_cost_file_once_it_changes(tmp_path):
    import tts_openrouter as T
    f = tmp_path / "c.jsonl"
    f.write_text(json.dumps({"api_type": "openrouter_tts", "cost_usd": 0.01}) + "\n")
    assert T._file_spend(f) == pytest.approx(0.01)
    with f.open("a") as h:
        h.write(json.dumps({"api_type": "openrouter_image", "cost_usd": 0.02}) + "\n")
    assert T._file_spend(f) == pytest.approx(0.03)

"""STEP 76 §1: English is marked with [[ ]], not guessed."""
import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tts_segmenter import segment_script, segment_text, strip_markers  # noqa: E402

WEDNESDAY = ROOT / "output" / "audio" / "pronunciation" / "wednesday_20261008_130901.json"


def _english(segments):
    return [s["text"] for s in segments if s["lang"] == "en"]


@pytest.mark.parametrize("text", ["Hoy: I have a [[meeting on Wednesday]]. Y ya.",
                                  "Hoy: [[I have a meeting on Wednesday]]. Y ya."])
def test_a_marked_sentence_is_one_english_segment(text):
    assert _english(segment_text(text, [])) == ["I have a meeting on Wednesday."]


@pytest.mark.skipif(not WEDNESDAY.exists(), reason="the Wednesday artifact is not on this machine")
def test_the_wednesday_script_no_longer_splits_i_have_a_from_meeting():
    segs = segment_script(json.loads(WEDNESDAY.read_text(encoding="utf-8")))
    assert "I have a meeting on Wednesday." in _english(segs)
    assert not any(s["text"].endswith("I have a") for s in segs)


def test_with_markers_the_markers_are_the_english_and_metadata_does_not_guess(caplog):
    script = {"full_script": "[warm] La palabra outfit no es [[embarrassed]]. [excited] ¿Ves?",
              "english_phrases": ["outfit", "embarrassed"]}
    with caplog.at_level(logging.INFO, logger="tts_segmenter"):
        segs = segment_script(script)
    assert _english(segs) == ["embarrassed."]
    assert "heuristic" not in caplog.text
    assert all("[" not in s["text"] for s in segs)


def test_without_markers_the_heuristic_runs_and_says_so(caplog):
    with caplog.at_level(logging.INFO, logger="tts_segmenter"):
        segs = segment_script({"full_script": "La palabra 'embarrassed' no es embarazada.",
                               "english_phrases": ["embarrassed"]})
    assert _english(segs) == ["embarrassed"]
    assert "no [[ ]] markers" in caplog.text


def test_strip_markers_cleans_around_them_and_keeps_the_spans():
    from tts_common import clean_for_tts
    text, marked = strip_markers("[warm] Tengo una [[meeting]], [excited] hoy.", clean_for_tts)
    assert text == "Tengo una meeting, hoy."
    assert [text[s:e] for s, e in marked] == ["meeting"]


def test_display_and_plain_voice_unwrap_markers():
    from audio_tags import strip_tags
    from tts_common import clean_for_tts
    assert strip_tags("[warm] Tengo una [[meeting]] hoy.") == "Tengo una meeting hoy."
    assert "[" not in clean_for_tts("Tengo una [[meeting on Wednesday]] [excited] ya")


@pytest.mark.parametrize("bad", ["Hola [[meeting y nada más aquí", "Hola meeting]] y nada más",
                                 "Hola [[a [[b]] c]] fin del texto", "Hola [[  ]] fin del texto"])
def test_the_schema_refuses_unbalanced_nested_or_empty_markers(bad):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _validate(bad)


def _validate(text):
    from script_schema import ScriptBase
    return ScriptBase.model_validate({"type": "educational", "full_script": text})


def test_the_schema_accepts_balanced_markers():
    assert _validate("Hola [[meeting]] y [[I have a car]].").full_script.count("[[") == 2


def test_the_gate_rejects_english_outside_markers():
    import qa_gate
    data = {"full_script": "Una meeting no es [[embarrassed]].", "english_phrases": ["meeting", "embarrassed"]}
    check = qa_gate.english_markers(data)
    assert check["available"] and check["outside"] == ["meeting"]
    report = {"checks": {"drift_table": {}, "sentence_timeline": {}, "letter_to_word": {},
                         "levels": {"clipping": {"verdict": "ok"}, "dead_air": {"verdict": "ok"}},
                         "english_markers": check},
              "covered_by": ["drift_table"], "video_type": "educational", "has_segment_times": True, "n_words": 3}
    flags = qa_gate._collect_flags(report)
    assert "english_outside_markers:meeting" in flags
    assert qa_gate.verdict({"flags": flags})["verdict"] == "REJECT"
    assert not qa_gate.english_markers({"full_script": "Sin marcas 'outfit'."})["available"]


def test_prompts_ask_for_markers_and_the_scrape_reads_them():
    import script_generator as G
    for build, category in ((G.build_prompt_educational, "common_mistakes"),
                            (G.build_prompt_pronunciation, "pronunciation")):
        assert "[[" in build(category, G.load_topics(category)[0])
    script = G.validate_and_clean_script(
        {"type": "educational", "full_script": "Ojo con [[I am embarrassed]] hoy, de verdad.",
         "english_phrases": ["embarrassed"], "hook": "x"}, "educational")
    assert "i am embarrassed" in [p.lower() for p in script["english_phrases"]]

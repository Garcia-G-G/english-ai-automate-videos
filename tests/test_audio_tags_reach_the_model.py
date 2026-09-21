#!/usr/bin/env python3
"""An emotion tag must reach the model that understands it.

    python3 -m pytest tests/test_audio_tags_reach_the_model.py

THE DEFECT. `clean_for_tts` removed every bracketed run, which meant it
removed every eleven_v3 audio tag on its way to the API. Dry run on a real
pronunciation script: four tags written, ZERO sent. Across September's
sidecars, 0 of 344 spoken segments carried one. The ~550 tags written into
the queue this month never reached ElevenLabs — the owner asked repeatedly
for narration with personality and got a cleaning function that removed it.

THE GATE IS THE MODEL, NOT THE TYPE. A tag sent to a model that does not
know it is SPOKEN ALOUD, so the safe direction is to strip, and the opt-in
belongs wherever the model is known. MODEL_ID is env-overridable, which is
why a type-based gate would not have held.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# MODULE SCOPE HOLDS ONLY NAMES THAT PREDATE THIS CHANGE. honours_tags and
# keep_known_tags are imported inside the tests that use them, so that on a
# tree without them this file FAILS rather than failing to COLLECT — a
# collection error aborts the whole run, which is what da82ac6 removed.
from audio_tags import unknown_tags  # noqa: E402
from tts_common import clean_for_tts  # noqa: E402


# ── the gate ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("model,honoured", [
    ("eleven_v3", True),
    ("ELEVEN_V3", True),
    ("eleven_turbo_v2_5", False),   # needs language_code, so it is not v3
    ("eleven_flash_v2_5", False),
    ("tts-1-hd", False),            # openai
    ("", False),
    (None, False),
])
def test_only_a_tag_aware_model_is_offered_tags(model, honoured):
    from audio_tags import honours_tags
    assert honours_tags(model) is honoured


def test_an_unknown_model_falls_back_to_stripping():
    """The safe direction. A tag that survives to a model which cannot read
    it is spoken out loud in the middle of a lesson; a tag that is stripped
    is only a missed opportunity."""
    from audio_tags import honours_tags
    assert honours_tags("some-model-shipped-next-year") is False


# ── what survives, and what must not ─────────────────────────────────

def test_a_known_tag_survives_for_a_model_that_reads_it():
    from audio_tags import keep_known_tags
    assert keep_known_tags("[excited] ¡Correcto!") == "[excited] ¡Correcto!"


def test_a_placeholder_that_merely_looks_like_a_tag_is_removed():
    """The corpus carries 9 of these — "[name]", "[company]",
    "[department name]". v3 does not know them, so it falls back to SPEAKING
    them, which is worse than dropping them."""
    from audio_tags import keep_known_tags
    assert keep_known_tags("Hola [name], ¿que tal?") == "Hola , ¿que tal?"
    assert keep_known_tags("[emocionado] hola") == "hola"
    assert "[" not in keep_known_tags("ver [1] la nota")


def test_every_tag_the_corpus_uses_is_one_the_model_knows():
    """An unknown tag is a write-time defect: the model reads it as text."""
    offenders = []
    for path in sorted((ROOT / "content").rglob("*.json")):
        try:
            blob = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for tag in unknown_tags(blob):
            name = tag[1:-1].strip().lower()
            # placeholders are a separate, known problem; they are stripped
            if name not in ("name", "company", "department name"):
                offenders.append(f"{path.name}: {tag}")
    assert not offenders, "tags the model will speak aloud:\n  " + "\n  ".join(offenders)


# ── the cleaning function's two callers ──────────────────────────────

def test_clean_for_tts_strips_by_default():
    """Any call site nobody updated keeps today's safe behaviour."""
    assert clean_for_tts("[excited] ¡Correcto!") == "¡Correcto!"


def test_clean_for_tts_keeps_tags_when_asked():
    assert clean_for_tts("[excited] ¡Correcto!", keep_tags=True) == "[excited] ¡Correcto!"


def test_a_tag_and_a_blank_survive_together():
    """§2 and §3 in one string, which is what the queue actually contains."""
    assert (clean_for_tts("[curious] Sarah will ___ it.", keep_tags=True)
            == "[curious] Sarah will ... it.")


# ── end to end: what the API is actually handed ──────────────────────

@pytest.fixture
def beep(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is needed to assemble the segments")
    path = tmp_path / "beep.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=0.4", "-ac", "2", str(path)],
                   capture_output=True, check=True)
    return path


def test_a_real_quiz_hands_its_tags_to_the_api(tmp_path, monkeypatch, beep):
    """THE PIN FOR THE WHOLE THING. Not "the regex keeps brackets" — the
    text ElevenLabs is handed, for a script off the queue, items 2 and 3
    included."""
    import tts_elevenlabs as el

    # Gated on MODEL_ID, which exists in every version of this module — NOT
    # on the _KEEP_TAGS flag this change introduces. Keying the skip to the
    # new flag would make this test quietly SKIP on a tree where the feature
    # was removed, and a pin that skips when the defect returns is not a pin.
    if "v3" not in (el.MODEL_ID or "").lower():
        pytest.skip(f"MODEL_ID={el.MODEL_ID} does not honour tags")

    # three items only because the switch is opened here; see
    # tests/test_items_spoken_switch.py for the switch itself
    import duration_spec
    _real_spec = duration_spec.type_spec
    monkeypatch.setattr(duration_spec, "type_spec",
                        lambda vt: {**(_real_spec(vt) or {}), "items_spoken": 3})

    sent = []

    def fake_segment(text=None, output_path=None, voice_id=None, **kwargs):
        sent.append(text)
        shutil.copy(beep, output_path)
        return output_path

    monkeypatch.setattr(el, "generate_segment_audio", fake_segment)

    script = json.loads(
        (ROOT / "content" / "queue" / "quiz"
         / "gr004_first_conditional.json").read_text(encoding="utf-8"))

    el.generate_quiz_audio_segmented(script, str(tmp_path / "q.mp3"))

    tagged = [s for s in sent if "[" in (s or "")]
    assert tagged, "not one tag reached the API — this is the original defect"

    # THE SCRIPT'S OWN QUESTIONS, identified by their words rather than by
    # their tag. Counting "[curious]" was a proxy that broke the moment the
    # narrator's own pooled lines (narration_phrases) started carrying tags
    # of their own -- the proxy counted those too.
    items = [script] + list((script.get("questions") or [])[1:])
    assert len(items) == 3, "fixture changed: expected a three-item script"

    for item in items:
        stem = item["question"].split("___")[0].split("]", 1)[-1].strip()
        spoken = [s for s in sent if stem and stem in s]
        assert spoken, f"this question never reached the API: {item['question']!r}"
        for line in spoken:
            assert line.startswith("["), f"question lost its tag: {line!r}"
            # and the blank in it is a pause, not a hole
            assert "..." in line and "___" not in line

    # every tag handed over is one the model knows
    for spoken in tagged:
        assert not unknown_tags(spoken), f"model will speak this aloud: {spoken}"


def test_the_turbo_path_still_strips_because_turbo_would_speak_them():
    """educational and pronunciation run on eleven_turbo_v2_5 — it needs the
    `language_code` v3 does not accept. Turbo does not interpret tags, so
    they go. A known gap, not an oversight: emotion for those two needs
    voice_settings.style or the wording itself."""
    from tts_segmenter import segment_script

    segments = segment_script(
        {"full_script": "[excited] Hola. Today we learn something.",
         "english_phrases": ["Today we learn something"]})

    spoken = " ".join(s["text"] for s in segments)
    assert "[excited]" not in spoken
    assert "excited" not in spoken.lower()
    assert "Hola" in spoken

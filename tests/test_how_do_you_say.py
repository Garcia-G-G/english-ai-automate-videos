#!/usr/bin/env python3
"""how_do_you_say ("¿Cómo se dice…?"), new type #1 — every door it needs.

    python3 -m pytest tests/test_how_do_you_say.py

What a type is, after the registry: a renderer, an audio generator, one
registry entry, and the schema / length / duration / category / metadata
doors that read from it. Each has a test here, so the type cannot be legal
in one place and missing from the next — the defect the registry exists for.

NOTHING HERE CALLS A PAID API. The audio generator is exercised end to end
with generate_segment_audio replaced by ffmpeg tones, so segment_times, the
think silence and the measured reveal_end are checked on real audio files.
"""

import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

QUEUED = sorted((ROOT / "content" / "queue" / "how_do_you_say").glob("*.json"))
DRAFTS = sorted((ROOT / "content" / "drafts" / "how_do_you_say").glob("*.json"))
SCRIPTS = QUEUED or DRAFTS


def _script(name="bv001_familia"):
    for p in SCRIPTS:
        if p.stem == name:
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(name)


def _timeline(data):
    """A synthetic but well-formed segment_times, shaped like the generator's."""
    st = {"intro": {"start": 0.0, "end": 4.0}}
    t = 4.6
    for i in range(1, len(data["items"]) + 1):
        st[f"es_{i}"] = {"start": t, "end": t + 0.8}; t += 0.8
        st[f"think_{i}"] = {"start": t, "end": t + 1.8}; t += 1.8
        st[f"en_{i}"] = {"start": t, "end": t + 1.6, "reveal_end": t + 0.7}; t += 2.0
    st["recap"] = {"start": t, "end": t + 9.0}; t += 9.6
    st["outro"] = {"start": t, "end": t + 4.0}
    data = copy.deepcopy(data)
    data["segment_times"] = st
    return data, t + 4.0


# ── emoji: the font's own cmap decides ───────────────────────────────

def test_emoji_in_the_font_passes_and_vs16_is_allowed():
    from emoji_font import emoji_problem
    assert emoji_problem("👪") is None
    assert emoji_problem("❤️") is None          # U+2764 + U+FE0F


def test_zwj_sequences_are_refused():
    """They render as two or three emoji wherever the font lacks the sequence."""
    from emoji_font import emoji_problem
    assert "ZWJ" in emoji_problem("👨‍👩‍👧")


def test_a_code_point_the_font_lacks_is_refused():
    from emoji_font import emoji_problem
    assert "not in" in emoji_problem("A")
    assert "code points" in emoji_problem("👪👪")


def test_the_licence_is_vendored_beside_the_font():
    assert (ROOT / "assets" / "fonts" / "NotoColorEmoji.ttf").exists()
    licence = (ROOT / "assets" / "fonts" / "OFL-NotoColorEmoji.txt").read_text()
    assert "SIL Open Font License" in licence


# ── schema ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.stem)
def test_the_three_scripts_validate(path):
    from script_schema import validate_script
    validate_script(json.loads(path.read_text(encoding="utf-8")),
                    video_type="how_do_you_say")


@pytest.mark.parametrize("n", [7, 11])
def test_item_count_is_eight_to_ten(n):
    from script_schema import check_script
    data = _script()
    items = data["items"]
    data["items"] = (items * 2)[:n]
    _model, errors, _ = check_script(data)
    assert any("items" in e for e in errors), errors


def test_tags_only_in_intro_recap_outro_and_only_known_ones():
    from script_schema import check_script
    data = _script()
    data["items"][1]["english"] = "[excited] mother"
    assert check_script(data)[1]

    data = _script()
    data["outro"] = "[emocionado] ¿Cuántas sabías?"
    errors = check_script(data)[1]
    assert any("unknown audio tag" in e for e in errors), errors


def test_drafts_were_moved_not_copied():
    """The brief: move them into the queue once the schema accepts them, and
    drop the draft flag."""
    assert {"bv001_familia", "bv002_casa", "bv003_comida"} <= {p.stem for p in QUEUED}
    assert not DRAFTS, "a script left in drafts/ too is two copies of one topic"
    for p in QUEUED:
        assert "draft" not in json.loads(p.read_text(encoding="utf-8"))["_meta"]


# ── length: measured in the renderer's own face and column ───────────

def test_every_queued_word_fits_its_column():
    import length_spec
    for p in SCRIPTS:
        assert length_spec.check_script(json.loads(p.read_text(encoding="utf-8"))) == []


def test_an_overlong_word_is_caught_with_the_renderers_fit():
    import length_spec
    from video.how_do_you_say import ENGLISH_W, fit_word
    data = _script()
    data["items"][0]["english"] = "internationalization"
    bad = length_spec.check_script(data)
    assert [v["where"] for v in bad] == ["items[0]"]
    assert bad[0]["width"] == fit_word("internationalization", ENGLISH_W)[2]


# ── registry and layout ──────────────────────────────────────────────

def _page_rows():
    from PIL import Image
    from video import how_do_you_say as h
    key = tuple(("Madre", "👩") for _ in range(10))
    layer = h._static_page(key, "la familia").rotate(h.TILT_DEG, resample=Image.BICUBIC)
    alpha = np.asarray(layer)[:, :, 3]
    rows = np.where((alpha > 8).any(axis=1))[0]
    return int(rows.min()) + h.PAGE_Y - h.PAD, int(rows.max()) + h.PAGE_Y - h.PAD


def test_the_registry_band_is_the_measured_page():
    import video_types
    assert video_types.TYPES["how_do_you_say"]["text_band"] == _page_rows()


def test_the_page_ends_above_the_watermark_and_its_scrim():
    import clip_contrast
    from video.brand import watermark_top
    assert _page_rows()[1] < clip_contrast.mark_rect()[1] < watermark_top()


def test_registry_entry():
    import video_types as vt
    e = vt.TYPES["how_do_you_say"]
    assert e["timing"] == "v3" and e["dashboard"] == "Cómo se dice"
    assert vt.audio_generator_name("how_do_you_say") == "generate_how_do_you_say_audio_segmented"
    import tts_elevenlabs
    assert callable(getattr(tts_elevenlabs, vt.audio_generator_name("how_do_you_say")))


# ── renderer ─────────────────────────────────────────────────────────

@pytest.fixture
def no_mascot():
    import video.character as character
    character._renderer, character._renderer_resolved = None, True


def test_frames_are_a_pure_function_of_t(no_mascot):
    from video.how_do_you_say import create_frame_how_do_you_say
    data, dur = _timeline(_script())
    t = data["segment_times"]["en_5"]["start"] + 0.3
    a = create_frame_how_do_you_say(t, copy.deepcopy(data), dur)
    create_frame_how_do_you_say(2.0, data, dur)          # another t in between
    b = create_frame_how_do_you_say(t, data, dur)
    assert a.shape == (1920, 1080, 3) and np.array_equal(a, b)


def test_no_segment_times_is_a_refusal_not_a_guess(no_mascot):
    from video.how_do_you_say import create_frame_how_do_you_say
    with pytest.raises(KeyError, match="segment_times"):
        create_frame_how_do_you_say(1.0, _script(), 60.0)


def test_reveal_runs_over_the_first_take_only():
    from video.how_do_you_say import Timeline
    data, dur = _timeline(_script())
    tl = Timeline(data, dur)
    en = data["segment_times"]["en_5"]
    assert tl.reveal(4, en["start"]) == 0.0
    mid = (en["start"] + en["reveal_end"]) / 2
    assert tl.reveal(4, mid) == pytest.approx(0.5)
    assert tl.reveal(4, en["reveal_end"]) == 1.0


def test_pencil_reaches_the_row_and_follows_the_mask():
    from video.how_do_you_say import (ENGLISH_X, ENGLISH_W, Timeline, fit_word,
                                      pencil_position, row_centres)
    data, dur = _timeline(_script())
    tl = Timeline(data, dur)
    centres = row_centres(len(data["items"]))
    st = data["segment_times"]
    x, _ = pencil_position(st["think_5"]["start"], tl, data["items"], centres)
    assert x == pytest.approx(ENGLISH_X)
    w = fit_word(data["items"][4]["english"], ENGLISH_W)[2]
    x, _ = pencil_position(st["en_5"]["reveal_end"], tl, data["items"], centres)
    assert x == pytest.approx(ENGLISH_X + w)


def test_the_pencil_body_trails_below_its_tip():
    """Rows fill top to bottom, so ink below the tip lies over rows not yet
    written. The first render had the body up-right, over the previous
    row's English word ("grandmother" at item 8)."""
    from video.how_do_you_say import pencil_image
    img, (cx, cy) = pencil_image()
    alpha = np.asarray(img)[:, :, 3]
    ys, xs = np.where(alpha > 8)
    assert ys.min() >= cy - 6, "ink above the tip covers a written row"
    assert xs.min() >= cx - 6, "ink left of the tip covers the word being written"


def test_recap_word_times_are_in_order_and_inside_the_recap():
    from video.how_do_you_say import _recap_word_times
    data = _script()
    times = _recap_word_times(data["recap"], data["items"], (50.0, 59.0))
    assert None not in times
    assert times == sorted(times) and 50.0 < times[0] and times[-1] < 59.0


# ── audio generator, offline ─────────────────────────────────────────

def _tone(path, spans, total):
    """An mp3 with a 440 Hz tone over each (start, end) and silence between."""
    expr = "+".join(f"between(t,{a},{b})" for a, b in spans)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='0.4*sin(2*PI*440*t)*({expr})':s=44100:d={total}",
                    "-ac", "1", "-q:a", "2", path], check=True)


def test_generator_declares_every_segment_and_measures_the_first_take(tmp_path, monkeypatch):
    import tts_elevenlabs as TE

    calls = []

    def fake(text, output_path, **kw):
        calls.append(text)
        if text.count(".") >= 2 and "?" not in text and len(text) < 40:
            _tone(output_path, [(0.05, 0.55), (0.95, 1.45)], 1.6)   # "Family. Family."
        else:
            _tone(output_path, [(0.05, 0.75)], 0.9)
        return 0.0

    monkeypatch.setattr(TE, "generate_segment_audio", fake)
    monkeypatch.setattr(TE, "DEFAULT_VOICE_ID", "test-voice")
    script = _script()
    out = TE.generate_how_do_you_say_audio_segmented(script, str(tmp_path / "a.mp3"))

    n = len(script["items"])
    assert len(calls) == 2 * n + 3, "intro + es/en per item + recap + outro"
    st = out["segment_times"]
    order = ["intro"] + [f"{k}_{i}" for i in range(1, n + 1)
                         for k in ("es", "think", "en")] + ["recap", "outro"]
    assert [s["id"] for s in out["segments"]] == order
    for i in range(1, n + 1):
        think = st[f"think_{i}"]
        assert think["duration"] == pytest.approx(TE.HDYS_THINK_S, abs=0.002)
        assert st[f"es_{i}"]["end"] <= think["start"] <= st[f"en_{i}"]["start"]
        en = st[f"en_{i}"]
        # the first tone ends ~0.5 s into the (trimmed) clip
        assert en["start"] < en["reveal_end"] < en["end"]
        assert en["reveal_end"] - en["start"] == pytest.approx(0.5, abs=0.12)
    assert all(s["text"] == "[silence]" for s in out["segments"] if s["id"].startswith("think_"))


# ── the gates that read the type ─────────────────────────────────────

def test_qa_gate_reads_think_as_declared_silence():
    import qa_gate
    data = {"segment_times": {"think_1": {"start": 1, "end": 2.8},
                              "countdown_3": {"start": 3, "end": 4},
                              "i2_countdown_2": {"start": 5, "end": 6},
                              "es_1": {"start": 0, "end": 1}},
            "segments": [{"id": "think_1", "text": "[silence]"},
                         {"id": "countdown_3", "text": "[3]"},
                         {"id": "i2_countdown_2", "text": "Dos."},
                         {"id": "es_1", "text": "Familia."}]}
    assert qa_gate._silent_segment_ids(data) == {"think_1", "countdown_3"}


def test_duration_uses_the_global_band_until_calibrated():
    import duration_spec as ds
    v = ds.check("how_do_you_say", 63.0)
    assert v["status"] == ds.PASS and v["calibrated"] is False
    assert v["band"] == [ds.band()["min_seconds"], ds.band()["max_seconds"]]
    assert ds.check("how_do_you_say", 90.0)["status"] == ds.OUT_OF_BAND
    assert ds.check("banana", 60.0)["status"] == ds.UNKNOWN
    assert "calibrated" not in ds.check("quiz", 60.0), "existing records unchanged"


def test_basic_vocab_feeds_this_type_only():
    import type_categories as tc
    tc.reload()
    assert tc.allowed_for("how_do_you_say") == ["basic_vocab"]
    import video_types
    for other in video_types.VIDEO_TYPES:
        if other != "how_do_you_say":
            assert "basic_vocab" not in tc.allowed_for(other)
    topics = json.loads((ROOT / "content/topics/basic_vocab.json").read_text())
    ids = [t["id"] for t in topics]
    # Contiguous from bv001; the set grows (bv021-bv060 added 2026-10-15).
    assert len(ids) >= 20
    assert ids == [f"bv{i:03d}" for i in range(1, len(ids) + 1)]


def test_metadata_title_template():
    from metadata_generator import generate_metadata
    data = _script()
    data.pop("video_title")
    meta = generate_metadata(data, "how_do_you_say", "basic_vocab")
    assert meta["title"] == f"¿Cómo se dice FAMILIA en inglés? {data['items'][0]['emoji']}"
    assert meta["hashtags"][:5] == ["#InglésParaPrincipiantes", "#VocabularioEnInglés",
                                    "#AprenderInglés", "#InglésFácil", "#HowDoYouSay"]


def test_spoken_words_count_english_twice_and_no_emoji():
    from duration_calibrate import spoken_words
    data = _script()
    items = sum(len(i["spanish"].split()) + 2 * len(i["english"].split())
                for i in data["items"])
    from audio_tags import strip_tags
    fixed = sum(len(strip_tags(data[k]).split()) for k in ("intro", "recap", "outro"))
    assert spoken_words(data) == items + fixed


def test_openai_refuses_instead_of_narrating_full_script(tmp_path):
    from tts_providers.openai_provider import OpenAITTSProvider
    with pytest.raises(NotImplementedError, match="ElevenLabs"):
        OpenAITTSProvider().generate_from_script(_script(), str(tmp_path / "a.mp3"))


def test_the_generator_prompt_names_only_known_tags():
    import re
    from audio_tags import TAGS
    from script_generator import build_prompt, load_topics
    prompt = build_prompt("basic_vocab", load_topics("basic_vocab")[0], "how_do_you_say")
    for tag in re.findall(r"\[([a-z ]+)\]", prompt):
        assert tag in TAGS, tag

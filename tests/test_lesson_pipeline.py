#!/usr/bin/env python3
"""The lesson pipeline's contracts, without Manim, without ElevenLabs, without OpenAI.

Three classes of bug, each with the test that makes it impossible to ship:
  1. Bilingual reading — an English span must become its own segment with lang=en, and
     the stitched word timings must be shifted by the real audio offsets. Otherwise the
     voice reads "have" as Spanish and the highlight lands on the wrong second.
  2. Cues — a beat animates on words; if the narration never says one, the writer must
     hear it before audio is paid for (validate/warnings), and the bookmark must be
     inserted before the first mention only.
  3. The shipped lessons — every lessons/*.json in the repo must validate, so a broken
     script never reaches the admin's picker as "ready".
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

STUDIO = Path(__file__).resolve().parent.parent / "experiments" / "manim_voiceover_poc"
sys.path.insert(0, str(STUDIO))

# TWO THINGS CAN BE ABSENT, and an unguarded ImportError in either is a
# COLLECTION error -- pytest aborts the entire run and the other ~1600 tests
# report nothing at all. A suite that collects zero tests is worse than a red
# one, because nothing looks red.
#
#   the studio TREE   experiments/manim_voiceover_poc/*.py. Every test here
#                     exercises it, so its absence skips the module -- there
#                     is nothing left to assert.
pytest.importorskip("lesson", reason=f"the Manim studio tree is not at {STUDIO}")

import lesson as L  # noqa: E402
import gen_audio as GA  # noqa: E402
import gen_script as GS  # noqa: E402

#   Manim's STACK    voices.py is the only module here that imports it, and
#                     it lives in the studio's own .venv (3.12) rather than
#                     the interpreter the suite runs on.
#
# The second one is NOT an importorskip, which would skip this whole module.
# Exactly one test below calls into V; the other nineteen are stdlib-only
# contracts -- segment splitting, cue validation, the shipped lessons -- that
# must keep running on a machine that has never installed Manim. Nineteen
# tests is too much to pay to protect one.
try:
    import voices as V  # noqa: E402
except ModuleNotFoundError:                    # pragma: no cover
    V = None

needs_manim_voiceover = pytest.mark.skipif(
    V is None, reason="voices.py needs Manim's stack, which lives in the "
                      "studio venv rather than the suite's interpreter")


# ── 1. bilingual segments and stitching ────────────────────────────────────────

def test_segments_split_english_spans_with_their_language():
    segs = L.segments("Mira esta frase: [[He have coffee]]. En español: él toma café. Cambia a [[has]].")
    assert segs == [
        {"text": "Mira esta frase:", "lang": "es"},
        {"text": "He have coffee", "lang": "en"},
        {"text": ". En español: él toma café. Cambia a", "lang": "es"},
        {"text": "has.", "lang": "en"},                 # a lone «.» is never its own request
    ]
    assert L.spoken_text("Mira: [[He  has\ncoffee]].") == "Mira: He has coffee."


def test_language_code_only_for_models_that_accept_it():
    assert "eleven_turbo_v2_5" in GA.SEGMENT_MODELS and "eleven_multilingual_v2" not in GA.SEGMENT_MODELS
    assert GA.ONE_REQUEST_MODEL == "eleven_v4" and "eleven_v4" in GA.LANGUAGE_CODE_MODELS      # owner's ear, STEP 55
    assert "eleven_multilingual_v2" not in GA.LANGUAGE_CODE_MODELS                            # it refuses language_code


def test_shift_words_adds_each_segment_offset():
    pieces = [{"words": [{"word": "Mira", "start": 0.0, "end": 0.3}], "offset": 0.0},
              {"words": [{"word": "He", "start": 0.1, "end": 0.2}, {"word": "has", "start": 0.3, "end": 0.5}], "offset": 1.5}]
    assert GA.shift_words(pieces) == [{"word": "Mira", "start": 0.0, "end": 0.3},
                                      {"word": "He", "start": 1.6, "end": 1.7}, {"word": "has", "start": 1.8, "end": 2.0}]


def test_gap_after_follows_punctuation():
    assert GA.gap_after("Hola.") == GA.GAP_AFTER["."] and GA.gap_after("hola") == GA.DEFAULT_GAP


def ffmpeg_available():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_stitch_offsets_match_real_durations_and_gaps(tmp_path):
    parts = []
    for n, secs in enumerate((0.5, 0.25)):
        p = tmp_path / f"s{n}.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                        "-t", str(secs), "-codec:a", "libmp3lame", "-b:a", "128k", str(p)], check=True)
        parts.append(p)
    target = tmp_path / "beat.mp3"
    offsets, lead_cuts = GA.stitch(parts, ["Hola.", "has"], target)
    assert offsets[0] == 0.0 and lead_cuts == [pytest.approx(0.0, abs=0.06)] * 2   # a pure tone has no silence to trim
    assert offsets[1] == pytest.approx(0.5 + GA.GAP_AFTER["."], abs=0.08)
    assert GA.probe_duration(target) == pytest.approx(0.75 + GA.GAP_AFTER["."], abs=0.12)


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_prepare_segment_trims_edge_silence_to_the_pad_and_reports_the_lead_cut(tmp_path):
    src = tmp_path / "seg.mp3"        # 0.30 s silence + 0.50 s tone + 0.30 s silence
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "aevalsrc=if(between(t\\,0.3\\,0.8)\\,0.5*sin(440*2*PI*t)\\,0):s=44100:d=1.1",
                    "-codec:a", "libmp3lame", "-b:a", "128k", str(src)], check=True)
    lead_cut, duration = GA.prepare_segment(src, tmp_path / "seg.wav")
    assert lead_cut == pytest.approx(0.30 - GA.EDGE_PAD, abs=0.05)
    assert duration == pytest.approx(0.50 + 2 * GA.EDGE_PAD, abs=0.08)


def test_shift_words_subtracts_the_trimmed_lead_before_adding_the_offset():
    pieces = [{"words": [{"word": "He", "start": 0.30, "end": 0.45}], "offset": 2.0, "lead_cut": 0.26}]
    assert GA.shift_words(pieces) == [{"word": "He", "start": 2.04, "end": 2.19}]
    clamped = GA.shift_words([{"words": [{"word": "x", "start": 0.1, "end": 0.2}], "offset": 1.0, "lead_cut": 0.5}])
    assert clamped == [{"word": "x", "start": 1.0, "end": 1.0}]


def test_alignment_to_words_folds_characters():
    al = {"characters": list("He has."), "character_start_times_seconds": [i * 0.1 for i in range(7)],
          "character_end_times_seconds": [i * 0.1 + 0.1 for i in range(7)]}
    assert [w["word"] for w in GA.alignment_to_words(al)] == ["He", "has."]


@needs_manim_voiceover
def test_word_boundaries_map_timed_words_onto_the_text_in_order():
    plain = "Cambia a has. He has coffee."
    words = [{"word": "Cambia", "start": 0.0}, {"word": "a", "start": 0.4}, {"word": "has.", "start": 0.5},
             {"word": "He", "start": 0.8}, {"word": "has", "start": 0.9}, {"word": "coffee.", "start": 1.1}]
    b = V.word_boundaries(plain, words)
    assert [x["text_offset"] for x in b] == [0, 7, 9, 14, 17, 21]
    assert b[4]["audio_offset"] == int(0.9 * V.AUDIO_OFFSET_RESOLUTION)


# ── 2. cues ────────────────────────────────────────────────────────────────────

def test_marked_narration_bookmarks_first_mention_only_and_reports_unsaid_words():
    beat = {"type": "sentence", "text": "He has coffee.", "highlight": {"He": "yellow", "has": "green"},
            "tags": {"coffee": "objeto"}, "narration": "El sujeto es [[He]]. Cambia a [[has]]. [[He has]]."}
    text, marks = L.marked_narration(beat)
    assert text == "El sujeto es <bookmark mark='c0'/>He. Cambia a <bookmark mark='c1'/>has. He has."
    assert marks == {"He": "c0", "has": "c1"}                      # "coffee" is never said → no mark
    assert L.cued(beat) == ["He", "has"]
    lesson = {"id": "x", "title": "x", "beats": [{"id": "b01", **beat}]}
    assert L.validate(lesson) == []
    assert L.warnings(lesson) == ["beat 1 (b01): «coffee» is animated but never said — its timing is a guess"]


def test_cue_words_strip_punctuation_and_arrows():
    beat = {"type": "list", "items": ["pero: play → plays", "work → works"], "narration": "Pero [[play]]: [[plays]]. Y [[work]]."}
    assert L.cue_words(beat) == ["pero", "work"]


def test_validate_catches_the_writer_mistakes_that_break_the_scene():
    lesson = {"id": "Bad Id", "title": "t", "beats": [
        {"id": "b01", "type": "sentence", "text": "one two three four five six seven eight nine ten eleven twelve thirteen",
         "narration": "x [[unbalanced"},
        {"id": "b01", "type": "quiz", "question": "q", "options": ["a"], "answer": 3, "narration": "y"},
        {"id": "b03", "type": "table", "rows": [["a", "b", "c", "d"]], "narration": "z"},
        {"id": "b04", "type": "mystery", "narration": "w"},
        {"id": "b05", "type": "tip", "text": "t", "narration": ""},
    ]}
    problems = "\n".join(L.validate(lesson))
    for expected in ("id must be a slug", "more than 12 words", "unbalanced", "duplicate id", "2–4 options",
                     "answer must index", "1–3 cells", "unknown type", "empty narration"):
        assert expected in problems, expected


# ── 3. the lessons we ship ─────────────────────────────────────────────────────

@pytest.mark.parametrize("path", sorted((STUDIO / "lessons").glob("*.json")), ids=lambda p: p.stem)
def test_shipped_lessons_are_renderable_and_long(path):
    lesson = L.load(path)
    assert L.validate(lesson) == []
    assert lesson["id"] == path.stem
    if lesson.get("demo"):          # a format demo (demo-motion): renderable, not a full lesson
        return
    assert len(lesson["beats"]) >= 25 and L.estimate_minutes(lesson) >= 5, "a lesson is a long video, not a clip"
    assert any(b["type"] == "dialogue" for b in lesson["beats"]) and sum(b["type"] == "quiz" for b in lesson["beats"]) >= 3
    english = [s for b in lesson["beats"] for s in L.segments(b["narration"]) if s.get("lang") == "en"]
    assert len(english) >= 40, "the narration must carry the English inside [[ ]]"


# ── gen_script plumbing (no network) ───────────────────────────────────────────

def test_gen_script_normalizes_ids_and_slug_and_prices():
    raw = {"title": "¿I work o I'm working?", "beats": [{"type": "title", "narration": "hola"}, {"type": "tip", "text": "x", "narration": "y"}]}
    out = GS.normalize(raw, "topic", "A2", 6)
    assert out["id"] == "i-work-o-i-m-working" and [b["id"] for b in out["beats"]] == ["b01", "b02"]
    assert out["level"] == "A2" and out["target_minutes"] == 6 and out["language"] == "es"
    assert GS.cost_usd("gpt-4o-mini", {"prompt_tokens": 1_000_000, "completion_tokens": 0}) == pytest.approx(0.15)
    assert "[[" in GS.PROMPT and "language_code" not in GS.user_prompt("t", "A1", 3)


# ── 4. pauses, tokens, captions' inputs ────────────────────────────────────────

def test_pause_marker_is_silent_in_text_but_a_segment_in_audio_and_a_bookmark_in_the_scene():
    n = "¿[[Plays]] o [[is playing]]? Piénsalo. {{pause:3}} La respuesta es [[is playing]]."
    assert L.spoken_text(n) == "¿Plays o is playing? Piénsalo. La respuesta es is playing."
    assert L.pauses(n) == [3.0]
    assert {"pause": 3.0} in L.segments(n)
    text, marks = L.marked_narration({"type": "quiz", "question": "q", "options": ["plays", "is playing"], "answer": 1, "narration": n})
    assert marks["pause:0"] == "p0" and "Piénsalo. <bookmark mark='p0'/>La respuesta" in text
    assert L.cued({"type": "quiz", "question": "q", "options": ["plays", "is playing"], "answer": 1, "narration": n}) == ["is"]
    lesson = {"id": "x", "title": "x", "beats": [{"id": "b01", "type": "tip", "text": "t", "narration": "a {{pause:9}} b"},
                                                 {"id": "b02", "type": "tip", "text": "t", "narration": "a {{pausa}} b"}]}
    problems = "\n".join(L.validate(lesson))
    assert "longer than 6 s" in problems and "not {{pause:N}}" in problems


def test_tokens_carry_language_and_offsets_into_the_spoken_text():
    n = "Mira: [[He has coffee]]. Bien. {{pause:2}} Sigue [[has]]."
    plain, toks = L.spoken_text(n), L.tokens(n)
    assert [t["text"] for t in toks] == ["Mira:", "He", "has", "coffee.", "Bien.", "Sigue", "has."]
    assert [t["en"] for t in toks] == [False, True, True, True, False, False, True]
    for t in toks:
        assert plain[t["offset"]:t["offset"] + len(t["text"])] == t["text"]


def test_shipped_lessons_pause_once_in_every_quiz():
    for path in sorted((STUDIO / "lessons").glob("*.json")):
        lesson = L.load(path)
        for beat in lesson["beats"]:
            if beat["type"] == "quiz":
                assert L.pauses(beat["narration"]) == [3.0], f"{path.stem} {beat['id']} has no 3 s think pause"
        assert lesson.get("english_speed") == 0.92


def test_render_outputs_chapters_poster_time_and_1080p30_flags(tmp_path):
    import renders as R
    argv, _ = R.render_command("/x/manim", "f", "demo", "v")
    assert argv[1:5] == ["-r", "1920,1080", "--fps", "30"] and R.QUALITIES["f"][0] == "1080p30"
    timeline = {"beats": [{"id": "b01", "type": "title", "start": 0.0}, {"id": "b02", "type": "heading", "text": "Parte 1 · El problema", "start": 12.7},
                          {"id": "b03", "type": "heading", "text": "Muy pronto", "start": 4.0}, {"id": "b04", "type": "heading", "text": "Resumen", "start": 347.67}]}
    assert R.chapters_text(timeline) == "00:00 Intro\n00:12 Parte 1 · El problema\n05:47 Resumen\n"
    assert R.poster_time(timeline, 380.0) == 2.5 and R.poster_time({}, 100.0) == 5.0


def test_stitching_sends_only_the_text_that_follows_at_a_switch_and_at_a_beat_start():
    """audio/_probe/stitching (2026-10-13): previous text + request ids gave clean onsets 1/10
    («i-ira la tabla», «d-do the beds»), next_text only 7/10."""
    segs = L.segments("Mira la tabla. [[Make the bed]] es prepararla. {{pause:2}} Y luego más.")
    texts = [n for n, s in enumerate(segs) if "text" in s]
    first, english, spanish, after_pause = texts
    assert GA.stitch_context(segs, first, "la frase de antes", ["r0"]) == ("", "Make the bed es prepararla. Y luego más.", [])
    assert GA.stitch_context(segs, english, "", ["r1"])[0] == "" and GA.stitch_context(segs, english, "", ["r1"])[2] == []
    assert GA.stitch_context(segs, spanish, "", ["r2"])[2] == []                       # en → es: a switch
    before, _, ids = GA.stitch_context(segs, after_pause, "", ["r3"])                 # es, pause, es: same voice goes on
    assert before.endswith("es prepararla.") and ids == ["r3"]
    assert GA.stitch_context(segs, english, "", ["r1"], full=True)[2] == ["r1"]        # --full-stitching: the old way


def test_punctuation_is_never_its_own_request_and_one_language_is_one_request():
    """can-could-pedir b05/b08 sent «:», «,» and «.» to ElevenLabs as Spanish requests."""
    assert L.segments("Habilidad: [[I can drive]]: sé conducir.") == [        # a «:» with words after it is no orphan
        {"text": "Habilidad:", "lang": "es"}, {"text": "I can drive", "lang": "en"}, {"text": ": sé conducir.", "lang": "es"}]
    assert L.segments("Igual: [[I can go]], [[I can help]], [[I can see]].") == [
        {"text": "Igual:", "lang": "es"}, {"text": "I can go, I can help, I can see.", "lang": "en"}]
    assert L.segments("Uno. {{pause:2}} . Dos") == [{"text": "Uno.", "lang": "es"}, {"pause": 2.0}, {"text": ". Dos", "lang": "es"}]
    for path in (STUDIO / "lessons").glob("*.json"):
        for beat in L.load(path)["beats"]:
            for seg in L.segments(beat["narration"]):
                assert "pause" in seg or any(ch.isalnum() for ch in seg["text"]), (path.stem, beat["id"], seg)


def _wav(path, lead_silence_s, burst=False):
    import wave
    import numpy as np
    rate = 44100
    t = np.arange(int(0.4 * rate)) / rate
    voice = 0.5 * np.sin(2 * np.pi * 220 * t)
    head = np.zeros(int(lead_silence_s * rate))
    if burst:                                   # ~50 ms of sound, a 40 ms hole, then the word: «i-ira»
        head = np.concatenate([0.4 * np.sin(2 * np.pi * 300 * np.arange(int(0.05 * rate)) / rate),
                               np.zeros(int(0.04 * rate))])
    x = np.concatenate([head, voice])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return path


def test_the_onset_gate_tells_a_clean_start_from_a_cut_or_a_fragment(tmp_path):
    assert GA.onset_report(_wav(tmp_path / "clean.wav", 0.08))["clean"]
    cut = GA.onset_report(_wav(tmp_path / "cut.wav", 0.0))                        # starts mid-sound
    assert not cut["clean"] and cut["first_db"] > -30
    frag = GA.onset_report(_wav(tmp_path / "frag.wav", 0.0, burst=True))
    assert not frag["clean"] and frag["fragment"] is not None


def test_the_gate_keeps_the_first_clean_take_else_the_cleanest():
    take = lambda clean, first, frag=None: {"onset": {"clean": clean, "first_db": first, "fragment": frag}}
    takes = [take(False, -5), take(True, -60), take(True, -80)]
    assert GA.cleanest(takes) is takes[1]
    dirty = [take(False, -20, (50, 20)), take(False, -12), take(False, -25)]
    assert GA.cleanest(dirty) is dirty[2]                                           # no fragment, quietest start
    assert GA.ONSET_RETRIES == 2


def test_the_onset_check_hears_what_the_owner_hears_on_make_vs_do_b18():
    """Ground truth by ear (owner, 2026-10-13, b18 md5 31bab61a…): a doubled start at «m-make the
    bed», «d-do the beds», «d-do a test», «m-make time», «d-do time» — and NOT at «Make a test»
    or any Spanish piece. The first gate missed all five: it only looked for loud fragments."""
    sys.path.insert(0, str(STUDIO))
    from probes import onset as O
    fixtures = sorted((STUDIO.parent.parent / "tests" / "fixtures" / "manim_onsets").glob("b18_[0-9]*.mp3"))
    assert len(fixtures) == 13
    flagged = {f.stem[4:6] for f in fixtures if O.doubled_onset(O.load(f))}
    assert flagged == {"01", "03", "07", "09", "11"}
    assert not GA.onset_report(fixtures[3])["clean"] and GA.onset_report(fixtures[5])["clean"]   # do the beds / Make a test


def test_the_beat_check_hears_the_owners_five_and_calls_one_request_beats_clean():
    """Owner, 2026-10-14: variant 4 (one request per beat, eleven_multilingual_v2) has no cuts and
    no strange sounds on make-vs-do b18 and can-could-pedir b05/b08. The fragment rule had called
    three of its /d/ starts dirty; the stitched b18 he marked must still give exactly his five."""
    sys.path.insert(0, str(STUDIO))
    import lesson as L
    from probes import beat_onsets as B
    folder = STUDIO.parent.parent / "tests" / "fixtures" / "manim_onsets"

    def dirty(name, lesson, beat):
        narration = next(b for b in L.load(STUDIO / "lessons" / f"{lesson}.json")["beats"] if b["id"] == beat)["narration"]
        rows = B.score(folder / f"{name}.mp3", json.loads((folder / f"{name}.words.json").read_text()), narration)
        return [r["at"] for r in rows if r["dirty"]]

    assert dirty("b18_owner_beat", "make-vs-do", "b18") == [1.98, 4.72, 9.93, 12.4, 14.93]
    for lesson, beat in (("make-vs-do", "b18"), ("can-could-pedir", "b05"), ("can-could-pedir", "b08")):
        assert dirty(f"v4_{lesson}_{beat}", lesson, beat) == [], (lesson, beat)


@pytest.mark.xfail(strict=True, reason="detector false positives: /d/ voice bars at -19.2..-19.7 dB (limit -20) and "
                   "«Mira» at a beat start read as dirty; the owner heard these eleven_v4 beats clean (STEP 55), "
                   "so the v4 path has no onset gate. Strict: passing means the detector learned them — drop the mark.")
def test_the_beat_check_calls_the_owners_clean_eleven_v4_beats_clean():
    sys.path.insert(0, str(STUDIO))
    import lesson as L
    from probes import beat_onsets as B
    folder = STUDIO.parent.parent / "tests" / "fixtures" / "manim_onsets"
    for lesson, beat in (("make-vs-do", "b18"), ("can-could-pedir", "b05"), ("can-could-pedir", "b08")):
        narration = next(b for b in L.load(STUDIO / "lessons" / f"{lesson}.json")["beats"] if b["id"] == beat)["narration"]
        name = f"eleven_v4_{lesson}_{beat}"
        rows = B.score(folder / f"{name}.mp3", json.loads((folder / f"{name}.words.json").read_text()), narration)
        assert [r["at"] for r in rows if r["dirty"]] == [], (lesson, beat)


def test_the_english_report_audits_new_beats_and_keeps_the_rest(tmp_path, monkeypatch):
    sys.path.insert(0, str(STUDIO))
    from probes import english_words_audit as E
    beats = [{"id": i, "text": t, "mp3": f"{i}.mp3", "words": f"{i}.words.json"} for i, t in (("b01", "Di make."), ("b02", "Y do."))]
    (tmp_path / "manifest.json").write_text(json.dumps({"beats": beats}))
    for b in beats:
        (tmp_path / b["words"]).write_text("[]")
    heard = []
    monkeypatch.setattr(E, "audit_beat", lambda mp3, words, narration, tmp: heard.append(mp3.name) or [
        {"time": 0.5, "expected": "do", "heard_en": "Dó", "verdict": "FAIL" if "do" in narration else "ok", "es_too": True}])
    lesson = {"beats": [{"id": "b01", "narration": "Di [[make]]."}, {"id": "b02", "narration": "Y [[do]]."}]}
    assert [b for b, _ in E.lesson_report(tmp_path, lesson, set())] == ["b02"] and heard == ["b01.mp3", "b02.mp3"]
    heard.clear()
    assert [b for b, _ in E.lesson_report(tmp_path, lesson, {"b01"})] == ["b02"] and heard == ["b01.mp3"]


def test_a_beat_is_one_request_per_side_of_a_pause():
    assert GA.beat_chunks("Mira: [[I can swim]], directo.", "es") == [{"text": "Mira: I can swim, directo.", "lang": "es"}]
    assert GA.beat_chunks("¿Lista? {{pause:3}} [[Make the bed]].", "es") == [
        {"text": "¿Lista?", "lang": "es"}, {"pause": 3.0}, {"text": "Make the bed.", "lang": "es"}]
    assert GA.beat_chunks("{{pause:9}}Hola", "es")[0] == {"pause": GA.L.MAX_PAUSE}

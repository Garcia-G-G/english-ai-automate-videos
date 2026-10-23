"""STEP 79 §2: the lesson layout — captions chunked by phrase, English blue in the page's text,
and a collision checker that every drawn beat must pass."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STUDIO = ROOT / "experiments" / "manim_voiceover_poc"
sys.path.insert(0, str(STUDIO))
import lesson as L  # noqa: E402

MANIM = STUDIO / ".venv" / "bin" / "manim"
LINE = 44                      # characters: about what one band line holds at the caption size


def _chars(tokens):
    return sum(len(t["text"]) + 1 for t in tokens) - 1


def _pages(narration, line_w=LINE, times=None):
    return [[" ".join(t["text"] for t in line) for line in page]
            for page in L.caption_chunks(L.tokens(narration), _chars, line_w, times)]


def _beat(lesson, text):
    data = L.load(STUDIO / "lessons" / f"{lesson}.json")
    return next(b for b in data["beats"] if text in b["narration"])


# ── captions by phrase ───────────────────────────────────────────────

def test_the_reviews_first_fragment_keeps_the_english_whole():
    """19 Oct render: «Una frase que se oye muchísimo: She did a» — the sentence was cut mid-way."""
    pages = _pages(_beat("make-vs-do", "Una frase que se oye muchísimo")["narration"])
    joined = [" ".join(p) for p in pages]
    assert any("She did a mistake." in j for j in joined), pages
    assert not any(j.endswith("She did a") for j in joined)


def test_the_reviews_second_fragment_starts_at_a_phrase_not_mid_way():
    """19 Oct render: «cabeza y completamente raro en la del otro.» — a page began in the middle of
    «en tu cabeza». Now the long sentence is cut before its «y»."""
    pages = [" ".join(p) for p in _pages(_beat("make-vs-do", "completamente raro")["narration"])]
    assert "y completamente raro en la del otro." in pages, pages
    assert not any(p.startswith("cabeza") for p in pages)


def test_a_clause_is_cut_at_its_longest_pause_when_times_are_known():
    toks = L.tokens("uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce")
    times = [0.3 * i + (1.0 if i >= 9 else 0.0) for i in range(len(toks))]         # a breath before «diez»
    pages = L.caption_chunks(toks, _chars, 20, times, max_lines=1)
    assert any(p[0][0]["text"] == "diez" for p in pages)


def test_never_inside_an_english_span_never_a_lone_word():
    narration = ("Fíjate bien en esta frase tan larga que tiene inglés dentro: [[I have been waiting for "
                 "you since this morning]], y luego sigue en español un buen rato más todavía. Sí.")
    for page in L.caption_chunks(L.tokens(narration), _chars, 30):
        words = [w for line in page for w in line]
        assert all(len(line) > 1 for line in page) or len(words) == 1
        assert all(_chars(line) <= 30 for line in page)
    spans = {}
    for k, page in enumerate(L.caption_chunks(L.tokens(narration), _chars, 30)):
        for line in page:
            for w in line:
                if w["span"] is not None:
                    spans.setdefault(w["span"], set()).add(k)
    assert all(len(pages) == 1 for pages in spans.values()), "an English span shows on one page"
    lone = L.caption_chunks(L.tokens("Muy bien hecho todo esto. Sí."), _chars, 40)
    assert len(lone) == 1, "a one-word page joins its neighbour"


# ── English in the page's own text ───────────────────────────────────

def test_english_runs_colour_the_english_in_a_list_item_and_nothing_else():
    vocab = {"make", "coffee", "dinner", "a", "decision", "at", "night", "in", "the", "no", "already", "i"}
    item = "Make coffee, make dinner y a veces nada"
    assert [item[a:b] for a, b in L.english_runs(item, vocab)] == ["Make coffee", "make dinner"]
    item = "At night, pero in the night no"
    assert [item[a:b] for a, b in L.english_runs(item, vocab)] == ["At night", "in the night"]
    assert L.english_runs("a la noche", vocab) == []                 # only shared words: Spanish


def test_lists_tips_and_recaps_pass_the_vocabulary():
    source = (STUDIO / "lesson_scene.py").read_text(encoding="utf-8")
    for beat in ("def beat_list", "def beat_tip"):
        body = source[source.index(beat):source.index("def ", source.index(beat) + 10)]
        assert "english=self.vocab" in body, beat


# ── the collision checker ────────────────────────────────────────────

AREAS = {"header": (-6, 3, 6, 3.6), "caption": (-6, -3.6, 6, -2.4), "page": (-5, -2, 5, 2.9),
         "paper": (-7, -2.4, 7, 3.1)}


def test_the_checker_finds_an_overlap_and_a_box_out_of_its_area():
    ok = [{"kind": "page", "text": "a", "box": [-1, 0, 0, 0.5]}, {"kind": "page", "text": "b", "box": [0.1, 0, 1, 0.5]},
          {"kind": "header", "text": "t", "box": [-5, 3.2, -2, 3.4]}, {"kind": "paper", "text": "page", "box": [-6, -2.2, 6, 3.0]}]
    assert L.layout_problems(ok, AREAS) == []
    bubble_over_header = ok + [{"kind": "page", "text": "Yes, and I made a few notes.", "box": [-4, 2.8, 2, 3.3]}]
    problems = L.layout_problems(bubble_over_header, AREAS)
    assert any(p.startswith("outside page") for p in problems) and any(p.startswith("overlap") for p in problems)


@pytest.mark.skipif(not MANIM.exists(), reason="the lesson studio's Manim venv is not installed")
def test_a_drawn_lesson_with_dialogue_list_table_and_quiz_has_no_collision(tmp_path):
    """Real beats of make-vs-do (estimated timings, no audio): every still passes the checker."""
    lesson = L.load(STUDIO / "lessons" / "make-vs-do.json")
    keep = {"b02", "b03", "b04", "b09", "b18", "b22", "b28", "b33", "b37"}
    lesson = {**lesson, "id": "layout-mini", "beats": [b for b in lesson["beats"] if b["id"] in keep]}
    path = tmp_path / "layout-mini.json"
    path.write_text(json.dumps(lesson, ensure_ascii=False), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("VOICE_DIR", "PYTEST_CURRENT_TEST")}
    env.update(STILLS="1", STILLS_OUT=str(tmp_path / "out"), LESSON=str(path), ELEVENLABS_LOCK="1",
               TIMELINE_OUT=str(tmp_path / "timeline.json"))
    run = subprocess.run([str(MANIM), "-ql", "--dry_run", "--disable_caching", "lesson_scene.py", "Lesson"],
                         cwd=str(STUDIO), env=env, capture_output=True, text=True, timeout=900)
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
    stills = json.loads((tmp_path / "out" / "stills.json").read_text(encoding="utf-8"))["stills"]
    assert len(stills) == len(keep)
    assert {s["id"]: s["problems"] for s in stills if s["problems"]} == {}
    kinds = {b["kind"] for s in stills for b in s["boxes"]}
    assert {"header", "caption", "page", "paper"} <= kinds

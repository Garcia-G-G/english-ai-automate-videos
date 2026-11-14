"""STEP 79 §4: free retention — a thumbnail per lesson from its first correction, and YouTube
chapters from the heading beats."""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
STUDIO = ROOT / "experiments" / "manim_voiceover_poc"
sys.path.insert(0, str(STUDIO))
import lesson as L  # noqa: E402
import renders as R  # noqa: E402
import thumbnail as T  # noqa: E402

LESSONS = sorted(p.stem for p in (STUDIO / "lessons").glob("*.json"))


def _lesson(lid):
    return L.load(STUDIO / "lessons" / f"{lid}.json")


# ── the hook ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("lid, pair", [
    ("make-vs-do", ("She did a mistake.", "She made a mistake.")),                   # a transform
    ("comparativos-superlativos", ("My brother is more tall than me.", "My brother is taller than me")),
    ("there-is-there-are", ("In my street have a pharmacy.", "In my street there is a pharmacy")),
    ("morning-phrasal-verbs", ("I wake up me at seven.", "I wake up at seven.")),      # the lesson's override
])
def test_the_hook_is_the_first_wrong_right_pair(lid, pair):
    assert T.hook(_lesson(lid)) == pair


def test_a_scripts_one_chip_fix_is_never_applied_as_a_sentence():
    """comparativos' fix is {more → taller}: applied literally it reads «taller tall»."""
    assert "tall than" not in T.hook(_lesson("comparativos-superlativos"))[1]


def test_a_cut_off_piece_or_the_same_sentence_is_not_a_right_form():
    assert not T._sentence_like("In my street have", "In my street have a pharmacy.")
    assert not T._sentence_like("Ran out of. We ran out of sugar", "We ran out of coffee.")
    assert not T._sentence_like("He have coffee.", "He have coffee.")
    assert T._sentence_like("He has coffee.", "He have coffee.")


def test_a_lesson_without_a_correction_has_no_thumbnail_and_says_so():
    assert T.hook(_lesson("pronunciacion-ed")) is None
    assert T.make(_lesson("pronunciacion-ed"), Path("/nonexistent/x.jpg")) is None


def test_the_title_is_at_most_five_words():
    assert T.short_title("Make y do: dos verbos, una confusión") == "Make y do"
    assert len(T.short_title("Present perfect o pasado simple: cuándo usar cada uno").split()) <= 5


@pytest.mark.parametrize("lid", [l for l in LESSONS if l != "pronunciacion-ed"])
def test_every_thumbnail_is_1280x720_and_readable_at_320(lid, tmp_path):
    out = T.make(_lesson(lid), tmp_path / f"{lid}.jpg")
    img = Image.open(out)
    assert img.size == (1280, 720)
    assert T.MIN_PX * 320 / 1280 >= 16                       # the forms never go under 16 px at 320 wide


# ── chapters ─────────────────────────────────────────────────────────

def _tl(*heads, duration=400.0):
    return {"duration": duration, "beats": [{"id": f"h{k}", "type": "heading", "text": t, "start": s}
                                           for k, (s, t) in enumerate(heads)]}


def test_chapters_start_at_00_00_intro_and_need_three():
    text = R.chapters_text(_tl((24.0, "Parte 1"), (78.5, "Parte 2")))
    assert text == "00:00 Intro\n00:24 Parte 1\n01:18 Parte 2\n"
    assert R.chapters_text(_tl((24.0, "Parte 1"))) == ""                       # two chapters: left out


def test_a_chapter_under_ten_seconds_is_left_out():
    text = R.chapters_text(_tl((4.0, "Muy pronto"), (30.0, "Parte 1"), (35.0, "Pegada"), (90.0, "Parte 2"),
                               (395.0, "Al final"), duration=400.0))
    assert text == "00:00 Intro\n00:30 Parte 1\n01:30 Parte 2\n"


def test_an_hour_long_lesson_writes_hours():
    assert R._stamp(3725) == "1:02:05" and R._stamp(65) == "01:05"


# ── wired into the render and the upload ─────────────────────────────

def test_register_puts_the_thumbnail_beside_the_render():
    source = (STUDIO / "renders.py").read_text(encoding="utf-8")
    assert '"thumbnail": thumbnail_for(lesson_id, target, studio_dir)' in source
    assert "chapters_text(timeline, duration)" in source


def test_the_upload_uses_the_thumbnail_before_the_poster():
    source = (ROOT / "src" / "manim_studio.py").read_text(encoding="utf-8")
    body = source[source.index("def upload_to_youtube"):]
    assert 'for k in ("thumbnail", "poster")' in body

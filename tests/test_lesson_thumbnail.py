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


def test_a_lesson_without_a_render_has_no_thumbnail_and_says_so():
    """An honest thumbnail needs a real frame: no render, no thumbnail."""
    assert T.hook(_lesson("pronunciacion-ed")) is None
    assert T.make(_lesson("make-vs-do"), Path("/nonexistent/x.jpg")) is None
    assert T.make(_lesson("make-vs-do"), Path("/nonexistent/x.jpg"), Path("/nonexistent/v.mp4"), {}) is None


def test_the_title_is_at_most_five_words():
    assert T.short_title("Make y do: dos verbos, una confusión") == "Make y do"
    assert len(T.short_title("Present perfect o pasado simple: cuándo usar cada uno").split()) <= 5


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    import subprocess
    mp4 = tmp_path_factory.mktemp("v") / "lesson.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=960x540:r=10:d=12", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    return mp4


TIMELINE = {"beats": [{"type": "title", "start": 0.0}, {"type": "sentence", "start": 3.0, "text": "I need to make my homework."}]}


def test_the_thumbnail_is_1280x720_with_a_real_frame_under_2mb(video, tmp_path):
    out = T.make(_lesson("make-vs-do"), tmp_path / "t.jpg", video, TIMELINE)
    assert Image.open(out).size == (1280, 720) and out.stat().st_size <= 2_000_000
    info = json.loads(out.with_suffix(".json").read_text())
    assert info["frame_t"] >= 3.0 + 1.5                                             # after the first sentence drew


def test_at_most_four_words_one_yellow_the_corrected_one():
    ws = T.words(_lesson("make-vs-do"))
    assert 1 <= len(ws) <= 4 and ws == ["Make", "y", "do"]
    assert ws[T.highlight(_lesson("make-vs-do"), ws)] in ws


def test_text_is_readable_at_320_and_the_duration_badge_corner_is_empty(video, tmp_path):
    from PIL import ImageStat
    out = T.make(_lesson("make-vs-do"), tmp_path / "t.jpg", video, TIMELINE)
    info = json.loads(out.with_suffix(".json").read_text())
    assert info["white_contrast"] >= 4.5 and info["yellow_contrast"] >= 4.5 and info["xheight_320"] >= T.XHEIGHT_MIN_320
    badge = Image.open(out).convert("L").crop(T.BADGE)
    assert max(ImageStat.Stat(badge).stddev) < 6                                    # plain gradient only: no text, no card, no Bubi


def test_no_sentence_beat_means_no_frame_to_show_and_no_thumbnail(video, tmp_path):
    assert T.make(_lesson("make-vs-do"), tmp_path / "t.jpg", video, {"beats": [{"type": "title", "start": 0.0}]}) is None


def test_the_thumbnail_follows_the_render_in_register():
    source = (STUDIO / "renders.py").read_text(encoding="utf-8")
    assert "thumbnail.make(lesson, target.with_suffix(\".thumb.jpg\"), target, timeline)" in source


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
    assert '"thumbnail": thumbnail_for(lesson_id, target, studio_dir, timeline)' in source
    assert "chapters_text(timeline, duration)" in source


def test_the_upload_uses_the_thumbnail_before_the_poster():
    source = (ROOT / "src" / "manim_studio.py").read_text(encoding="utf-8")
    body = source[source.index("def upload_to_youtube"):]
    assert 'for k in ("thumbnail", "poster")' in body

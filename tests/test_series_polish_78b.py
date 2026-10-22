"""STEP 78b §1: the series polish from the proof review."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video.series import comic, escena, mensajes, poster  # noqa: E402
from video.series import gate as G  # noqa: E402
from video.series import render as R  # noqa: E402
from video.series import series_kit as K  # noqa: E402

DRAFTS = ROOT / "content" / "hecho_con_claude" / "drafts"


def _draft(sid):
    return json.loads((DRAFTS / f"{sid}.json").read_text(encoding="utf-8"))


def _rgb(img):
    return np.asarray(img.convert("RGB")).astype(int)


def _region(a, box):
    x0, y0, x1, y1 = (int(v) for v in box)
    return a[y0:y1, x0:x1]


# ── mensajes: the examples after the correction ──────────────────────

def test_mensajes_examples_are_the_phrases_after_the_card_but_not_the_right_form():
    s = _draft("hc_m001")
    tl = R.estimated_timeline(s)
    ex = mensajes.examples(s, tl)
    assert ex, "hc_m001's voice gives examples after the correction"
    card = mensajes.times(s, tl)["card"]
    assert all(at > card for _x, at, _ok in ex)
    assert all(not mensajes._same(x, s["correction"]["right"]) for x, _a, _ok in ex)


def test_each_example_card_enters_on_its_phrase_and_stays_in_the_safe_area():
    s = _draft("hc_m001")
    tl = R.estimated_timeline(s)
    lay = mensajes.layout(s)
    text, at, _ok = mensajes.examples(s, tl)[0]
    box = (K.W / 2 - mensajes.EX_W / 2, lay["stack_top"], K.W / 2 + mensajes.EX_W / 2, lay["stack_top"] + mensajes.EX_H)
    before = _region(_rgb(mensajes.frame(at - 0.1, s, tl)), box)
    after = _region(_rgb(mensajes.frame(at + 0.6, s, tl)), box)
    assert np.abs(after - before).mean() > 20, text
    assert all(K.in_safe_area(b) for label, b in mensajes.text_boxes(s) if label.startswith("example slot"))


@pytest.mark.parametrize("sid", [p.stem for p in sorted(DRAFTS.glob("hc_m*.json"))])
def test_every_mensajes_stack_has_room_for_at_least_three_cards(sid):
    assert mensajes.layout(_draft(sid))["slots"] >= 3


def test_past_its_slots_the_oldest_card_leaves():
    s = _draft("hc_m001")
    lay = dict(mensajes.layout(s), slots=2)
    from PIL import Image
    shown = [("One a", 1.0, True), ("Two b", 2.0, True), ("Three c", 3.0, True)]
    img = Image.new("RGBA", (K.W, K.H), (0, 0, 0, 255))
    mensajes._draw_examples(img, 5.0, lay, shown)
    a = _rgb(img)
    top = (K.W / 2 - mensajes.EX_W / 2, lay["stack_top"], K.W / 2 + mensajes.EX_W / 2, lay["stack_top"] + mensajes.EX_H)
    third = (top[0], top[1] + 2 * (mensajes.EX_H + mensajes.EX_GAP), top[2], top[3] + 2 * (mensajes.EX_H + mensajes.EX_GAP))
    assert _region(a, top).mean() > 100            # slot 1 now holds «Two b»
    assert _region(a, third).mean() < 5            # nothing past the second slot


# ── escena: frame 0 is the thumbnail ─────────────────────────────────

@pytest.mark.parametrize("sid", ["hc_e001", "hc_e011", "hc_e027"])
def test_escena_frame_zero_shows_take_one_and_the_question(sid):
    s = _draft(sid)
    tl = R.estimated_timeline(s)
    lay = escena.layout(s)
    f0 = _rgb(escena.frame(0.0, s, tl))
    blank = _rgb(escena.frame(0.0, dict(s, scene=dict(s["scene"], take1=" ")), tl))
    assert np.abs(_region(f0, lay["boxes"]["take1"]) - _region(blank, lay["boxes"]["take1"])).mean() > 8
    spot = _region(f0, lay["boxes"]["spot"])
    assert (np.abs(spot - np.array(escena.RED[:3])).sum(axis=2) < 40).mean() > 0.3
    assert K.in_safe_area(lay["boxes"]["spot"])


def test_the_question_goes_once_take_one_is_struck():
    s = _draft("hc_e001")
    tl = R.estimated_timeline(s)
    tm, lay = escena.times(s, tl), escena.layout(s)
    late = _region(_rgb(escena.frame(tm["strike"] + 0.5, s, tl)), lay["boxes"]["spot"])
    assert (np.abs(late - np.array(escena.RED[:3])).sum(axis=2) < 40).mean() < 0.05


# ── poster: display line breaks ──────────────────────────────────────

POSTERS = [p.stem for p in sorted(DRAFTS.glob("hc_p*.json"))]


@pytest.mark.parametrize("sid", POSTERS)
def test_poster_display_lines_never_start_with_a_separator_nor_leave_a_lone_short_word(sid):
    lay = poster.layout(_draft(sid))
    for which in ("wrong", "right"):
        _size, lines = lay[which]
        for line in lines:
            assert line.split()[0] not in poster.SEPARATORS, (which, lines)
            if len(lines) > 1:
                assert not (len(line.split()) == 1 and len(line) <= poster.SHORT_WORD), (which, lines)


def test_a_phrase_after_a_slash_is_kept_whole():
    assert poster.display_lines("DESPITE / IN SPITE OF", 120, poster.BLOCK_TEXT_W, 2) == ("DESPITE /", "IN SPITE OF")


def test_breaks_go_after_the_separator_when_there_is_one():
    assert poster.layout(_draft("hc_p011"))["right"][1] == ("DEGREE =", "CARRERA")


# ── comic: the hook points at something on frame 0 ───────────────────

@pytest.mark.parametrize("sid", ["hc_c001", "hc_c014", "hc_c027"])
def test_comic_frame_zero_shows_the_question_and_the_three_options(sid):
    s = _draft(sid)
    tl = R.estimated_timeline(s)
    lay = comic.layout(s)
    f0 = _rgb(comic.frame(0.0, s, tl))
    for box in [lay["prompt_box"], *lay["opt_boxes"]]:
        assert (_region(f0, box).sum(axis=2) > 700).mean() > 0.4, box        # a white card is there
    assert all(K.in_safe_area(b) for _l, b in comic.text_boxes(s))


# ── gate: no still stretch over 4 s ──────────────────────────────────

def _clip(path, vf_src, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{vf_src}:s={K.W}x{K.H}:r=30:d={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True, timeout=120)


def test_a_static_clip_is_one_long_still_stretch(tmp_path):
    _clip(tmp_path / "s.mp4", "color=c=0x3a2a20", 5)
    still = G.longest_still(tmp_path / "s.mp4")
    assert still["seconds"] > G.STILL_MAX_S and still["from"] == 0.0


def test_grain_counts_as_motion(tmp_path):
    _clip(tmp_path / "n.mp4", "color=c=0x808080", 3)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp_path / "n.mp4"), "-vf", "noise=alls=8:allf=t",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp_path / "g.mp4")], check=True, timeout=120)
    assert G.longest_still(tmp_path / "g.mp4")["seconds"] < 0.5


def test_a_name_one_letter_off_is_heard_but_a_different_short_word_is_not():
    assert G._same_word("anna", "ana") and G._same_word("your", "youre")
    assert not G._same_word("am", "an") and not G._same_word("have", "am") and not G._same_word("cold", "gold")
    assert G._in_order(["earth", "to", "ana"], ["earth", "to", "anna"]) == 3
    assert G._in_order(["i", "am", "cold"], ["i", "have", "cold"]) < 3


def test_a_phrase_missed_by_one_transcript_is_taken_from_the_second(tmp_path):
    s = json.loads((DRAFTS / "hc_c001.json").read_text(encoding="utf-8"))
    tl = R.estimated_timeline(s)
    phrases = [e for b in tl["beats"] for e in b["english"]]
    words = [{"word": w, "start": e["start"] + 0.1 * k, "end": e["start"] + 0.1 * k + 0.08}
             for e in phrases for k, w in enumerate(e["text"].split())]
    half = [w for w in words if w["start"] < phrases[1]["start"]]
    first = G.english_heard(tl, half)
    assert first["missing"]
    assert G.english_heard(tl, words)["missing"] == []


@pytest.mark.parametrize("sid", [p.stem for p in sorted(DRAFTS.glob("hc_c*.json"))])
def test_the_no_stamp_sits_beside_the_option_not_over_its_words(sid):
    s = _draft(sid)
    boxes = dict(comic.text_boxes(s))
    for k, opt in enumerate(comic.layout(s)["opt_boxes"]):
        if k != s["quiz"]["answer"]:
            assert boxes[f"stamp {comic.LETTERS[k]}"][0] >= opt[2] - 30


def test_the_inter_licence_is_the_official_one_of_the_vendored_version():
    """rsms/inter, tag v4.0, LICENSE.txt (the fonts' name table says Version 4.000)."""
    import hashlib
    data = (ROOT / "assets" / "fonts" / "OFL-Inter.txt").read_bytes()
    assert hashlib.sha256(data).hexdigest() == "262481e844521b326f5ecd053e59b98c8b2da78c8ee1bdbb6e8174305e54935a"


def test_english_is_compared_by_sound_not_by_spelling():
    """hc_c010 through the panel: «since three o'clock» heard as «since 3 o clock», «for» as «4»."""
    assert G._by_sound(["since", "3", "o", "clock"]) == G._by_sound(["since", "three", "oclock"])
    assert G._by_sound(["4"]) == G._by_sound(["for"]) == ["for"]
    assert G._by_sound(["i", "am", "cold"]) != G._by_sound(["i", "have", "cold"])
    tl = {"beats": [{"start": 20.0, "end": 27.0, "english": [{"text": "for", "start": 23.0},
                                                              {"text": "since three o'clock", "start": 26.0}]}]}
    words = [{"word": w, "start": t} for w, t in [("va.", 23.4), ("4.", 23.9), ("since", 26.3), ("3", 26.4),
                                                  ("o", 26.8), ("clock.", 27.0)]]
    assert G.english_heard(tl, words)["missing"] == []

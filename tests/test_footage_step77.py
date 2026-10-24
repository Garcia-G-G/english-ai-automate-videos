"""STEP 77 §6: footage for the notebook Shorts — the script's theme first, crossfades between
clips, one grade for the set, and frame indices from timestamps."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import topic_clips  # noqa: E402
from video import clip_background as CB  # noqa: E402


def _hdys():
    return {"type": "how_do_you_say", "items": [{"english": w} for w in
                                                 ("pillow", "blanket", "lamp", "rug", "drawer", "closet")]}


def test_a_how_do_you_say_page_asks_for_its_own_objects_before_the_category():
    themes = topic_clips.footage_themes(_hdys())
    assert themes == ["pillow close up", "blanket close up", "lamp close up", "rug close up"]
    # STEP 78 §0: a level type without a place in its theme gets the calm set, not nothing
    assert topic_clips.footage_themes({"type": "choose_level", "items": [{"english": "x"}]})[0] in topic_clips.CALM_FOOTAGE
    assert topic_clips.footage_themes({"type": "quiz"}) == []
    q = topic_clips.build_queries("Bedroom", "basic_vocab", count=6, themes=themes)
    assert q[:4] == themes and len(q) == len(set(q)) == 6                 # then two category subjects
    assert topic_clips.build_queries("Bedroom", "basic_vocab", count=2, themes=themes) == themes[:2]
    assert topic_clips.build_queries("Bedroom", "basic_vocab", count=3) == \
        topic_clips.build_queries("Bedroom", "basic_vocab", count=3, themes=())   # unchanged without


def test_the_themes_reach_the_fetch_from_the_resolver_and_the_panel(monkeypatch, tmp_path):
    import pipeline
    seen = {}

    def fake(topic, category, **kw):
        seen.update(kw)
        return None
    monkeypatch.setattr(topic_clips, "fetch_for_topic", fake)
    try:                                       # the fetch declines; the cache tier may then serve or refuse
        pipeline.resolve_background(None, None, topic="Bedroom", category="basic_vocab",
                                    dest_dir=tmp_path, duration=60, themes=["pillow close up"])
    except pipeline.BackgroundUnavailable:
        pass
    assert seen.get("themes") == ["pillow close up"]
    admin = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    assert "themes=footage_themes" in admin and "footage_themes = _themes(_artifact)" in admin


@pytest.mark.parametrize("fps, step", [(30.0, 1), (60.0, 2), (25.0, None), (30000 / 1001, None), (60000 / 1001, None)])
def test_frame_indices_come_from_timestamps(fps, step):
    idx = [CB.frame_index(n / 30, fps) for n in range(30 * 120)]
    if step:
        assert idx == [n * step for n in range(30 * 120)]                 # int(t * fps) duplicated some
    d = np.diff(idx)
    assert d.min() >= 0
    expected = fps / 30                                                    # source frames per output frame
    assert abs(idx[-1] - expected * (len(idx) - 1)) <= 1


def _solid(path, colour, seconds=1.0):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c={colour}:s=1080x1920:r=30:d={seconds}", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)], check=True, timeout=120)


def test_two_clips_crossfade_over_half_a_second(tmp_path):
    _solid(tmp_path / "a.mp4", "0x202020")
    _solid(tmp_path / "b.mp4", "0xC0C0C0")
    bg = CB.ClipLibraryBackground(str(tmp_path), 1080, 1920, duration=2.0, seed=3, video_type="how_do_you_say")
    try:
        cut = bg._playlist[1]["start"]
        first, second = (bg.get_frame(t).mean() for t in (cut - 0.4, cut + 0.4))
        mid = bg.get_frame(cut).mean()
        assert abs(mid - (first + second) / 2) < 6                         # halfway through the blend
        quarter = bg.get_frame(cut - CB.CROSSFADE / 4).mean()
        assert min(first, second) < quarter < max(first, second)
        assert abs(bg.get_frame(cut - CB.CROSSFADE / 2 - 0.05).mean() - first) < 1   # before the window
    finally:
        bg.close()


def test_one_grade_pulls_the_clips_toward_one_another(tmp_path):
    _solid(tmp_path / "dark.mp4", "0x404040")
    _solid(tmp_path / "light.mp4", "0x909090")
    _solid(tmp_path / "mid.mp4", "0x606060")
    bg = CB.ClipLibraryBackground(str(tmp_path), 1080, 1920, duration=3.0, seed=1, video_type="how_do_you_say")
    try:
        means = []
        for entry in bg._playlist:
            t = entry["start"] + entry["clip"]["duration"] / 2
            means.append(bg.get_frame(t).mean())
        raw = [0x40, 0x90, 0x60]
        assert max(means) - min(means) < 0.6 * (max(raw) - min(raw))      # closer than they came in
        gains = [c["gain"] for c in bg._clips]
        assert all(CB.GRADE_LIMITS[0] <= g.min() and g.max() <= CB.GRADE_LIMITS[1] for g in gains)
    finally:
        bg.close()


def test_behind_the_page_no_watermark_scrim_is_solved():
    """§4 removed the notebook watermark, so §6's soft plan no longer darkens its corner."""
    plan = CB.ClipLibraryBackground._soft_plan.__doc__
    assert "no watermark scrim" in plan

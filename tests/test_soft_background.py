"""STEP 75 §6: behind an opaque page the footage is softened, not banded; HEADLINE_COLOR has one source."""
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import video_types  # noqa: E402
from video import clip_background as CB  # noqa: E402


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=2",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(d / "a.mp4")],
                   check=True, timeout=120)
    return d


def test_the_opaque_page_types_are_how_do_you_say_and_the_levels():
    assert "how_do_you_say" in video_types.OPAQUE_PAGE_TYPES
    assert video_types.LEVEL_TYPES <= video_types.OPAQUE_PAGE_TYPES
    assert "quiz" not in video_types.OPAQUE_PAGE_TYPES and "educational" not in video_types.OPAQUE_PAGE_TYPES


def test_an_opaque_page_type_gets_softened_footage_and_no_band(clips, monkeypatch):
    import clip_contrast
    monkeypatch.setattr(clip_contrast, "treatment_for_dir", lambda *a, **k: pytest.fail("sampled the clips"))
    bg = CB.ClipLibraryBackground(str(clips), 1080, 1920, duration=2.0, seed=1, video_type="how_do_you_say")
    soft_dir = Path(bg._soft_dir)
    try:
        assert bg.softened and bg.scrim == 0.0
        assert bg.contrast_report["mark_meets_floor"]                 # the mark keeps its 3:1
        assert bg.contrast_report["skipped"].startswith("opaque page")
        assert list(soft_dir.glob("*.soft.mp4"))
        cap = cv2.VideoCapture(bg._clips[0]["path"])
        assert (cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) == (270, 480)
        cap.release()
        frame = bg.get_frame(1.0)
        assert frame.shape == (1920, 1080, 3)
    finally:
        bg.close()
    assert not soft_dir.exists()
    original = cv2.cvtColor(cv2.VideoCapture(str(clips / "a.mp4")).read()[1], cv2.COLOR_BGR2RGB)
    sharp = lambda img: cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()
    assert sharp(frame) < sharp(original) / 5                       # blurred
    warm = lambda img: float(img[..., 0].mean() - img[..., 2].mean())
    assert warm(frame) > warm(original)                              # warmer
    centre, corner = frame[860:1060, 440:640].mean(), frame[:200, :200].mean()
    assert corner < centre                                           # vignette


def test_other_types_still_measure_their_band(clips, monkeypatch):
    import clip_contrast
    calls = []
    real = clip_contrast.treatment_for_dir
    monkeypatch.setattr(clip_contrast, "treatment_for_dir", lambda *a, **k: calls.append(a) or real(*a, **k))
    bg = CB.ClipLibraryBackground(str(clips), 1080, 1920, duration=2.0, seed=1, video_type="quiz")
    bg.close()
    assert calls and not bg.softened and bg._soft_dir is None


def test_a_clip_ffmpeg_cannot_soften_is_used_as_it_is(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    assert CB.soften_clip(bad, tmp_path, 1080, 1920) == bad


def test_headline_colour_comes_from_the_one_place_renderers_read():
    import text_contrast
    from config import colors
    assert text_contrast.HEADLINE_COLOR is colors.ENGLISH_WORD_COLOR

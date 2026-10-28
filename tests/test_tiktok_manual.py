"""STEP 73 §4: TikTok by hand: the caption, the Finder/clipboard hand-off, the manual record."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import admin  # noqa: E402
import publication_log as PL  # noqa: E402


def test_the_caption_carries_title_text_and_missing_hashtags_within_2200():
    caption = admin.tiktok_caption("Say it right", "Body #LearnEnglish", ["LearnEnglish", "Idiomas"])
    assert caption == "Say it right\n\nBody #LearnEnglish\n\n#Idiomas"
    assert len(admin.tiktok_caption("t", "x" * 5000, ["a"])) == 2200


def test_prepare_reveals_the_file_and_copies_the_caption():
    calls = []
    admin.prepare_for_tiktok(Path("/v/x.mp4"), "hola", run=lambda cmd, **kw: calls.append((cmd, kw)))
    assert calls[0][0] == ["open", "-R", "/v/x.mp4"]
    assert calls[1][0] == ["pbcopy"] and calls[1][1]["input"] == "hola"


def test_a_manual_upload_is_recorded_and_is_not_an_open_attempt():
    row = admin.record_manual_tiktok("bv030_x", "output/approved/quiz/bv030_x.mp4", "caption")
    assert row["status"] == PL.ATTEMPT_MANUAL == "manual" and row["platform"] == "tiktok"
    attempts = PL.read_attempts()
    assert admin.manual_tiktok_row("bv030_x", attempts)["detail"] == "caption"
    assert admin.manual_tiktok_row("other", attempts) is None
    assert PL.open_attempt("bv030_x", "tiktok") is None      # the guard does not hold it


def test_tiktok_is_out_of_the_automatic_upload_platforms():
    assert "tiktok" not in admin._upload_platforms() and "youtube" in admin._upload_platforms()

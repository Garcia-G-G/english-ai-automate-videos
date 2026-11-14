"""STEP 85b §0-§2: choosing and checking the thumbnail frame. The fixtures are the three cases of the spec."""
import io
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import thumbs as T  # noqa: E402
from test_tablero_frame import _data  # noqa: E402
from video.tablero import frame as F  # noqa: E402
from video.how_do_you_say import Timeline  # noqa: E402


def _draw(d, dur):
    return lambda t: F.create_frame_tablero(t, d, dur)


def test_a_mid_flip_frame_is_rejected_and_the_settled_one_three_tiles_later_passes():
    d, dur = _data()
    tl = Timeline(d, dur)
    b = F.Beats(tl)
    draw = _draw(d, dur)
    flipping = T.measure(draw, b.fill_end[2] + F.FLIP_DUR / 4)
    settled = T.measure(draw, tl.es[3][0] + 0.5)
    assert flipping["steady"] > 4 and not flipping["steady_ok"] and not flipping["ok"]
    assert settled["steady"] < 0.5 and settled["ok"], settled


def test_a_black_transition_frame_is_rejected():
    black = lambda t: np.zeros((1920, 1080, 3), dtype=np.uint8)                          # noqa: E731
    m = T.measure(black, 1.0)
    assert not m["not_blank_ok"] and not m["sharp_ok"] and not m["ok"]


def test_the_thresholds_sit_between_the_settled_and_the_flipping_measurements():
    assert 0.3 < T.STEADY_MAX < 4.0 and T.SHARP_MIN < 600


def test_settle_slides_a_failing_moment_forward_to_the_first_steady_frame():
    d, dur = _data()
    b = F.Beats(Timeline(d, dur))
    mid = b.fill_end[2] + F.FLIP_DUR / 2
    t, m = T.settle(_draw(d, dur), mid, dur)
    assert m["ok"] and m["shift"] > 0 and t > mid and m["shift"] <= T.SLIDE_MAX


def test_settle_keeps_a_good_moment_where_it_is():
    d, dur = _data()
    t0 = Timeline(d, dur).es[3][0] + 0.5
    t, m = T.settle(_draw(d, dur), t0, dur)
    assert t == t0 and m["shift"] == 0.0


def test_the_moments_follow_the_format_rule():
    d, dur = _data()
    tl = Timeline(d, dur)
    m = dict(T.hdys_moments(d, dur))
    assert m["B"] == 0.0 and m["A"] == pytest.approx(tl.es[3][0] + 0.5) and m["C"] > F.Beats(tl).flip_end[5]


def test_the_jpeg_is_1080x1920_progressive_under_2mb_without_metadata():
    d, dur = _data()
    raw = T.encode_jpeg(F.create_frame_tablero(0.0, d, dur))
    im = Image.open(io.BytesIO(raw))
    assert im.size == (1080, 1920) and len(raw) <= T.JPEG_MAX and im.info.get("progressive") == 1
    assert not im.getexif() and "exif" not in im.info


def test_make_for_tablero_writes_three_candidates_the_choice_and_the_why(tmp_path):
    d, dur = _data()
    mp4 = tmp_path / "v.mp4"
    info = T.make_for_tablero(mp4, d, dur)
    folder = T.thumb_dir(mp4)
    assert {p.name for p in (folder / "cands").glob("*.png")} == {"A.png", "B.png", "C.png"}
    assert info["chosen"] == "A" and "passed every check" in info["why"]
    assert Image.open(folder / "thumb.jpg").size == (1080, 1920)
    saved = json.loads((folder / "thumb.json").read_text())
    assert saved["chosen"] == "A" and saved["metrics"]["A"]["ok"] and saved["metrics"]["B"]["t"] == 0.0


def test_switching_candidates_re_encodes_without_a_render(tmp_path):
    d, dur = _data()
    mp4 = tmp_path / "v.mp4"
    T.make_for_tablero(mp4, d, dur)
    folder = T.thumb_dir(mp4)
    before = (folder / "thumb.jpg").read_bytes()
    T.pick(folder, "B")
    assert (folder / "thumb.jpg").read_bytes() != before
    assert json.loads((folder / "thumb.json").read_text())["chosen"] == "B"
    with pytest.raises(FileNotFoundError):
        T.pick(folder, "Z")


def test_the_thumb_folder_travels_with_the_video(tmp_path):
    d, dur = _data()
    src, dest = tmp_path / "pending", tmp_path / "approved"
    src.mkdir(), dest.mkdir()
    mp4 = src / "v.mp4"
    T.make_for_tablero(mp4, d, dur)
    T.carry(mp4, dest)
    assert (dest / "v.thumb" / "thumb.jpg").exists() and not (src / "v.thumb").exists()
    T.carry(mp4, dest)                                                                  # nothing left to move: no error


def test_other_formats_get_frames_extracted_from_the_mp4_with_the_same_files(tmp_path):
    import subprocess
    mp4 = tmp_path / "q.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=540x960:r=10:d=10", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    info = T.make_for_video(mp4, {"type": "quiz"}, 10.0)
    folder = T.thumb_dir(mp4)
    assert {p.name for p in (folder / "cands").glob("*.png")} == {"A.png", "B.png", "C.png"} and info["metrics"]["A"]["source"] == "mp4"
    assert Image.open(folder / "thumb.jpg").size == (1080, 1920)


def test_a_failure_to_make_thumbnails_is_swallowed_not_raised(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    assert T.make_for_video(bad, {"type": "quiz"}, 5.0) is None


def test_approve_and_reject_carry_the_thumb_folder(tmp_path, monkeypatch):
    import jobs
    from panel_core import videos
    monkeypatch.setattr(jobs, "PENDING_DIR", tmp_path / "pending")
    pending = tmp_path / "pending" / "quiz"
    pending.mkdir(parents=True)
    for name in ("a", "b"):
        (pending / f"{name}.mp4").write_bytes(b"x")
        (pending / f"{name}.json").write_text("{}")
        (pending / f"{name}.thumb").mkdir()
        (pending / f"{name}.thumb" / "thumb.jpg").write_bytes(b"j")
    videos.approve_video(pending / "a.mp4", tmp_path / "approved")
    videos.reject_video(pending / "b.mp4", tmp_path / "rejected")
    assert (tmp_path / "approved" / "quiz" / "a.thumb" / "thumb.jpg").exists()
    assert (tmp_path / "rejected" / "quiz" / "b.thumb" / "thumb.jpg").exists()


# ── §2: nothing cut, readable small ──────────────────────────────────

def test_nothing_is_cut_on_the_fixture_and_a_box_that_overflows_is_caught():
    from thumbs import checks as C
    d, _ = _data()
    assert C.nothing_cut(d) == {"ok": True, "cut": []}
    long = {**d, "items": [{**d["items"][0], "english": "an extraordinarily long english phrase here"}] + d["items"][1:]}
    assert "english1" in C.nothing_cut(long)["cut"]


def test_a_tile_below_the_caption_zone_counts_as_cut(monkeypatch):
    from thumbs import checks as C
    d, _ = _data()
    monkeypatch.setattr(F.kit, "GRID_Y0", F.kit.GRID_Y0 + 60)
    assert "tile10" in C.nothing_cut(d)["cut"]


def test_contrast_is_enforced_and_the_x_height_is_only_a_warning():
    from thumbs import checks as C
    d, _ = _data()
    r = C.readable_small(d)
    assert r["contrast_ok"] and r["contrast"]["chip_topic"] >= 4.5
    assert r["warnings"] and all(v < C.XHEIGHT_MIN for v in r["xheight_px"].values())     # the 7 px rule would fail every tile
    assert C.tablero_checks(d)["ok"]                                                      # ...and it does not fail the thumbnail


def test_low_contrast_fails_the_check(monkeypatch):
    from thumbs import checks as C
    d, _ = _data()
    monkeypatch.setattr(F.kit, "PAPER", (200, 200, 200, 255))
    monkeypatch.setattr(F.kit, "INK", (150, 150, 150, 255))
    assert not C.readable_small(d)["contrast_ok"]


def test_thumb_json_stores_the_checks(tmp_path):
    d, dur = _data()
    mp4 = tmp_path / "v.mp4"
    T.make_for_tablero(mp4, d, dur)
    saved = json.loads((T.thumb_dir(mp4) / "thumb.json").read_text())
    assert saved["checks"]["nothing_cut"]["ok"] and saved["checks"]["readable_small"]["xheight_px"]["english"] < 7

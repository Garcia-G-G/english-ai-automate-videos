"""STEP 75 §7: a registered lesson gets one final pass — x264 crf 14, BT.601→709 with tags,
faststart, −14 LUFS — and a failed pass leaves Manim's file as it was."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
STUDIO = ROOT / "experiments" / "manim_voiceover_poc"
sys.path.insert(0, str(STUDIO))
sys.path.insert(0, str(ROOT / "src"))

import renders as R  # noqa: E402
import loudness  # noqa: E402

BLUE = (0x1B, 0x6F, 0xA8)


def _manim_like(path: Path):
    """What Manim writes: untagged yuv420p converted with the BT.601 matrix, quiet stereo AAC."""
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=0x1B6FA8:s=320x180:r=30:d=6,format=rgb24",
                    "-f", "lavfi", "-i", "sine=f=330:r=48000:d=6,volume=0.6,aformat=channel_layouts=stereo",
                    "-vf", "scale=out_color_matrix=bt601:out_range=tv", "-c:v", "libx264", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True, timeout=60)


def _decoded_centre(path: Path, matrix: str):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-vf",
                          f"scale=in_color_matrix={matrix}:in_range=tv,format=rgb24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True, timeout=30).stdout
    return np.frombuffer(raw, np.uint8).reshape(180, 320, 3)[90, 160]


def test_the_final_pass_tags_bt709_keeps_the_colour_and_normalises(tmp_path):
    lesson = tmp_path / "l.mp4"
    _manim_like(lesson)
    assert loudness.measure(lesson)["I"] < -20
    report = R.final_encode(lesson)
    v = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=color_space,color_primaries,color_transfer,color_range", "-of", "json",
                                   str(lesson)], capture_output=True, text=True, check=True, timeout=30).stdout)
    assert v["streams"][0] == {"color_range": "tv", "color_space": "bt709", "color_primaries": "bt709",
                               "color_transfer": "bt709"}
    assert max(abs(int(a) - b) for a, b in zip(_decoded_centre(lesson, "bt709"), BLUE)) <= 3
    m = loudness.measure(lesson)
    assert abs(m["I"] - loudness.TARGET_I) <= 1.0 and m["TP"] <= -1.5
    a = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                                   "stream=sample_rate,channels", "-of", "json", str(lesson)],
                                  capture_output=True, text=True, check=True, timeout=30).stdout)["streams"][0]
    assert (a["sample_rate"], a["channels"]) == ("48000", 2)
    head = lesson.read_bytes()[:4096]
    assert b"moov" in head                                           # faststart
    assert report["loudnorm"] in ("linear", "dynamic")   # a steady test tone goes dynamic; speech is linear
    assert not list(tmp_path.glob(".encode-*"))


def test_a_failed_pass_leaves_the_original_untouched(tmp_path, monkeypatch):
    import proc
    lesson = tmp_path / "l.mp4"
    _manim_like(lesson)
    before = lesson.read_bytes()
    real = proc.run
    calls = []

    def flaky(cmd, **kw):
        calls.append(cmd)
        if "-tune" in cmd:
            raise subprocess.CalledProcessError(1, cmd, stderr=b"encoder exploded")
        return real(cmd, **kw)
    monkeypatch.setattr(proc, "run", flaky)
    with pytest.raises(subprocess.CalledProcessError):
        R.final_encode(lesson)
    assert lesson.read_bytes() == before and not list(tmp_path.glob(".encode-*"))


def test_register_records_a_failed_encode_and_keeps_the_copy(tmp_path, monkeypatch):
    src = tmp_path / "manim.mp4"
    _manim_like(src)
    monkeypatch.setattr(R, "final_encode", lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(R, "render_features", lambda *a, **k: {})
    row = R.register(src, "lesson-x", "teacher", R.DEFAULT_QUALITY, 1.0, studio_dir=tmp_path)
    assert row["final_encode"] == {"error": "boom"}
    target = tmp_path / "renders" / row["file"]
    assert target.read_bytes() == src.read_bytes()

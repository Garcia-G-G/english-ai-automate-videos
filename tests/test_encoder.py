"""STEP 75 §4: Shorts encode with libx264, BT.709 tags, B-frames, 2 s GOP, faststart; a dead
ffmpeg is a readable error; the gate judges the duration WITH the outro."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video.compositor import render_video_ffmpeg  # noqa: E402

BLUE = (0x1B, 0x6F, 0xA8)


def _frames(t):
    img = np.zeros((320, 180, 3), np.uint8)
    img[:] = BLUE
    img[: int(20 + 100 * t) % 320, :20] = 255           # some motion, so B-frames have work
    return img


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    d = tmp_path_factory.mktemp("enc")
    audio = d / "a.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:r=44100", "-t", "5", str(audio)],
                   check=True, timeout=60)
    out = d / "v.mp4"
    render_video_ffmpeg(_frames, str(audio), str(out), 5.0, fps=30, width=180, height=320)
    return out


def _probe(path, entries):
    return json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                      entries, "-of", "json", str(path)], capture_output=True, text=True,
                                     check=True, timeout=30).stdout)


def test_the_stream_is_x264_high_bt709_with_b_frames(clip):
    s = _probe(clip, "stream=codec_name,profile,pix_fmt,has_b_frames,color_space,color_primaries,"
                     "color_transfer,color_range")["streams"][0]
    assert (s["codec_name"], s["profile"], s["pix_fmt"]) == ("h264", "High", "yuv420p")
    assert int(s["has_b_frames"]) > 0
    assert (s["color_space"], s["color_primaries"], s["color_transfer"], s["color_range"]) == \
        ("bt709", "bt709", "bt709", "tv")


def test_keyframes_every_two_seconds_and_moov_first(clip):
    kf = subprocess.run(["ffprobe", "-v", "error", "-skip_frame", "nokey", "-select_streams", "v:0",
                         "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(clip)],
                        capture_output=True, text=True, check=True, timeout=30).stdout.split()
    times = sorted(float(t.strip(",")) for t in kf)
    assert len(times) == 3 and times[1] == pytest.approx(2.0, abs=0.05)   # -g 60 at 30 fps
    head = clip.read_bytes()[:4096]
    assert 0 <= head.find(b"moov") < head.find(b"mdat") or b"mdat" not in head


def test_the_brand_blue_survives_the_round_trip(clip):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(clip), "-frames:v", "1", "-vf",
                          "scale=in_color_matrix=bt709:in_range=tv,format=rgb24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True, timeout=30).stdout
    px = np.frombuffer(raw, np.uint8).reshape(320, 180, 3)[200, 120]
    assert max(abs(int(a) - b) for a, b in zip(px, BLUE)) <= 3


def test_a_dead_ffmpeg_raises_with_its_own_error(tmp_path):
    with pytest.raises(RuntimeError, match="stopped reading frames|FFmpeg encoding failed") as caught:
        render_video_ffmpeg(_frames, str(tmp_path / "missing.mp3"), str(tmp_path / "v.mp4"), 30.0,
                            fps=30, width=180, height=320)
    assert "missing.mp3" in str(caught.value) or "rc=" in str(caught.value)


def test_no_videotoolbox_is_left():
    src = (ROOT / "src" / "video" / "compositor.py").read_text(encoding="utf-8")
    assert "h264_videotoolbox" not in src and "use_hardware" not in src


def test_the_gate_judges_the_final_duration_with_the_outro(monkeypatch, tmp_path):
    import duration_spec
    import pipeline
    import qa_gate
    from video import outro as O
    monkeypatch.setattr(qa_gate, "analyze", lambda p: {"artifact": "x", "video_type": "quiz",
                                                       "measured_duration": 70.0})
    monkeypatch.setattr(qa_gate, "verdict", lambda r: {"verdict": "PASS", "blocking_flags": []})
    monkeypatch.setattr(O, "select_variant", lambda seed=None: {"id": "v"})
    monkeypatch.setattr(O, "append_outro", lambda *a, **k: pytest.fail("outro on a too-long video"))
    ceiling = duration_spec.reject_window("quiz")["max_seconds"]
    lengths = {"v.mp4": ceiling - 2.0, "v": 4.0}
    monkeypatch.setattr(qa_gate, "probe_duration",
                        lambda p: lengths["v.mp4"] if p.endswith("v.mp4") and "outro" not in p else 4.0)
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x")
    res = pipeline.finalize_video(vid, tmp_path / "a.json")
    assert res["gate"] == "REJECT" and res["outro_appended"] is False
    assert res["blocking_flags"][0].startswith("final_duration:")
    assert res["final_duration"]["measured_seconds"] == pytest.approx(ceiling + 2.0)


def _finalize_how_do_you_say(monkeypatch, tmp_path, body_seconds):
    import pipeline
    import qa_gate
    from video import outro as O
    monkeypatch.setattr(qa_gate, "analyze", lambda p: {"artifact": "x", "video_type": "how_do_you_say",
                                                       "measured_duration": body_seconds})
    monkeypatch.setattr(qa_gate, "verdict", lambda r: {"verdict": "PASS", "blocking_flags": []})
    monkeypatch.setattr(O, "select_variant", lambda seed=None: {"id": "v"})
    monkeypatch.setattr(O, "append_outro", lambda p, v, output_path=None:
                        Path(output_path).write_bytes(b"y") or output_path)
    monkeypatch.setattr(O, "measure_seam", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "_loudness_check", lambda *a, **k: None)
    monkeypatch.setattr(qa_gate, "probe_duration",
                        lambda p: 4.0 if "outro" in p and "tmp" not in p else body_seconds)
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x")
    return pipeline.finalize_video(vid, tmp_path / "a.json")


def test_how_do_you_say_has_its_own_window_and_is_rejected_outside_it(monkeypatch, tmp_path):
    """STEP 76 §0: 66-86 s aimed, 55-95 s accepted, with the outro."""
    ok = _finalize_how_do_you_say(monkeypatch, tmp_path, 78.7)              # 82.7 s, an approved render
    assert ok["gate"] == "PASS" and ok["final_duration"]["blocks"] is True
    long = _finalize_how_do_you_say(monkeypatch, tmp_path, 92.0)            # 96 s
    assert long["gate"] == "REJECT" and long["blocking_flags"][0].startswith("final_duration:")


def test_a_type_without_its_own_window_is_warned_not_rejected(monkeypatch, tmp_path):
    import duration_spec
    monkeypatch.setattr(duration_spec, "declares_window", lambda t: False)
    res = _finalize_how_do_you_say(monkeypatch, tmp_path, 92.0)
    assert res["gate"] == "PASS" and res["outro_appended"] is True
    assert res["final_duration"]["status"] == "OUT_OF_BAND" and res["final_duration"]["blocks"] is False


def test_the_default_preset_is_medium_and_drafts_stay_ultrafast():
    """STEP 77 §2b: medium is the default (CPU, not colour); --fast still asks ultrafast."""
    import inspect
    from video import compositor
    assert inspect.signature(compositor.render_video_ffmpeg).parameters["preset"].default == "medium"
    src = (Path(__file__).resolve().parent.parent / "src" / "video" / "__init__.py").read_text()
    assert '{"preset": "ultrafast"} if fast_mode' in src

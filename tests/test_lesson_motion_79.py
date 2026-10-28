"""STEP 79 §3: motion with a purpose — Bubi on the page, a page turn between parts, pencil marks
on the key word, the 5 s stillness rule in the lesson gate, and the v3 end card."""
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
SOURCE = (STUDIO / "lesson_scene.py").read_text(encoding="utf-8")
BRAND = ROOT / "assets" / "branding" / "english-unlimited"


def _body(name):
    start = SOURCE.index(f"    def {name}(")
    end = SOURCE.find("\n    def ", start + 10)
    return SOURCE[start:end if end > 0 else len(SOURCE)]


# ── Bubi ─────────────────────────────────────────────────────────────

def test_every_bubi_pose_is_a_v3_asset_on_disk():
    import re
    poses = dict(re.findall(r'"(\w+)": "([\w/]+\.png)"', SOURCE[SOURCE.index("BUBI_POSES"):SOURCE.index("BUBI_CUES")]))
    assert set(poses) == {"hola", "wow", "lo_lograste", "bien_hecho"}
    assert all((BRAND / f).exists() for f in poses.values())


@pytest.mark.parametrize("beat, cue", [("beat_title", "wave"), ("beat_quiz", "think"), ("beat_quiz", "celebrate"),
                                       ("beat_tip", "point"), ("beat_recap", "nod")])
def test_bubi_reacts_on_his_cue(beat, cue):
    assert f'self.bubi_cue("{cue}")' in _body(beat)


def test_he_thinks_during_the_pause_and_celebrates_the_answer():
    quiz = _body("beat_quiz")
    assert quiz.index('bubi_cue("think")') < quiz.index("Create(arc)") < quiz.index('bubi_cue("celebrate")')


def test_between_cues_he_breathes_two_percent_on_the_clock():
    assert "BREATH = 0.02" in SOURCE
    body = _body("mount_bubi")
    assert "add_updater" in body and "self.play" not in body, "an updater: Bubi costs the lesson no time"


# ── page turn, pencil marks ──────────────────────────────────────────

def test_a_parte_heading_turns_the_page_with_a_paper_sound():
    heading = _body("beat_heading")
    assert "Parte" in heading and "self.turn_page()" in heading
    turn = _body("turn_page")
    assert "run_time=0.6" in turn and 'self.sfx("page")' in turn


def test_the_paper_sound_sits_22_db_under_the_voice():
    import sfx
    assert "page" in sfx.NAMES
    x = sfx.render("page")
    assert abs(sfx.rms_db(x) - (sfx.VOICE_RMS_DB - 22.0)) < 0.5
    assert 0.4 < len(x) / sfx.RATE < 0.7


def test_the_pencil_circles_a_highlight_strikes_the_wrong_chip_and_ticks_the_right_one():
    sentence = _body("beat_sentence")
    assert "hand_circle(chips[i]" in sentence and "Create(c) for c in circled" in sentence
    fix = _body("fix_chip")
    assert fix.index("strike(chips[i])") < fix.index("Transform(c, paint(") or "strike(chips[i])" in fix
    assert "check_mark(" in fix and "Create(tick)" in fix


def test_the_camera_push_is_at_most_three_percent():
    import re
    push = float(re.search(r"^PUSH = ([\d.]+)", SOURCE, re.M).group(1))
    assert 1.0 < push <= 1.03


# ── the end card ─────────────────────────────────────────────────────

def test_the_end_card_uses_the_v3_logo_breathes_and_keeps_its_two_frames():
    end = _body("end_screen")
    assert "brand_logo()" in end and "logo.add_updater" in end
    assert 'BRAND_DIR / "logo_horizontal.png"' in SOURCE
    assert "for _ in range(2)" in end, "the two end-screen placeholders for YouTube"
    from PIL import Image
    logo = Image.open(BRAND / "logo_horizontal.png")
    assert logo.size == (1871, 600), "the v3 horizontal logo (Bubi + wordmark)"


# ── the lesson gate ──────────────────────────────────────────────────

def _clip(path, video, audio, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{video}{':' if '=' in video else '='}s=320x180:r=30:d={seconds}",
                    "-f", "lavfi", "-i", f"{audio}:d={seconds}", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(path)], check=True, timeout=120)


def test_the_lesson_gate_rejects_a_still_stretch_over_five_seconds(tmp_path):
    import renders
    _clip(tmp_path / "still.mp4", "color=c=0xeeeeee", "sine=f=440:sample_rate=48000", 7)
    report = renders.lesson_gate(tmp_path / "still.mp4", {"cues": []})
    assert report["gate"] == "REJECT"
    assert any(f.startswith("still:") for f in report["flags"]), report
    assert report["checks"]["still"]["seconds"] > renders.STILL_MAX_S


def test_the_lesson_gate_wants_cues_and_minus_14_lufs(tmp_path):
    import renders
    _clip(tmp_path / "quiet.mp4", "testsrc2", "sine=f=440:sample_rate=48000", 3)
    report = renders.lesson_gate(tmp_path / "quiet.mp4", {})
    assert any(f.startswith("sync:") for f in report["flags"])            # no cue records: sync not proved
    assert any(f.startswith("loudness:") for f in report["flags"]) or abs(report["checks"]["lufs"] + 14) <= 1
    assert report["checks"]["still"]["seconds"] < 1.0                     # testsrc2 moves every frame

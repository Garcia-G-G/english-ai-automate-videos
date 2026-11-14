"""Garcia (STEP 80): «the videos cut too fast and don't give time to learn the answer of the mini
challenge». After the challenge: 3 s to think (3-2-1), the answer held 3 s, and the outro shows it
from its first frame."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from video.series import render as R  # noqa: E402
from video.series import series_kit as K  # noqa: E402

DRAFTS = ROOT / "content" / "hecho_con_claude" / "drafts"


def _draft(sid):
    return json.loads((DRAFTS / f"{sid}.json").read_text(encoding="utf-8"))


def test_the_answer_stays_on_screen_about_seven_seconds():
    assert K.THINK_S >= 3.0 and K.REVEAL_S >= 3.0
    assert K.OUTRO_ANSWER_AT == 0.0
    from video import outro
    assert K.REVEAL_S + outro.OUTRO_DURATION - K.OUTRO_ANSWER_AT >= 7.0


@pytest.mark.parametrize("sid", [p.stem for p in sorted(DRAFTS.glob("hc_*.json"))])
def test_the_countdown_and_the_answer_sit_inside_the_safe_area(sid):
    s = _draft(sid)
    box = dict(R.style_module(s["style"]).text_boxes(s))["challenge"]
    assert K.in_safe_area(K.reveal_layout(box, s["challenge"]["answer"])["box"])


def test_think_shows_a_countdown_and_then_the_answer_card(tmp_path):
    from PIL import Image
    s = _draft("hc_p019")
    box = dict(R.style_module("poster").text_boxes(s))["challenge"]
    lay = K.reveal_layout(box, s["challenge"]["answer"])
    base = Image.new("RGBA", (K.W, K.H), (240, 235, 225, 255))
    frames = {}
    for t in (0.5, 1.5, K.THINK_S + 1.0):
        img = base.copy()
        K.after_challenge(img, t, box, s["challenge"]["answer"])
        x0, y0, x1, y1 = (int(v) for v in lay["box"])
        frames[t] = np.asarray(img.convert("RGB"))[y0:y1, x0:x1].astype(int)
    assert np.abs(frames[0.5] - frames[1.5]).mean() > 0.2                  # 3 → 2 (a small disc in the box)
    green = np.array([47, 143, 91])
    assert (np.abs(frames[K.THINK_S + 1.0] - green).sum(axis=2) < 60).mean() > 0.01   # the answer, in green


def test_a_silent_render_is_longer_by_the_think_and_reveal_time(tmp_path):
    s = _draft("hc_p019")
    info = R.render_series(s, tmp_path / "p.mp4", tmp_path / "w", silent=True, workers=1)
    from video import outro
    assert info["duration"] == pytest.approx(info["voice_seconds"] + K.AFTER_S + outro.OUTRO_DURATION, abs=0.05)
    assert info["reveal_at"] == pytest.approx(info["voice_seconds"] + K.THINK_S, abs=0.01)


def test_a_script_already_voiced_in_pieces_keeps_its_cached_pieces(monkeypatch):
    """Merging into one request per sentence must not make an already-voiced script spend again."""
    import tts_bilingual as B
    from video.series import beats
    s = _draft("hc_c010")
    data = {"type": "hecho_con_claude", "full_script": beats.full_script(s)}
    settings = {**B.resolve_settings(), "model_id": "eleven_v3", "voice_id": "v"}
    monkeypatch.setattr(B, "one_request", lambda vtype, st: st.get("one_request", True))
    seen = {}
    monkeypatch.setattr(B, "all_cached", lambda calls, st: seen.setdefault("n", len(calls)) and True)
    plan = {}

    def fake_synth(call, out, st, take=0):
        plan.setdefault("calls", []).append(call["text"])
        raise RuntimeError("stop after planning")
    monkeypatch.setattr(B, "_synthesize_segment", fake_synth)
    with pytest.raises(Exception):
        B.generate_bilingual_narration(data, "/tmp/x.mp3", settings=settings)
    split = B.plan_calls(data, {**settings, "one_request": False})
    assert seen["n"] == len(split)                       # the split plan was checked against the cache…
    assert plan["calls"][0] == split[0]["text"]          # …and used, since it was all cached

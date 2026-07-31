#!/usr/bin/env python3
"""The pre-rendered outro: caching, copy variants, and concat safety.

    python3 -m pytest tests/test_outro.py

No API calls. The cache-hit tests rely on assets/outro/*.mp4 already existing;
where they do not, the test skips rather than silently spending money.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video import outro as O  # noqa: E402


# ── copy config ──────────────────────────────────────────────────────

def test_config_parses_and_has_live_variants():
    cfg = O.load_variants()

    assert cfg["variants"], "no variants defined"
    assert any(v.get("weight", 0) > 0 for v in cfg["variants"])


def test_every_variant_has_the_fields_the_renderer_reads():
    for v in O.load_variants()["variants"]:
        for key in ("id", "weight", "spoken", "line_1", "line_2"):
            assert key in v, f"variant {v.get('id')} missing {key}"


def test_variant_ids_are_unique_and_filename_safe():
    """The id becomes a cache filename, so a duplicate silently overwrites
    another variant's clip."""
    ids = [v["id"] for v in O.load_variants()["variants"]]

    assert len(ids) == len(set(ids))
    for i in ids:
        assert i and all(c.isalnum() or c in "-_" for c in i), i


def test_the_url_appears_in_every_spoken_line():
    """The outro is the CTA. A variant that does not say the domain is not
    doing its job."""
    for v in O.load_variants()["variants"]:
        assert "learningroutes.com" in v["spoken"]
        assert "learningroutes.com" in v["line_2"]


def test_selection_is_weighted_and_respects_a_zero_weight(monkeypatch):
    cfg = {
        "variants": [
            {"id": "kept", "weight": 5, "spoken": "a learningroutes.com",
             "line_1": "a", "line_2": "learningroutes.com"},
            {"id": "retired", "weight": 0, "spoken": "b learningroutes.com",
             "line_1": "b", "line_2": "learningroutes.com"},
        ]
    }
    monkeypatch.setattr(O, "load_variants", lambda: cfg)

    picks = {O.select_variant(seed=str(i))["id"] for i in range(30)}

    assert picks == {"kept"}, "a zero-weight variant was selected"


def test_selection_is_reproducible_for_a_given_seed():
    """Same video, same variant — so a re-render does not silently change
    which copy was measured."""
    assert O.select_variant(seed="vid-1")["id"] == O.select_variant(seed="vid-1")["id"]


def test_all_weights_zero_raises_rather_than_picking_nothing(monkeypatch):
    monkeypatch.setattr(O, "load_variants", lambda: {
        "variants": [{"id": "x", "weight": 0, "spoken": "learningroutes.com",
                      "line_1": "x", "line_2": "learningroutes.com"}]})

    with pytest.raises(ValueError):
        O.select_variant()


# ── the cache is the point ───────────────────────────────────────────

def _existing():
    return sorted(O.OUTRO_DIR.glob("*.mp4"))


def test_a_cached_variant_is_reused_and_never_resynthesised(monkeypatch):
    """RENDERED ONCE, EVER. Any implementation that synthesises per video is
    wrong: it costs money per render and lets the voice drift between videos."""
    clips = _existing()
    if not clips:
        pytest.skip("no rendered outro yet")

    variant_id = clips[0].stem
    monkeypatch.setattr(O, "_synthesize", lambda *a, **k: pytest.fail(
        "outro was re-synthesised despite a cache hit"))

    got = O.ensure_outro({"id": variant_id, "spoken": "x",
                          "line_1": "x", "line_2": "learningroutes.com"})

    assert got == clips[0]


def test_cached_clips_have_the_expected_duration():
    clips = _existing()
    if not clips:
        pytest.skip("no rendered outro yet")

    for clip in clips:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(clip)], capture_output=True, text=True)
        assert abs(float(out.stdout.strip()) - O.OUTRO_DURATION) < 0.05, clip.name


# ── concat safety ────────────────────────────────────────────────────

def test_outro_streams_match_what_the_compositor_produces():
    """`-c copy` is only legal when the parameters match. Both clips come out
    of the same compositor, but a mismatch silently forcing a re-encode is
    exactly the quality loss nobody notices, so it is checked."""
    clips = _existing()
    if not clips:
        pytest.skip("no rendered outro yet")

    params = O._probe_params(str(clips[0]))

    assert params["video"][0] == "h264"
    assert params["video"][1:3] == (1080, 1920)
    assert params["video"][4] == "yuv420p"
    assert params["audio"][0] == "aac"
    assert params["audio"][1] == "44100"


def test_append_refuses_a_mismatched_source(tmp_path, monkeypatch):
    """Rather than silently re-encoding."""
    clips = _existing()
    if not clips:
        pytest.skip("no rendered outro yet")

    monkeypatch.setattr(O, "ensure_outro", lambda v, force=False: clips[0])
    monkeypatch.setattr(O, "_probe_params", lambda p: (
        {"video": ("h264", 720, 1280, "30/1", "yuv420p")}   # deliberate mismatch
        if str(p).endswith("main.mp4")
        else {"video": ("h264", 1080, 1920, "30/1", "yuv420p")}))

    fake = tmp_path / "main.mp4"
    fake.write_bytes(b"x")

    with pytest.raises(RuntimeError, match="parameters differ"):
        O.append_outro(str(fake), {"id": clips[0].stem})


# ── ordering ─────────────────────────────────────────────────────────

def test_a_rejected_video_gets_no_outro(monkeypatch, tmp_path):
    """The outro points at Learning Routes. Putting the brand on the end of
    something the gate just refused is worse than shipping nothing."""
    import pipeline
    import qa_gate
    monkeypatch.setattr(qa_gate, "analyze", lambda p: {
        "artifact": "x", "video_type": "quiz", "flags": ["dead_air:5.0s"],
        "measured_duration": 30.0})
    monkeypatch.setattr(qa_gate, "verdict", lambda r: {
        "verdict": "REJECT", "blocking_flags": ["dead_air:5.0s"]})

    def boom(*a, **k):
        pytest.fail("an outro was appended to a REJECTED video")
    monkeypatch.setattr(O, "append_outro", boom)

    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x")
    res = pipeline.finalize_video(vid, tmp_path / "a.json")

    assert res["gate"] == "REJECT"
    assert res["outro_appended"] is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

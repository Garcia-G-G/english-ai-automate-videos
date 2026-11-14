"""STEP 78 §7: the series' quality gate, its queue, and the panel's door to a render."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import series  # noqa: E402
from video.series import gate as G  # noqa: E402
from video.series import render as R  # noqa: E402


def _draft(sid):
    return json.loads((ROOT / "content" / "hecho_con_claude" / "drafts" / f"{sid}.json").read_text(encoding="utf-8"))


def _heard_words(tl, drop=()):
    """A transcript that says every English phrase in its beat, except those in `drop`."""
    out = []
    for b in tl["beats"]:
        for e in b["english"]:
            if e["text"] in drop:
                continue
            for k, w in enumerate(e["text"].split()):
                out.append({"word": w, "start": e["start"] + 0.1 * k, "end": e["start"] + 0.1 * k + 0.08})
    return out


def test_every_english_phrase_must_be_heard_near_its_beat():
    s = _draft("hc_c001")
    tl = R.estimated_timeline(s)
    assert G.english_heard(tl, _heard_words(tl))["missing"] == []
    gone = tl["beats"][0]["english"][1]["text"]
    assert G.english_heard(tl, _heard_words(tl, drop={gone}))["missing"] == [gone]
    late = [dict(w, start=w["start"] + 30) for w in _heard_words(tl)]      # heard, but nowhere near
    assert G.english_heard(tl, late)["missing"]


def test_a_two_second_silent_clip_is_rejected_for_duration_and_loudness(tmp_path):
    s = _draft("hc_p001")
    info = R.render_series(s, tmp_path / "p.mp4", tmp_path / "w", silent=True, seconds=2.0, workers=1)
    report = G.check(s, tmp_path / "p.mp4", info, transcribe=lambda p: _heard_words(info["timeline"]))
    assert report["gate"] == "REJECT"
    assert any(f.startswith("duration:") for f in report["flags"])
    assert any(f.startswith("loudness:") for f in report["flags"])
    assert report["checks"]["hook"]["shown"] and report["checks"]["safe_areas"]["outside"] == []


def test_frame_zero_without_its_hook_is_caught(tmp_path):
    from video.series import poster
    s = _draft("hc_p001")
    tl = R.estimated_timeline(s)
    import numpy as np
    blank = np.asarray(poster.frame(0.0, dict(s, hook_text=" "), tl).convert("RGB"))
    assert not G.hook_shown(s, poster, tl, blank)["shown"]
    full = np.asarray(poster.frame(0.0, s, tl).convert("RGB"))
    assert G.hook_shown(s, poster, tl, full)["shown"]


PROOFS = ROOT / "_audit" / "stills" / "STEP78b"


@pytest.mark.parametrize("sid", ["hc_m001", "hc_p019", "hc_m010", "hc_e001", "hc_p011", "hc_c019"])
def test_the_proofs_pass_the_gate(sid):
    """The STEP 78b renders (the STEP 78 ones predate the stillness rule)."""
    if not (PROOFS / f"{sid}.mp4").exists():
        pytest.skip("the proof is not rendered on this machine")
    info = json.loads((PROOFS / f"{sid}.json").read_text(encoding="utf-8"))
    report = G.check(_draft(sid), PROOFS / f"{sid}.mp4", info, transcribe=lambda p: _heard_words(info["timeline"]))
    assert report["gate"] == "PASS", report["flags"]


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(series, "QUEUE_DIR", tmp_path / "queue")
    monkeypatch.setattr(series, "DONE_DIR", tmp_path / "done")
    monkeypatch.setattr(series, "OUTPUT", tmp_path / "output")
    return tmp_path


def test_all_108_drafts_are_queued_and_the_drafts_stay(dirs):
    counts = series.queue_drafts()
    assert sum(n for lv in counts.values() for n in lv.values()) == 108
    assert all(n == 9 for lv in counts.values() for n in lv.values())
    assert len(list((dirs / "queue").glob("hc_*.json"))) == 108 and len(series.drafts()) == 108
    assert sum(n for lv in series.queue_drafts().values() for n in lv.values()) == 0     # a second run copies nothing


@pytest.mark.parametrize("verdict", ["PASS", "REJECT"])
def test_render_one_files_the_video_by_its_gate(dirs, monkeypatch, verdict):
    series.queue_drafts()
    import video.series.render as RR

    def fake_render(script, out, work, **kw):
        Path(out).write_bytes(b"mp4")
        return {"timeline": {}, "duration": 40.0, "tts_usd": 0.09, "outro_variant": "aprende-ingles"}
    monkeypatch.setattr(RR, "render_series", fake_render)
    monkeypatch.setattr(G, "check", lambda *a, **k: {"gate": verdict, "flags": [] if verdict == "PASS" else ["x"],
                                                     "checks": {}})
    out = series.render_one(style="poster", level="dificil")
    video = Path(out["video"])
    assert video.exists() and video.parent.name == "hecho_con_claude"
    assert video.parent.parent.name == ("pending" if verdict == "PASS" else "rejected")
    side = json.loads(video.with_suffix(".json").read_text())
    s = _draft(out["script_id"])
    assert side["title"] == s["title"] and side["description"] == s["caption"] and side["hashtags"] == s["hashtags"]
    # the panel reads the sidecar's verdict as a string (STEP 78b: a dict here broke every page)
    import admin
    record = admin.gate_record(side)
    assert record["known"] and record["verdict"] == verdict and record["flags"] == side["blocking_flags"]
    moved = (dirs / "done" / f"{out['script_id']}.json").exists()
    assert moved == (verdict == "PASS")


def test_the_panel_can_start_a_series_render_now():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "src" / "admin.py"), default_timeout=120)
    at.session_state["current_page"] = "Generate"
    at.run()
    next(x for x in at.selectbox if x.label == "Tipo de vídeo").set_value(series.PANEL_LABEL).run()
    assert [b.disabled for b in at.button if b.label == "Crear video"] == [False]
    import admin
    assert callable(admin.start_series_generation)


def test_the_guard_reads_neither_the_skipped_shelf_nor_the_series():
    sys.path.insert(0, str(ROOT / "tools"))
    import queue_guard as Q
    shelves = {Q.DONE_DIR, Q.SKIPPED_DIR, Q.SERIES_DIR}
    assert not [p for p in Q.queued_scripts() if shelves & set(p.parents)]
    assert (Q.SKIPPED_DIR / "README.md").exists()


def test_a_script_a_job_is_rendering_is_not_picked_again(dirs, monkeypatch):
    """Two panel jobs started in the same second both took hc_e002 and shared its work dir."""
    series.queue_drafts()
    first = series.pick()
    assert first is not None
    monkeypatch.setattr(series, "_CLAIMED", {first[0].name})
    again = series.pick()
    assert again is None or again[0] != first[0]

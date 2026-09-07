#!/usr/bin/env python3
"""Every capability the engine has must have a door onto it.

    python3 -m pytest tests/test_dashboard_doors.py

THE DEFECT CLASS THIS PINS, which no other test in this repo can catch:
a capability that is built, tested, and unreachable. None of the code below
was wrong. It was fine, and it had passing tests, and nothing could call it.

  · run_pipeline_with_tracking took `background` and `dry_run` and the UI
    passed neither. pipeline.resolve_profile takes a profile NAME and admin
    called it with no argument, so the `children` profile — configured in
    config.yaml, tested, complete — had never once been selectable.
  · pipeline.render_video takes use_v2 and nothing on the dashboard set it.
  · The scheduler offered four of six types, because the UI held its own
    hand-written copy of the list. fill_blank and pronunciation could not be
    produced from the unattended batch AT ALL.
  · topic_history.coverage() returns a dict shaped for a screen. Its only
    caller was its own test.

So the tests here are mostly about REACHABILITY, not arithmetic: they assert
that a value chosen at the top arrives at the bottom. A widget that renders
and does nothing is the exact failure being corrected, so "the control
exists" is never the assertion — "the control's value arrives" is.
"""

import ast
import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

logging.getLogger("streamlit").setLevel(logging.CRITICAL)

import admin  # noqa: E402
from script_generator import VIDEO_TYPES  # noqa: E402


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Point the job ledger at tmp_path (conftest does not cover JOBS_FILE)."""
    path = tmp_path / "generation_jobs.json"
    path.write_text(json.dumps({"active": [], "history": []}))
    monkeypatch.setattr(admin, "JOBS_FILE", path)
    return path


class _Recorder:
    """A stand-in pipeline that records what it was handed."""

    RENDER_TIMEOUT_S = 60
    TERMINAL_PRESET = "static_midnight"

    class PipelineError(Exception):
        pass

    def __init__(self):
        self.profile_name = "UNSET"
        self.background_arg = "UNSET"
        self.render_kwargs = {}

    def resolve_profile(self, name=None):
        self.profile_name = name
        return {"name": name or "adults", "content": {"categories": None}}

    def resolve_provider_name(self):
        return "fake"

    def generate_tts(self, script_data, audio_path, script_path=None, dry_run=False):
        Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
        Path(audio_path).write_bytes(b"0" * 32)
        json_path = Path(audio_path).with_suffix(".json")
        json_path.write_text(json.dumps({"duration": 20.0}))
        return Path(audio_path), json_path

    def merge_script_into_tts(self, script_data, json_path):
        return None

    def resolve_background(self, profile, background, **kwargs):
        self.background_arg = background
        return background or "static_midnight"

    def render_video(self, audio_path, data_path, video_path, **kwargs):
        self.render_kwargs = kwargs
        Path(video_path).parent.mkdir(parents=True, exist_ok=True)
        Path(video_path).write_bytes(b"0" * 4096)
        return Path(video_path)

    def finalize_video(self, video_path, json_path, variant_seed=None):
        return {"gate": "PASS", "video": str(video_path), "blocking_flags": []}


@pytest.fixture
def recorder(monkeypatch, tmp_path, ledger):
    """A full run of run_pipeline_with_tracking with no paid call and no render."""
    rec = _Recorder()
    monkeypatch.setattr(admin, "pipeline", rec)
    monkeypatch.setattr(admin, "generate_script",
                        lambda c, t, v: {"type": v, "word": "test"})
    monkeypatch.setattr(admin, "get_random_topic",
                        lambda allowed_categories=None: ("social", {"english": "test"}))
    monkeypatch.setattr(admin, "reset_tracker", lambda video_id=None: None)
    for name, sub in (("SCRIPTS_DIR", "scripts"), ("AUDIO_DIR", "audio"),
                      ("PENDING_DIR", "pending"), ("CLIPS_DIR", "clips")):
        monkeypatch.setattr(admin, name, tmp_path / sub)
    return rec


# ═══════════════════ §2 · the scheduler offers every type ═══════════════════

def test_the_scheduler_can_produce_all_six_types():
    """fill_blank and pronunciation could not be produced from the unattended
    batch at all — not misconfigured, absent from the UI's own list."""
    offered = set(admin.scheduler_default_types())

    assert offered == set(VIDEO_TYPES)
    assert {"fill_blank", "pronunciation"} <= offered


def test_the_dashboard_holds_no_hand_written_copy_of_the_type_list():
    """THE ACTUAL FIX. Two of six went missing because the UI wrote the list
    out by hand; a third list under 'Add 5 of Each Type' queued three types
    and reported fifteen videos. VIDEO_TYPES is defined once, in
    script_generator, and the UI must read it rather than restate it."""
    tree = ast.parse((ROOT / "src" / "admin.py").read_text(encoding="utf-8"))

    hand_written = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [e.value for e in node.elts
                      if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if (len(values) == len(node.elts) and len(values) >= 3
                    and all(v in VIDEO_TYPES for v in values)):
                hand_written.append((node.lineno, values))

    assert not hand_written, f"video-type lists written out by hand: {hand_written}"


def test_every_type_gets_a_label_including_one_nobody_has_added_yet():
    """A label map that has to be edited for each new type is the same defect
    one layer down. An unknown type gets a readable label, not a KeyError and
    not a silent omission."""
    for video_type in VIDEO_TYPES:
        assert admin.type_label(video_type)

    assert admin.type_label("fill_blank") == "Fill Blank"
    assert admin.type_label("some_future_type") == "Some Future Type"


# ═══════════════════ §3 · the used-topic memory has a screen ═══════════════

def test_the_memory_report_is_computed_from_the_real_corpus():
    """720 topics and 160 used are measurements, not numbers typed into a
    caption. The screen must recompute them or it will go stale silently."""
    report = admin.topic_memory_report()

    assert report["total"] > 0
    assert report["used"] + report["unused"] == report["total"]
    assert report["by_category"], "no per-category rows to draw"


def test_the_percentage_is_derived_rather_than_stored():
    report = admin.topic_memory_report()

    assert report["percent_used"] == pytest.approx(
        100.0 * report["used"] / report["total"], abs=0.05)


def test_the_repeats_answer_the_question_that_prompted_the_screen():
    """'se me han repetido como 4 videos con el mismo tema'. The repeats list
    is the answer, so it is sorted worst-first and is not an appendix."""
    report = admin.topic_memory_report()
    times = [r["times"] for r in report["repeats"]]

    assert times == sorted(times, reverse=True)
    assert all(t > 1 for t in times), "a 'repeat' seen once is not a repeat"


def test_an_empty_corpus_reports_zero_rather_than_dividing_by_it(monkeypatch):
    monkeypatch.setattr(admin.topic_history, "coverage",
                        lambda *a, **k: {"total": 0, "used": 0, "unused": 0,
                                         "by_category": [], "repeats": []})

    assert admin.topic_memory_report()["percent_used"] == 0.0


# ═══════════════ §1 · the Generate page's controls arrive ═══════════════

def test_the_chosen_profile_reaches_the_resolver(recorder, ledger):
    """admin called resolve_profile() with no argument, so the dashboard was
    pinned to config.yaml's default and `children` was unreachable."""
    admin.run_pipeline_with_tracking("job1", "educational", dry_run=True,
                                     profile_name="children")

    assert recorder.profile_name == "children"


def test_no_profile_chosen_still_means_the_config_default(recorder, ledger):
    """Widening the door must not change what the door did before."""
    admin.run_pipeline_with_tracking("job2", "educational", dry_run=True)

    assert recorder.profile_name is None


def test_the_chosen_background_reaches_the_resolver(recorder, ledger):
    """The parameter was already there and the UI never passed a value."""
    admin.run_pipeline_with_tracking("job3", "educational",
                                     background="static_fire")

    assert recorder.background_arg == "static_fire"


def test_the_chosen_engine_reaches_the_renderer(recorder, ledger):
    admin.run_pipeline_with_tracking("job4", "educational", use_v2=True)

    assert recorder.render_kwargs.get("use_v2") is True


def test_v2_is_refused_for_the_types_it_cannot_render(recorder, ledger):
    """v2 only supports educational. Offering it for six types would be a
    control that silently does nothing — the failure this package corrects."""
    assert admin.v2_supported("educational")
    assert not admin.v2_supported("quiz")

    admin.run_pipeline_with_tracking("job5", "quiz", use_v2=True)

    assert recorder.render_kwargs.get("use_v2") is False


def test_dry_run_reaches_the_plan_without_paying_for_it(recorder, ledger):
    """The parameter existed and there was no way to reach it from the UI."""
    result = admin.run_pipeline_with_tracking("job6", "educational", dry_run=True)

    assert result["success"] and result["dry_run"]
    assert recorder.render_kwargs == {}, "a dry run rendered a video"


def test_the_controls_offer_only_values_the_engine_accepts():
    """Do not invent controls the engine does not have. Each list here is
    read from the same config the pipeline reads."""
    # `children` is deliberately NOT asserted here: it is declared in
    # config.yaml and cannot be resolved without a real voice id, so it is
    # offered only once that exists. See
    # test_only_profiles_that_actually_resolve_are_offered.
    assert "adults" in admin.available_profiles()

    backgrounds = admin.available_backgrounds()
    assert "static_midnight" in backgrounds
    # 'generated:*' is a wildcard in config.yaml, not a preset anyone can pick.
    assert not any("*" in b for b in backgrounds)


def test_start_generation_forwards_the_new_controls(ledger, monkeypatch):
    """The button hands these to start_generation, which is the only thing
    between the widget and the pipeline."""
    seen = {}

    def fake(job_id, video_type, category=None, topic_name=None, **kwargs):
        seen.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(admin, "run_pipeline_with_tracking", fake)
    admin.start_generation("educational", None, None,
                           profile_name="children", background="static_fire",
                           use_v2=True, dry_run=True)
    assert admin.wait_for_generations(timeout=10), "worker did not finish"

    assert seen == {"profile_name": "children", "background": "static_fire",
                    "use_v2": True, "dry_run": True}


def test_only_profiles_that_actually_resolve_are_offered(monkeypatch):
    """A SELECTBOX IN FRONT OF A BROKEN PATH IS WORSE THAN NO SELECTBOX.

    `children` is configured in config.yaml, has its own topic categories and
    its own audio settings — and cannot be resolved, because its voice_id is
    the literal "default", which audiences._validated_voice rejects. Offering
    it would raise InvalidAudienceProfile after the operator had already
    chosen a topic.

    So the list is what resolves, not what is declared. The moment a real
    CHILDREN_ELEVENLABS_VOICE_ID exists the profile appears on its own, with
    no code change — which is the door opening itself.
    """
    monkeypatch.delenv("CHILDREN_ELEVENLABS_VOICE_ID", raising=False)
    assert "children" not in admin.available_profiles()
    assert "children" in admin.unavailable_profiles()

    monkeypatch.setenv("CHILDREN_ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    assert "children" in admin.available_profiles()
    assert "children" not in admin.unavailable_profiles()


def test_an_unavailable_profile_says_why():
    """The operator has to be able to fix it. 'children unavailable' with no
    reason is the same dead end as no control at all."""
    reasons = admin.unavailable_profiles()

    assert "voice" in reasons.get("children", "").lower()


def _job_row(job_id):
    """The row for `job_id`, wherever the ledger has moved it to."""
    jobs = admin.load_jobs()
    return next(j for j in jobs["history"] + jobs["active"] if j["id"] == job_id)


def test_an_explicitly_chosen_background_is_recorded(recorder, ledger):
    """WHAT YOU PICKED MUST BE WHAT THE ROW SAYS YOU GOT.

    resolve_background's tier 1 returns an explicit instruction untouched and
    never calls on_record — that callback exists to describe FETCHED clips
    and GENERATED images. So the first video rendered with a pinned preset
    recorded `background: None`, and the dashboard could not show which
    background a hand-picked video had. A control whose effect is invisible
    is only half a door.
    """
    job_id = admin.create_job("vocabulary")
    admin.run_pipeline_with_tracking(job_id, "vocabulary",
                                     background="static_fire")

    row = _job_row(job_id)
    assert row["background"]["preset"] == "static_fire"
    assert row["background"]["kind"] == "preset"


def test_v2_does_not_pay_to_resolve_a_background_it_discards(recorder, ledger):
    """video/__init__.py sets `background = None` whenever v2 is active — v2
    renders its own. The first v2 video through this door fetched 25.4 MB of
    Pexels footage into output/clips/ and then threw it away. Free in dollars,
    but it is a download and a gate run for nothing, and it made the job row
    claim a background the video does not have.
    """
    admin.run_pipeline_with_tracking("jobv2", "educational", use_v2=True)

    assert recorder.background_arg == "UNSET", "v2 resolved a background anyway"

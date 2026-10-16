#!/usr/bin/env python3
"""One definition of which timing artefact each video type needs.

    python3 -m pytest tests/test_timing_contract.py

THE DEFECT THIS PINS. The rule was implemented twice. qa_gate.py stated it
per type; studio/media_validation.py re-implemented it as "words AND
segments must both be non-empty", for every type. Measured across the real
sidecars on disk, nothing satisfied both:

    quiz          13 samples   words 0..37   segments 0..20
    true_false    19 samples   words 0..24   segments 0..8
    vocabulary     7 samples   words 0..0    segments 7..8
    quiz_openai    1 sample    words 51      segments 0

vocabulary always failed on words; the OpenAI quiz path failed on segments.
Production was blocked for every type, which is why output/artifacts/ did
not exist until 2026-09-02 despite a month of green tests.

The fix was not a looser validator — that would have left two
implementations for the next person to choose wrongly between. There is now
one, in timing_contract, and these tests exist so a third cannot appear
quietly: they assert the two consumers share the SAME OBJECTS, not merely
equal ones.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import qa_gate  # noqa: E402
import timing_contract as contract  # noqa: E402
from studio import media_validation  # noqa: E402
from timing_contract import (  # noqa: E402
    KNOWN_TYPES, REQUIRES_SEGMENT_TIMES, REQUIRES_WORD_TIMELINE,
    UnknownVideoType, describe, required_timeline,
)


# ─────────────────── one definition, not two agreeing ones ───────────────────

@pytest.mark.parametrize("name", [
    "TURBO_TYPES", "V3_TYPES", "REQUIRES_SEGMENT_TIMES", "REQUIRES_WORD_TIMELINE",
])
def test_qa_gate_re_exports_the_same_object_not_a_copy(name):
    """`is`, not `==`. Two equal frozensets are exactly what the bug was:
    they can drift apart one edit at a time and stay passing until a type
    moves. Sharing the object makes drift impossible."""
    assert getattr(qa_gate, name) is getattr(contract, name)


def test_media_validation_consults_the_contract_rather_than_its_own_rule():
    """The validator must ask, not re-decide."""
    assert media_validation.required_timeline is required_timeline


def test_the_two_halves_do_not_overlap_and_cover_every_type():
    assert not (REQUIRES_SEGMENT_TIMES & REQUIRES_WORD_TIMELINE)
    assert REQUIRES_SEGMENT_TIMES | REQUIRES_WORD_TIMELINE == KNOWN_TYPES


def test_the_contract_matches_the_repos_declared_video_types():
    """If a seventh type is added, it must be given a timing requirement
    rather than silently inheriting one."""
    from script_schema import VIDEO_TYPES
    assert set(VIDEO_TYPES) == set(KNOWN_TYPES)


# ─────────────────────────── the rule itself ───────────────────────────

@pytest.mark.parametrize("video_type", ["quiz", "true_false", "fill_blank", "vocabulary"])
def test_segment_rendered_types_require_segments(video_type):
    assert required_timeline(video_type) == "segments"


@pytest.mark.parametrize("video_type", ["educational", "pronunciation"])
def test_word_rendered_types_require_words(video_type):
    assert required_timeline(video_type) == "words"


@pytest.mark.parametrize("video_type", ["banana", "", None, 7, "Quiz"])
def test_an_unknown_type_is_a_refusal_not_a_free_pass(video_type):
    """"neither -> REJECT". An unrecognised type is not a type with no
    requirements — defaulting is the mistake the second implementation made,
    just with a smaller blast radius."""
    with pytest.raises(UnknownVideoType):
        required_timeline(video_type)


def test_describe_states_the_rule_for_an_error_message():
    text = describe("quiz")
    assert "segments" in text and "words" in text


# ──────────────── the shapes that actually exist on disk ────────────────

def _probe(duration):
    return {"duration": duration, "audio_streams": 1}


def _meta(duration=2.0, words=None, segments=None):
    return {
        "duration": duration,
        "words": [] if words is None else words,
        "segments": [] if segments is None else segments,
    }


WORD = [{"word": "hola", "start": 0.0, "end": 0.5}]
SEG = [{"text": "hola", "start": 0.0, "end": 0.5}]


@pytest.mark.parametrize("video_type", ["quiz", "true_false", "fill_blank", "vocabulary"])
def test_a_segment_type_with_no_word_timeline_is_accepted(video_type):
    """The exact shape of every quiz/true_false/vocabulary sidecar on disk,
    and the exact shape that used to block production."""
    media_validation.validate_timing(_meta(segments=SEG), _probe(2.0), video_type)


def test_the_openai_quiz_shape_words_but_no_segments_is_still_refused():
    """A quiz WITH a word timeline and no segments is not saved by having
    words: the renderer drives off segment_times, and without it falls back
    to the /4 estimator at video/quiz.py:130 — inventing timing and
    presenting it as measured."""
    with pytest.raises(ValueError, match="non-empty 'segments'"):
        media_validation.validate_timing(_meta(words=WORD), _probe(2.0), "quiz")


@pytest.mark.parametrize("video_type", ["educational", "pronunciation"])
def test_a_word_type_with_no_segments_is_accepted(video_type):
    media_validation.validate_timing(_meta(words=WORD), _probe(2.0), video_type)


@pytest.mark.parametrize("video_type", ["educational", "pronunciation"])
def test_a_word_type_with_only_segments_is_refused(video_type):
    """Nothing would drive the karaoke."""
    with pytest.raises(ValueError, match="non-empty 'words'"):
        media_validation.validate_timing(_meta(segments=SEG), _probe(2.0), video_type)


def test_the_validator_will_not_run_without_a_type():
    """The signature makes the type mandatory, so no caller can reintroduce
    a global rule by omitting it."""
    with pytest.raises(TypeError):
        media_validation.validate_timing(_meta(segments=SEG), _probe(2.0))


# ─────────────── the real artifact this was diagnosed on ───────────────

REAL = ROOT / "output/artifacts/art_20260902_173159_7c953d19/audio/narration.json"


@pytest.mark.skipif(not REAL.exists(), reason="diagnostic artifact not present")
def test_the_artifact_that_exposed_the_bug_now_validates():
    """words: [], segments: 12 — blocked before, a valid quiz now."""
    import json
    metadata = json.loads(REAL.read_text(encoding="utf-8"))
    assert metadata["words"] == [] and len(metadata["segments"]) == 12
    media_validation.validate_timing(
        metadata, _probe(metadata["duration"]), "quiz")


# ───────────── the spend is recorded when production fails ─────────────
#
# Money is spent BEFORE the step that fails. The forced-failure run bought a
# script and a full 13-segment TTS, was blocked at the renderer, and recorded
# $0.0008 on its artifact against $0.0847 actually spent. The ledger fix put
# the money in output/costs/; these pin the other half, so the artifact an
# operator reads does not under-report a failed run.

class _Tracker:
    """The cost tracker's surface as the gateways use it: an append-only
    `entries` list and a save()."""

    def __init__(self):
        self.entries = []
        self.saves = 0

    def spend(self, amount, label):
        self.entries.append(
            {"api_type": "elevenlabs_tts", "cost_usd": amount, "label": label})

    def save(self):
        self.saves += 1


def _gateway(tracker, boom):
    """A LegacyProductionGateway whose _produce spends, then raises."""
    from studio.legacy_pipeline import LegacyProductionGateway

    gateway = LegacyProductionGateway.__new__(LegacyProductionGateway)
    gateway._get_tracker = lambda video_id=None: tracker

    def _produce(artifact, script, profile, progress, tracker_arg):
        tracker_arg.spend(0.0734, "tts_segment")
        raise boom

    gateway._produce = _produce
    return gateway


def test_production_failure_carries_the_spend_and_persists_the_ledger():
    from studio.editorial_costs import costs_of

    tracker = _Tracker()
    boom = RuntimeError("renderer refused")
    gateway = _gateway(tracker, boom)

    class _Artifact:
        artifact_id = "art_forced_failure"

    with pytest.raises(RuntimeError) as caught:
        gateway.produce(_Artifact(), {}, {}, lambda *a: None)

    assert caught.value is boom, (
        "the delegated stage's own exception must reach the caller "
        "unchanged — tests/studio/test_legacy_pipeline.py pins this, so the "
        "spend is attached to it rather than replacing it with a wrapper")
    assert [float(c.amount) for c in costs_of(boom)] == [0.0734]
    assert tracker.saves == 1, "the ledger is written on the failure path too"


def test_a_failure_that_refuses_attributes_does_not_mask_the_real_error():
    """Bookkeeping must never be the thing that takes a run down."""
    from studio.editorial_costs import costs_of

    class Sealed(RuntimeError):
        """Refuses annotation, the way some C-extension exceptions do.
        (A plain `__slots__` subclass does NOT: it inherits BaseException's
        __dict__ and accepts the attribute happily — checked, not assumed.)"""

        def __setattr__(self, name, value):
            raise AttributeError(name)

    tracker = _Tracker()
    boom = Sealed("renderer refused")

    class _Artifact:
        artifact_id = "art_slotted"

    with pytest.raises(Sealed) as caught:
        _gateway(tracker, boom).produce(_Artifact(), {}, {}, lambda *a: None)
    assert caught.value is boom
    assert costs_of(boom) == []
    assert tracker.saves == 1


def test_costs_land_on_the_artifact_before_the_failure_is_recorded(tmp_path):
    from studio.creation import CreationService
    from studio.models import ArtifactCost

    saved = []

    class Repo:
        def save(self, artifact):
            saved.append(artifact)

    service = CreationService.__new__(CreationService)
    service.repository = Repo()

    class Artifact:
        costs = []

        def model_copy(self, update=None):
            clone = Artifact()
            clone.costs = list((update or {}).get("costs", self.costs))
            return clone

    spent = [ArtifactCost(category="elevenlabs_tts", amount=0.0734, details={})]
    recorded = service._record_costs(Artifact(), spent)

    assert [float(c.amount) for c in recorded.costs] == [0.0734]
    assert saved and saved[-1] is recorded, (
        "spend is checkpointed in its own write, before the blocked_* "
        "transition — it is the part least reconstructable afterwards")
    assert service._record_costs(Artifact(), []) is not None


def test_both_halves_of_create_record_spend_before_recording_failure():
    """Editorial wraps (AuthorFailure); production annotates, because the
    gateway's exception identity is itself a pinned contract. Different
    mechanisms, one rule: the money is on the artifact either way."""
    import inspect

    from studio.creation import CreationService

    source = inspect.getsource(CreationService.create)
    assert source.count("self._record_costs(") == 2
    assert "costs_of(exc)" in source

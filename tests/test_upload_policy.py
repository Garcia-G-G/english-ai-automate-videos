#!/usr/bin/env python3
"""Unattended publication is refused, and the refusal is deliberate.

    python3 -m pytest tests/test_upload_policy.py

`--batch N --upload` used to publish. It no longer does, by decision: the
duplicate that put hPdSoqjvu3E on the channel twice came from a hand upload
against a queue that did not know the video was already live, and an
unattended loop is that same mistake on a timer.

The risk with a policy expressed as one `if` in one function is that the
next person to rewire the CLI removes it without noticing they made a
decision. These tests make the brake something you have to delete on
purpose. They assert the CURRENT policy — if the owner lifts it, they
should fail, and that failure is the reminder to lift it deliberately.
"""

import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import main  # noqa: E402


def test_the_refusal_names_the_artifact_so_it_can_be_found(capsys):
    message = main.refuse_unattended_upload("quiz_20260901_120000")
    out = capsys.readouterr().out
    assert "refused" in message.lower()
    assert "quiz_20260901_120000" in message
    assert message in out, "the operator must see it, not only the log"


def test_the_refusal_reaches_the_run_log(caplog):
    """After an unattended batch the log is what gets read, not the tty."""
    with caplog.at_level(logging.WARNING, logger="main"):
        main.refuse_unattended_upload("artifact_a")
    assert any("refused" in r.message.lower() for r in caplog.records)


def test_run_creation_refuses_instead_of_publishing(monkeypatch, tmp_path):
    """The whole point: upload=True renders, and publishes nothing."""
    published = []

    def explode(*a, **kw):                       # pragma: no cover
        published.append(a)
        raise AssertionError("upload_video was reached from an unattended path")

    monkeypatch.setattr(main, "upload_video", explode)

    class _Artifact:
        artifact_id = "artifact_under_test"
        # run_creation now inspects the state before it considers uploading:
        # a blocked artifact is a failed run and must never reach the upload
        # decision at all. A successful one still must be refused.
        state = "ready_for_review"
        error = None
        class paths:
            video = None

    class _Service:
        def create(self, request, **kw):
            return _Artifact()

    monkeypatch.setattr(main, "get_creation_service", lambda **kw: _Service())

    refusals = []
    monkeypatch.setattr(main, "refuse_unattended_upload",
                        lambda aid=None: refusals.append(aid))

    artifact, _ = main.run_creation(
        workspace="youtube", audience="adults", idea="phrasal verbs",
        mode="auto", root=tmp_path, upload=True,
    )
    assert artifact.artifact_id == "artifact_under_test"
    assert refusals == ["artifact_under_test"], "the refusal did not fire"
    assert published == []


def test_without_upload_nothing_is_refused_and_nothing_is_published(
        monkeypatch, tmp_path):
    class _Artifact:
        artifact_id = "quiet"
        state = "ready_for_review"
        error = None
        class paths:
            video = None

    class _Service:
        def create(self, request, **kw):
            return _Artifact()

    monkeypatch.setattr(main, "get_creation_service", lambda **kw: _Service())
    refusals = []
    monkeypatch.setattr(main, "refuse_unattended_upload",
                        lambda aid=None: refusals.append(aid))

    main.run_creation(workspace="youtube", audience="adults", idea="x",
                      mode="auto", root=tmp_path, upload=False)
    assert refusals == []


def test_no_unattended_path_reaches_the_publisher():
    """`upload_video` still exists and still holds the guard, the ledger
    write and the metadata resolution — it is kept for the approved path,
    not deleted. What must stay true is that run_creation never calls it."""
    import inspect
    source = inspect.getsource(main.run_creation)
    assert "upload_video" not in source


def test_the_flag_does_not_advertise_publishing():
    """A flag whose help says "Upload video to configured platforms" while
    refusing to do so reads as a bug, and the operator's fix for a bug is to
    publish by hand."""
    parser_src = inspect_main_parser()
    assert "REFUSED" in parser_src


def inspect_main_parser() -> str:
    import inspect
    return inspect.getsource(main.main)


def test_a_blocked_artifact_is_never_offered_for_upload(monkeypatch, tmp_path):
    """A run that produced no video must not reach the upload decision — the
    refusal is about publishing a finished video, not about consoling a
    failed render."""
    class _Blocked:
        artifact_id = "blocked_one"
        state = "blocked_production"
        error = "ValueError: boom"
        class paths:
            video = None

    class _Service:
        def create(self, request, **kw):
            return _Blocked()

    monkeypatch.setattr(main, "get_creation_service", lambda **kw: _Service())
    refusals = []
    monkeypatch.setattr(main, "refuse_unattended_upload",
                        lambda aid=None: refusals.append(aid))

    artifact, video = main.run_creation(
        workspace="youtube", audience="adults", idea="x", mode="auto",
        root=tmp_path, upload=True,
    )
    assert video is None
    assert refusals == [], "a failed render must not print an upload refusal"
    assert main.creation_failure(artifact) == "ValueError: boom"

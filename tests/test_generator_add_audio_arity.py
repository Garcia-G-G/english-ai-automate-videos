#!/usr/bin/env python3
"""Guard the add_audio contract across every generator.

    python3 -m pytest tests/test_generator_add_audio_arity.py

`add_audio` is defined as a CLOSURE, once per generator function — four times
in tts_elevenlabs.py, four in tts_openai.py, one in tts_google.py. Nine copies
of the same six lines.

That duplication bit twice in one session. Widening the return from
(start, file_end, duration) to (..., speech_end) matched only ONE definition
per file, so quiz worked while fill_blank, true_false and vocabulary raised
`ValueError: not enough values to unpack` on the first real generation. The
full test suite stayed green throughout, because no test calls these paths —
they all need the ElevenLabs API.

This test needs no API. It parses the source and checks the contract holds at
every definition and every call site, which is exactly the check that was
missing.

The real fix is to stop having nine copies. Recorded in docs/recorded-debt.md;
until then, this guard.
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GENERATORS = ["src/tts_elevenlabs.py", "src/tts_openai.py", "src/tts_google.py"]

EXPECTED_ARITY = 4  # start, file_end, duration, speech_end


def _tree(rel):
    return ast.parse((ROOT / rel).read_text(encoding="utf-8"))


def _add_audio_defs(tree):
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "add_audio"]


@pytest.mark.parametrize("rel", GENERATORS)
def test_every_add_audio_returns_the_full_tuple(rel):
    defs = _add_audio_defs(_tree(rel))
    assert defs, f"{rel}: no add_audio definition found"

    for fn in defs:
        returns = [n for n in ast.walk(fn)
                   if isinstance(n, ast.Return) and n.value is not None]
        assert returns, f"{rel}:{fn.lineno} add_audio returns nothing"
        for r in returns:
            assert isinstance(r.value, ast.Tuple), (
                f"{rel}:{r.lineno} add_audio must return a tuple")
            assert len(r.value.elts) == EXPECTED_ARITY, (
                f"{rel}:{r.lineno} add_audio returns "
                f"{len(r.value.elts)} values, expected {EXPECTED_ARITY}. "
                "A definition was missed — there are several per file.")


@pytest.mark.parametrize("rel", GENERATORS)
def test_every_unpack_site_matches_the_arity(rel):
    """`a, b, _ = add_audio(...)` against a 4-tuple raises at RUN time, deep
    inside a paid API call. Catch it here instead."""
    tree = _tree(rel)
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "add_audio"):
            continue
        for target in node.targets:
            if isinstance(target, ast.Tuple) and len(target.elts) != EXPECTED_ARITY:
                bad.append(f"{rel}:{node.lineno} unpacks {len(target.elts)}")
    assert not bad, "arity mismatch at:\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("rel", GENERATORS)
def test_speech_end_is_actually_measured_not_aliased(rel):
    """The 4th value must come from measure_speech_end. Returning
    `running_time` again would satisfy the arity checks above while restoring
    exactly the bug scope item (b) removed."""
    src = (ROOT / rel).read_text(encoding="utf-8")
    n_defs = len(_add_audio_defs(_tree(rel)))

    assert src.count("measure_speech_end(path)") >= n_defs, (
        f"{rel}: {n_defs} add_audio definitions but fewer calls to "
        "measure_speech_end — one is aliasing the file end again")


#: Segment ends that legitimately are NOT a measured speech end.
#: `cd_end` bounds a countdown, which is spliced anullsrc with no audio file
#: and therefore no speech to measure — its end IS its silence end. Every
#: other segment wraps a real clip and must use the measured value.
_NON_SPEECH_ENDS = {"cd_end"}


def test_segments_are_recorded_against_speech_end_not_file_end():
    """Any add_segment whose end argument is a bare `*_end` name is using the
    FILE end. It must use the `*_end_speech` measured value.

    This caught two real misses that the arity checks above could not: the
    `answer` segment in all three generators called add_audio() bare and then
    read `running_time`, so it recorded the file end and kept the exact defect
    scope item (b) was meant to remove.
    """
    offenders = []
    for rel in GENERATORS:
        tree = _tree(rel)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "add_segment"):
                continue
            if len(node.args) < 4:
                continue
            end = node.args[3]
            if (isinstance(end, ast.Name) and end.id.endswith("_end")
                    and end.id not in _NON_SPEECH_ENDS):
                offenders.append(f"{rel}:{node.lineno} end={end.id}")
    assert not offenders, (
        "segment end taken from the FILE end instead of measured speech end:\n  "
        + "\n  ".join(offenders))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

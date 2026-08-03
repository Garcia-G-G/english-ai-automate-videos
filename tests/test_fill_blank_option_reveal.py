#!/usr/bin/env python3
"""fill_blank option cards appear when their option is SPOKEN.

    python3 -m pytest tests/test_fill_blank_option_reveal.py

_OPT_STAGGER = 0.10 put all four cards on screen within 0.4 s while the
narration took ~11 s to read them, so the screen was static for the rest of
the block. Retention on two published fill_blanks decays across exactly that
window (_audit/RETENTION_BASELINE.md).

The stagger constant is NOT tuned. It is replaced by measured speech
boundaries, and kept only as the fallback when those boundaries are absent.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video.fill_blank import _OPT_STAGGER, option_reveal_times  # noqa: E402


def _st(starts):
    return {f"option_{i + 1}": {"start": s, "end": s + 1.5}
            for i, s in enumerate(starts)}


# ── measured ─────────────────────────────────────────────────────────

def test_reveal_follows_the_measured_boundaries():
    times, measured = option_reveal_times(_st([6.3, 9.0, 12.2, 17.0]), 5.0)

    assert measured is True
    assert times == [6.3, 9.0, 12.2, 17.0]


def test_the_reveal_now_spans_the_whole_block_not_04_seconds():
    """The point of the change: the screen keeps changing while the narration
    reads, instead of freezing 0.4 s in."""
    times, _ = option_reveal_times(_st([6.3, 9.0, 12.2, 17.0]), 5.0)
    span = max(times) - min(times)

    assert span > 5.0, f"cards still bunched into {span:.2f}s"
    assert span > 4 * _OPT_STAGGER * 10


# ── fallback, not guesswork ──────────────────────────────────────────

def test_missing_boundaries_fall_back_to_the_constant_stagger():
    """An older artifact has no per-option segments. Fall back rather than
    invent a schedule."""
    times, measured = option_reveal_times({}, 5.0)

    assert measured is False
    assert times == [5.0, 5.1, 5.2, 5.3]


def test_a_partial_set_falls_back_entirely():
    """All or nothing. A half-measured schedule — two real boundaries and two
    invented ones — would be worse than a consistent approximation."""
    partial = _st([6.3, 9.0])          # only 2 of 4

    times, measured = option_reveal_times(partial, 5.0)

    assert measured is False
    assert times == [5.0, 5.1, 5.2, 5.3]


def test_out_of_order_boundaries_fall_back():
    """Cards must never reveal in the wrong sequence; if the data says they
    would, the data is not trustworthy."""
    times, measured = option_reveal_times(_st([6.3, 5.0, 12.2, 17.0]), 5.0)

    assert measured is False


def test_the_fallback_is_the_original_behaviour_unchanged():
    """So a fallback render looks exactly like it did before this change."""
    times, _ = option_reveal_times({}, 4.2)

    assert times == [4.2 + i * _OPT_STAGGER for i in range(4)]


# ── the generator contract ───────────────────────────────────────────

def test_fill_blank_emits_per_option_segments():
    """The reveal depends on them, and before this change fill_blank emitted
    only a single whole-block `options` segment — which is why the QA gate's
    letter-to-word check skipped all 24 fill_blank artifacts in the baseline
    as 'fewer than 2 per-option segment_times'."""
    src = (ROOT / "src" / "tts_elevenlabs.py").read_text(encoding="utf-8")

    assert 'seg_ids=opt_seg_ids' in src
    assert 'f"option_{i + 1}"' in src


def test_the_whole_block_options_segment_is_still_emitted():
    """The renderer and the QA gate both read it; the per-option spans are
    additive, not a rename."""
    src = (ROOT / "src" / "tts_elevenlabs.py").read_text(encoding="utf-8")

    assert "add_segment('options'," in src


def test_quiz_and_fill_blank_share_one_split_implementation():
    """Reuse, not a fork. They differ only in labels and transition text."""
    import ast
    tree = ast.parse((ROOT / "src" / "tts_elevenlabs.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "emit_split_options"]

    assert len(calls) == 2, f"expected quiz + fill_blank, found {len(calls)}"
    defs = [n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "emit_split_options"]
    assert len(defs) == 1, "the split has been forked into a second implementation"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

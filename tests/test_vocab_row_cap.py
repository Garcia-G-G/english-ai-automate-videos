#!/usr/bin/env python3
"""A vocabulary deck longer than the card can hold must be refused.

    python3 -m pytest tests/test_vocab_row_cap.py

config/layout.py has declared VOCAB_MAX_ROWS = 12 since the file was written
and nothing enforced it. The 6-10 window in VocabularyScript.lint() looks
like it covers this, but validate_render_data never calls lint() and neither
does anything else outside script_schema — the same shape of defect as
finalize_video, unrecorded_platforms and the dead layout constants: a check
that exists and nothing invokes.

It is not cosmetic. _draw_vocab_rows steps rows at VOCAB_ROW_HEIGHT with no
clamp while only the CARD is clamped, so past a certain count the rows walk
out of their own card and keep going:

    14 rows  last row bottom y=1610   inside the safe band
    15 rows                    1700   past SAFE_AREA_BOTTOM (1632)
    18 rows                    1970   past the bottom of a 1920px frame

The generator is asked for 6-10, so this fires when the model overshoots by
five — unattended, twice a day.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from config.layout import (  # noqa: E402
    BAR_Y, CARD_PADDING, SAFE_AREA_BOTTOM, VIDEO_HEIGHT,
    VOCAB_MAX_ROWS, VOCAB_ROW_HEIGHT,
)
from script_schema import ScriptValidationError, validate_render_data  # noqa: E402

_HEADER_H = 70          # vocabulary._HEADER_H
_CARD_TOP_MIN = 260     # vocabulary._CARD_TOP_MIN


def _deck(n: int) -> dict:
    return {
        "type": "vocabulary",
        "full_script": "Vocabulario de hoy, presta atencion a la pronunciacion.",
        "title": "Vocabulario: Pull vs Pool",
        "pairs": [{"spanish": f"palabra {i}", "english": f"word {i}"}
                  for i in range(n)],
        "hashtags": ["#ingles", "#learnenglish", "#vocabulario",
                     "#idiomas", "#english"],
        "duration": 30.0,
    }


def _last_row_bottom(n: int) -> int:
    """Where _draw_vocab_rows would put the bottom of row n."""
    first_row_y = _CARD_TOP_MIN + CARD_PADDING // 2 + _HEADER_H
    return first_row_y + (n - 1) * VOCAB_ROW_HEIGHT + VOCAB_ROW_HEIGHT


def test_the_overflow_this_cap_exists_to_prevent_is_real():
    """The geometry, so the cap is not a number defended by nothing."""
    assert _last_row_bottom(VOCAB_MAX_ROWS) <= SAFE_AREA_BOTTOM, (
        "VOCAB_MAX_ROWS itself should fit inside the safe band")
    assert _last_row_bottom(15) > SAFE_AREA_BOTTOM, (
        "15 rows should cross SAFE_AREA_BOTTOM")
    assert _last_row_bottom(18) > VIDEO_HEIGHT, (
        "18 rows should leave the frame")


@pytest.mark.parametrize("n", [6, 10, VOCAB_MAX_ROWS])
def test_decks_within_the_cap_validate(n):
    model = validate_render_data(_deck(n), "vocabulary")
    assert len(model.pairs) == n


@pytest.mark.parametrize("n", [VOCAB_MAX_ROWS + 1, 15, 18])
def test_decks_over_the_cap_are_refused(n):
    """Fails before the cap is enforced: these validate and then overflow."""
    with pytest.raises(ScriptValidationError) as exc:
        validate_render_data(_deck(n), "vocabulary")
    assert "pairs" in str(exc.value)


def test_the_cap_is_refused_before_any_rendering_happens():
    """It must fail in validation, not by drawing off the bottom of a frame.

    validate_render_data is what generate_video calls before the first frame,
    so a deck refused here costs nothing. A deck caught later would already
    have paid for TTS.
    """
    with pytest.raises(ScriptValidationError):
        validate_render_data(_deck(15), "vocabulary")
    # And the clamp that does exist protects only the card, never the rows.
    card_h = _HEADER_H + 15 * VOCAB_ROW_HEIGHT + CARD_PADDING * 2
    assert card_h > BAR_Y - _CARD_TOP_MIN - 30 or _last_row_bottom(15) > SAFE_AREA_BOTTOM

#!/usr/bin/env python3
"""Pin the english_phrases scraper in validate_and_clean_script.

    python3 -m pytest tests/test_english_phrases_scraper.py

english_phrases is not decoration: it drives is_english, which drives BOTH
the on-screen word styling and the TTS accent. A Spanish span listed here is
spoken in an English accent — the same failure class as the 'tela' defect
recorded in tests/fixtures/known_bad/manifest.json.

Two bugs fed it, and the first is the serious one:

  a) APOSTROPHE DESYNC. `re.findall(r"'([^']+)'", full_script)` pairs
     apostrophes positionally. The first contraction consumes one delimiter
     and shifts every subsequent pair, so the regex starts capturing the
     Spanish narration BETWEEN the intended phrases.

  b) A guard of `any(len(w) > 1 ...)` admits any span containing one
     two-letter word, so "me gusta tu outfit" was filed as English.

Measured over the 172-script historical corpus, the old scraper appended 854
spans; the fixed one appends 727, dropping 127 — 184 distinct artefacts.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from script_generator import validate_and_clean_script  # noqa: E402


#: validate_and_clean_script early-returns when a required field is empty, so
#: english_phrases must be seeded non-empty for the scraper to run at all.
#: See docs/schema-prompt-mismatches.md M11.
SEED = "placeholder"


def scrape(full_script, seed=None):
    """Run the cleaner and return the resulting english_phrases, lowercased."""
    script = {
        "type": "educational",
        "full_script": full_script,
        "english_phrases": list(seed or [SEED]),
        "hook": "hook",
        "hashtags": ["#a"],
    }
    out = validate_and_clean_script(script, "educational")
    return [p.lower() for p in out.get("english_phrases", [])]


# ── (a) the apostrophe desync ────────────────────────────────────────

def test_contraction_does_not_desynchronise_the_quote_pairing():
    """The reported case. A contraction inside a quoted phrase used to split
    it into 'i can' + 'm swamped with deadlines'."""
    got = scrape(
        "Hoy aprendemos 'I can't be swamped with deadlines' que significa "
        "estar hasta el cuello."
    )

    assert "i can't be swamped with deadlines" in got
    assert "i can" not in got
    assert "m swamped with deadlines" not in got


def test_narration_between_phrases_is_never_captured():
    """After a desync the regex captured the Spanish gap text itself."""
    got = scrape(
        "Usamos 'It's raining', que significa que llueve. También "
        "'Let's go', que se traduce como vamos."
    )

    assert "it's raining" in got
    assert "let's go" in got
    for artefact in (", que significa ", ", que se traduce como "):
        assert artefact not in got
        assert artefact.strip() not in got


# ── (b) the Spanish guard ────────────────────────────────────────────

#: Typographic quotes, as gpt-4o-mini actually emits them. Written as \u
#: escapes so the fixture cannot be silently normalised to ASCII by an editor
#: — which is exactly how the original `.replace("'", "'")` no-op was born.
SMART_L, SMART_R = "\u2018", "\u2019"      # left/right single quote
SMART_LD, SMART_RD = "\u201c", "\u201d"    # left/right double quote


def test_typographic_apostrophes_are_normalised_before_pairing():
    """script_generator.py:642 used to be an ASCII-to-ASCII no-op, so a U+2019
    inside a contraction reached the pairing untouched and desynchronised it
    exactly like an ASCII apostrophe would."""
    full = (f"Hoy vemos {SMART_L}I can{SMART_R}t go to lunch{SMART_R} "
            f"que significa que no puedo ir.")
    got = scrape(full)

    assert "i can't go to lunch" in got, got
    assert "i can" not in got
    assert "t go to lunch" not in got


def test_typographic_double_quotes_are_normalised():
    """The second normalisation line was `.replace(\"\"\", '\"')`, which Python
    read as a triple-quoted string — so U+201C/U+201D were never converted."""
    script = {
        "type": "educational",
        "full_script": f"El profesor dijo {SMART_LD}hello{SMART_RD} a la clase.",
        "english_phrases": [SEED],
        "hook": "hook",
        "hashtags": ["#a"],
    }
    out = validate_and_clean_script(script, "educational")

    assert SMART_LD not in out["full_script"]
    assert SMART_RD not in out["full_script"]
    assert '"hello"' in out["full_script"]


def test_no_typographic_quote_survives_into_the_cleaned_script():
    """Whatever the mix, nothing typographic reaches TTS or the renderer."""
    full = (f"{SMART_L}It{SMART_R}s fine{SMART_R}, dijo, y luego "
            f"{SMART_LD}really{SMART_RD}.")
    out = validate_and_clean_script({
        "type": "educational", "full_script": full,
        "english_phrases": [SEED], "hook": "h", "hashtags": ["#a"],
    }, "educational")

    for ch in (SMART_L, SMART_R, SMART_LD, SMART_RD):
        assert ch not in out["full_script"], f"{ch!r} survived"


#: Both spans below are rejected only when the stoplist actually contains
#: their tokens. Until the five forked stoplists were unified, the 113-word
#: tts_common.SPANISH_FILTER lacked 'gusta'/'tu'/'increible' and these two
#: were xfail(strict=True). The canonical 275-word set made them pass, which
#: is exactly the behaviour change that unification bought.


def test_spanish_span_with_one_loanword_is_rejected():
    """A single English loanword must not drag a Spanish sentence into an
    English accent. Requires the unified stoplist to catch every token."""
    got = scrape("Un ejemplo es 'me gusta tu outfit' en redes sociales.")

    assert "me gusta tu outfit" not in got


def test_entirely_spanish_span_is_rejected():
    got = scrape("Puedes decir 'qué increíble' cuando algo te sorprende.")

    assert "qué increíble" not in got


def test_english_lesson_phrases_are_retained():
    """The deliberately-WRONG English phrases are the whole point of the
    lesson. A tie between Spanish and English tokens must resolve to English,
    because 'me' is a word in both languages."""
    got = scrape(
        "El error es 'explain me' y lo correcto es 'explain to me'. "
        "También 'tell me' y 'depend of' y 'listen music'."
    )

    for phrase in ("explain me", "explain to me", "tell me",
                   "depend of", "listen music"):
        assert phrase in got, f"lost the lesson phrase {phrase!r}"


def test_seeded_phrases_survive_and_are_not_duplicated():
    got = scrape("Decimos 'work out' todos los días.", seed=["work out"])

    assert got.count("work out") == 1


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))

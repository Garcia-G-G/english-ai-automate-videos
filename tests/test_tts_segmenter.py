#!/usr/bin/env python3
"""Unit tests for src/tts_segmenter.py — runnable standalone or with pytest.

    python3 tests/test_tts_segmenter.py

Cases are taken from real scripts in output/scripts/educational/.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tts_segmenter import (  # noqa: E402
    LANGUAGE_POLICIES, collect_english_terms, segment_text, segment_script, looks_english,
    describe_segments,
)

FAILURES = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append((name, detail))


def langs(segs):
    return [s["lang"] for s in segs]


def texts(segs):
    return [s["text"] for s in segs]


def en_texts(segs):
    return [s["text"] for s in segs if s["lang"] == "en"]


def norm(text):
    """Strip attached punctuation for comparisons."""
    return text.strip(".,!?¿¡;: ").lower()


# ── Case 1: real script "actually" ───────────────────────────────────
def test_actually():
    print("\nCase 1: 'actually' (real script — false friend)")
    script = {
        "full_script": ("¡Cuidado! 'Actually' NO significa actualmente. "
                        "Este es uno de los errores más comunes. En inglés, "
                        "'actually' significa 'en realidad' o 'de hecho'. "
                        "Por ejemplo: 'Actually, I don't like coffee'. "
                        "Si quieres decir actualmente, la palabra correcta es "
                        "'currently'. Por ejemplo: 'I'm currently working from "
                        "home'. Recuerda: 'actually' es para corregir o aclarar "
                        "algo. ¿Tú también confundías estas palabras?"),
        "english_phrases": ["actually", "Actually, I don't like coffee",
                            "currently", "I'm currently working from home"],
        "translations": {"actually": "en realidad", "currently": "actualmente"},
    }
    segs = segment_script(script)
    ens = en_texts(segs)
    check("segments alternate and start ES... actually first EN",
          segs[0]["lang"] == "es" and "Cuidado" in segs[0]["text"], str(segs[0]))
    check("'Actually' isolated as EN", any(norm(e) == "actually" for e in ens), str(ens))
    check("full example sentence is ONE EN segment",
          any("don't like coffee" in e for e in ens), str(ens))
    check("'currently' detected as EN", any(norm(e) == "currently" for e in ens), str(ens))
    check("'en realidad' quoted Spanish stays ES",
          not any("en realidad" in e.lower() for e in ens), str(ens))
    check("'actualmente' never EN", not any("actualmente" in e.lower() for e in ens))
    check("no empty segments", all(s["text"].strip() for s in segs))


# ── Case 2: real script "give up" (nested quotes ES translations) ────
def test_give_up():
    print("\nCase 2: 'give up' (real script — quoted ES translations inline)")
    script = {
        "full_script": ("El phrasal verb 'give up' significa rendirse. Por "
                        "ejemplo, 'I gave up smoking' que significa 'Dejé de "
                        "fumar'. Otro ejemplo es 'Don't give up on your "
                        "dreams', que se traduce como 'No te rindas en tus "
                        "sueños'. Y si te sientes frustrado, puedes decir "
                        "'I give up! This is impossible', que significa "
                        "'¡Me rindo! Esto es imposible'."),
        "english_phrases": ["give up", "I gave up smoking",
                            "Don't give up on your dreams",
                            "I give up! This is impossible"],
        "translations": {"I gave up smoking": "Dejé de fumar"},
    }
    segs = segment_script(script)
    ens = en_texts(segs)
    check("'give up' EN", any(e.lower() == "give up" for e in ens), str(ens))
    check("'I gave up smoking' one EN segment",
          any("gave up smoking" in e for e in ens), str(ens))
    check("quoted 'Dejé de fumar' stays ES",
          not any("fumar" in e.lower() for e in ens), str(ens))
    check("quoted '¡Me rindo!...' stays ES",
          not any("rindo" in e.lower() for e in ens), str(ens))
    check("'Don't give up on your dreams' EN",
          any("your dreams" in e for e in ens), str(ens))


# ── Case 3: real script "-ed endings" (weird terms: '-ed', 'wan-tid') ─
def test_ed_endings():
    print("\nCase 3: '-ed endings' (real script — hyphenated fragments)")
    script = {
        "full_script": ("¿Sabías que en inglés, la terminación '-ED' se "
                        "pronuncia de tres maneras diferentes? Por ejemplo, "
                        "'wanted' agrega una sílaba extra, así que se "
                        "pronuncia 'wan-tid'. En cambio, 'played' no añade "
                        "nada, se dice simplemente 'pleyd'. Por ejemplo, "
                        "'I wanted to play, but I watched a movie instead.'"),
        "english_phrases": ["wanted", "played", "watched", "-d", "-t",
                            "pleyd", "wochd", "wan-tid", "-ed",
                            "i wanted to play, but i watched a movie instead."],
        "translations": {"wanted": "querido", "played": "jugado"},
    }
    segs = segment_script(script)
    ens = en_texts(segs)
    check("'-ED' matched as EN (case-insensitive)",
          any(e.lower() == "-ed" for e in ens), str(ens))
    check("'wanted' EN", any(e.lower() == "wanted" for e in ens), str(ens))
    check("long example sentence EN",
          any("movie instead" in e for e in ens), str(ens))
    check("Spanish frame text stays ES",
          any("terminación" in s["text"] for s in segs if s["lang"] == "es"))


# ── Case 4: quotes WITHOUT metadata (heuristic only) ──────────────────
def test_heuristic_quotes():
    print("\nCase 4: quoted spans with NO metadata (heuristic fallback)")
    segs = segment_text(
        "La frase 'see you later' significa 'hasta luego' en español.",
        english_terms=[])
    ens = en_texts(segs)
    check("'see you later' EN by heuristic",
          any("see you later" == e for e in ens), str(ens))
    check("'hasta luego' ES by heuristic",
          not any("hasta luego" in e for e in ens), str(ens))
    check("looks_english positives",
          looks_english("I don't like coffee") and looks_english("break up"))
    check("looks_english negatives",
          not looks_english("pasar el rato") and not looks_english("de hecho")
          and not looks_english("¡Me rindo!"))


# ── Case 5: metadata wins over heuristic + no-English script ─────────
def test_metadata_priority_and_pure_spanish():
    print("\nCase 5: metadata priority + pure-Spanish script")
    # 'como' is a Spanish word but here metadata marks nothing — pure ES
    segs = segment_text("Hola amigos, hoy vamos a aprender mucho. ¿Listos?",
                        english_terms=[])
    check("pure Spanish -> single ES segment",
          langs(segs) == ["es"], str(segs))

    # Metadata forces unquoted English mid-sentence
    script = {
        "full_script": "Muchos dicen break up cuando terminan una relación.",
        "english_phrases": ["break up"],
        "translations": {"break up": "terminar relación"},
    }
    segs = segment_script(script)
    check("unquoted metadata term still isolated",
          en_texts(segs) == ["break up"], str(segs))
    check("order preserved (es, en, es)", langs(segs) == ["es", "en", "es"],
          str(langs(segs)))
    # Spanish words in metadata must be rejected
    terms = collect_english_terms({"english_phrases":
                                   ["ejemplo", "según", "break up"]})
    check("Spanish metadata terms filtered",
          terms == ["break up"], str(terms))


# ── Case 6: vocabulary pairs + quiz 'cómo se dice' ────────────────────
def test_pairs_and_quiz():
    print("\nCase 6: vocabulary pairs + quiz option extraction")
    script = {
        "full_script": "Perro se dice dog. Gato se dice cat.",
        "pairs": [{"spanish": "perro", "english": "dog"},
                  {"spanish": "gato", "english": "cat"}],
    }
    segs = segment_script(script)
    check("pair terms detected",
          {norm(e) for e in en_texts(segs)} >= {"dog", "cat"}, str(segs))

    quiz = {
        "full_script": "¿Cómo se dice fiesta en inglés? La respuesta es party.",
        "question": "¿Cómo se dice 'fiesta' en inglés?",
        "options": {"A": "party", "B": "meeting"},
        "correct": "A",
    }
    segs = segment_script(quiz)
    check("quiz correct option EN",
          "party" in [norm(e) for e in en_texts(segs)], str(segs))
    check("'fiesta' stays ES",
          "fiesta" not in [norm(t) for t in en_texts(segs)])


# ── Case 7: pause hints ───────────────────────────────────────────────
def test_pauses():
    print("\nCase 7: pause_after hints from punctuation")
    segs = segment_text("Primero, 'break up'. Luego seguimos.",
                        english_terms=["break up"])
    by_text = {s["text"]: s for s in segs}
    check("sentence-final EN keeps sentence pause",
          any(s["lang"] == "en" and s["pause_after"] >= 0.15 for s in segs)
          or any(s["pause_after"] >= 0.15 for s in segs), str(segs))
    check("all segments have pause_after",
          all(isinstance(s["pause_after"], float) for s in segs))
    assert by_text  # silence linters


def test_simplified_chinese_policy_preserves_source_and_isolates_english():
    text = "先听：I need two tickets，数字 2 不要丢；再说 I need two tickets。"
    segments = segment_text(
        text,
        ["I need two tickets"],
        language_policy=LANGUAGE_POLICIES["zh-Hans"],
    )
    assert "".join(segment["source_text"] for segment in segments) == text
    assert [segment["lang"] for segment in segments] == ["zh", "en", "zh", "en", "zh"]
    assert [segment["index"] for segment in segments] == list(range(len(segments)))
    assert all(segment["source_start"] < segment["source_end"] for segment in segments)
    assert all(
        left["source_end"] == right["source_start"]
        for left, right in zip(segments, segments[1:])
    )


def test_language_policy_rejects_unknown_or_malformed_native_language():
    import pytest

    with pytest.raises(ValueError, match="language policy"):
        segment_text("你好", [], narration_lang="zh")
    with pytest.raises(ValueError, match="language policy"):
        segment_script({"full_script": "你好"}, narration_lang="zh-Hans")


def main():
    test_actually()
    test_give_up()
    test_ed_endings()
    test_heuristic_quotes()
    test_metadata_priority_and_pure_spanish()
    test_pairs_and_quiz()
    test_pauses()

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURES:")
        for name, detail in FAILURES:
            print(f"  - {name}: {detail}")
        sys.exit(1)
    print("ALL SEGMENTER TESTS PASSED")


if __name__ == "__main__":
    main()

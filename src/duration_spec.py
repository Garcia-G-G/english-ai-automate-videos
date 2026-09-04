#!/usr/bin/env python3
"""Duration as a specification: the band, the word target, and the verdict.

    from duration_spec import word_target, project, check
    word_target("quiz")              -> 107   words to aim the generator at
    project("quiz", narration=41.2)  -> 45.2  seconds of finished video
    check("quiz", narration=41.2)    -> a verdict dict, PASS or OUT_OF_BAND

WHY THIS EXISTS. Nothing in the pipeline aimed at a duration. The length of
a video was whatever the script model happened to write plus whatever fixed
structure its type adds, and 27 of 138 measured videos — 20% — landed in
the 50-80 s band. The duration was an outcome; here it becomes the input.

THE MODEL, and every term in it is measured rather than assumed:

    video = speech + declared_silence + outro
    overhead     = declared_silence + outro
    target_words = (target_seconds - overhead) x rate

WHAT MADE THE OLD ARITHMETIC WRONG. Overheads had been computed from
UNPAIRED sets — one group of artifacts' audio duration against a different
group's video duration. Recomputed per artifact, where the mp3 and the mp4
are the same video, educational's overhead came out at 9.5 s against an
earlier estimate of ~20.8 s. Every word target built on the old figure
would have been about 25 words short.

TWO TRAPS WORTH RESTATING HERE, because both are easy to reintroduce:

  1. `rate` counts words of SPEECH per second of SPEECH, from the
     narration's `segments`. NOT from `full_script`: on quiz, full_script
     carries 140 words where the segments carry 53, because full_script is
     a fuller narrative than the one that is actually synthesised. Aiming a
     word target at full_script would be aiming at nothing.

  2. `silence` is declared silence INSIDE the narration — countdowns,
     think-pauses, the gaps between repeats. It is part of the narration
     duration, so it never shows up in video-minus-narration, which is
     exactly why it went unnoticed.

WHY THE CHECK RUNS AFTER TTS AND NOT BEFORE IT. Language models do not hit
word counts precisely. The word target is a LEVER, not the specification;
the specification is the duration. So the generator is aimed with words and
the result is judged in seconds, against the real synthesised narration.
Checking the script's word count before synthesis would be measuring the
lever instead of the thing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

#: Verdicts, in the same vocabulary the QA gate uses so an operator reading
#: an artifact does not have to learn a second one.
PASS = "PASS"
OUT_OF_BAND = "OUT_OF_BAND"
UNKNOWN = "NO_SPEC"

#: The kind recorded on the artifact, alongside "compatibility" and
#: "final_qa".
GATE_KIND = "duration"

_CACHE: Optional[Dict] = None


def _config() -> Dict:
    """The `duration:` block of config.yaml.

    Read from config, never hardcoded here — the whole point of (a) is that
    a band and a rate are settings an operator can retune after a voice or
    model change, not constants buried in a prompt string.
    """
    global _CACHE
    if _CACHE is None:
        import yaml
        raw = yaml.safe_load((ROOT / "config.yaml").read_text()) or {}
        _CACHE = raw.get("duration") or {}
    return _CACHE


def reload() -> None:
    """Drop the cached config. For tests and for a long-lived dashboard."""
    global _CACHE
    _CACHE = None


def band() -> Dict[str, float]:
    b = _config().get("band") or {}
    return {
        "min_seconds": float(b.get("min_seconds", 50.0)),
        "max_seconds": float(b.get("max_seconds", 80.0)),
        "target_seconds": float(b.get("target_seconds", 65.0)),
    }


def outro_seconds() -> float:
    return float(_config().get("outro_seconds", 4.0))


def type_spec(video_type: str) -> Optional[Dict[str, float]]:
    """The measured rate and declared silence for one type, or None.

    None rather than a default. A type with no measurement has no basis for
    a word target, and inventing one would put a made-up number in the same
    field as six measured ones.
    """
    entry = (_config().get("types") or {}).get((video_type or "").lower())
    if not entry:
        return None
    return {"rate": float(entry["rate"]), "silence": float(entry["silence"]),
            "n": int(entry.get("n", 0)),
            "fixed_words": entry.get("fixed_words"),
            "items_spoken": int(entry.get("items_spoken", 1))}


def overhead(video_type: str) -> Optional[float]:
    """Seconds of the finished video that are not speech."""
    spec = type_spec(video_type)
    return None if spec is None else spec["silence"] + outro_seconds()


def word_target(video_type: str, target_seconds: float = None) -> Optional[int]:
    """How many SPOKEN words this type needs to land on the target duration.

    Spoken words: what the TTS will actually say. For the segmented types
    that is the text of the segments, not `full_script`.
    """
    spec = type_spec(video_type)
    if spec is None:
        return None
    seconds = float(target_seconds if target_seconds is not None
                    else band()["target_seconds"])
    speech_seconds = seconds - (spec["silence"] + outro_seconds())
    return max(1, round(speech_seconds * spec["rate"]))


def word_range(video_type: str) -> Optional[Dict[str, int]]:
    """Word counts for the two edges of the band, for a prompt instruction.

    A range rather than a single number because a model given one number
    treats it as approximate anyway; given a range it has something to
    aim inside.
    """
    b = band()
    lo = word_target(video_type, b["min_seconds"])
    hi = word_target(video_type, b["max_seconds"])
    mid = word_target(video_type, b["target_seconds"])
    if lo is None:
        return None
    return {"min": lo, "target": mid, "max": hi}


def project(video_type: str, narration_seconds: float) -> float:
    """The finished video's duration, from a real measured narration.

    narration ALREADY contains the declared silence, so only the outro is
    added. Adding `silence` here would double-count it — the mistake the
    unpaired arithmetic made in the other direction.
    """
    return float(narration_seconds or 0.0) + outro_seconds()


def check(video_type: str, narration_seconds: float,
          measured_video_seconds: float = None) -> Dict:
    """The duration verdict for one artifact, shaped like a gate record.

    Recorded on the artifact whether it passes or fails: a silent pass tells
    an operator nothing, and the point of the exercise is that duration
    stops being invisible.

    `measured_video_seconds` is used in preference to the projection when
    the video already exists — a projection is only needed before the render.
    """
    b = band()
    projected = project(video_type, narration_seconds)
    actual = float(measured_video_seconds) if measured_video_seconds else None
    judged = actual if actual is not None else projected

    spec = type_spec(video_type)
    record = {
        "kind": GATE_KIND,
        "version": 1,
        "video_type": video_type,
        "narration_seconds": round(float(narration_seconds or 0.0), 2),
        "outro_seconds": outro_seconds(),
        "projected_seconds": round(projected, 2),
        "measured_seconds": round(actual, 2) if actual is not None else None,
        "band": [b["min_seconds"], b["max_seconds"]],
        "target_seconds": b["target_seconds"],
        "word_target": word_target(video_type),
    }

    if spec is None:
        # An unmeasured type is not a type that passes. Same rule as the
        # timing contract: unknown is a refusal to judge, not a pass.
        record["status"] = UNKNOWN
        record["reason"] = (
            f"no duration spec for video type {video_type!r}; add it to "
            f"config.yaml duration.types after measuring it")
        return record

    if judged < b["min_seconds"]:
        record["status"] = OUT_OF_BAND
        record["reason"] = (f"{judged:.1f}s is {b['min_seconds'] - judged:.1f}s "
                            f"under the {b['min_seconds']:.0f}s floor")
    elif judged > b["max_seconds"]:
        record["status"] = OUT_OF_BAND
        record["reason"] = (f"{judged:.1f}s is {judged - b['max_seconds']:.1f}s "
                            f"over the {b['max_seconds']:.0f}s ceiling")
    else:
        record["status"] = PASS
        record["reason"] = f"{judged:.1f}s is inside {b['min_seconds']:.0f}-{b['max_seconds']:.0f}s"
    return record


def prompt_instruction(video_type: str) -> str:
    """The duration instruction for a generator prompt.

    Built here rather than written into each prompt string, so retuning the
    band is a config edit and not six prompt edits. Returns "" for a type
    with no spec, so a prompt can interpolate it unconditionally.
    """
    words = word_range(video_type)
    if not words:
        return ""
    b = band()
    return (
        f"DURACIÓN OBJETIVO: el video terminado debe durar entre "
        f"{b['min_seconds']:.0f} y {b['max_seconds']:.0f} segundos, "
        f"idealmente {b['target_seconds']:.0f}.\n"
        f"Para lograrlo, el texto NARRADO (lo que se dice en voz alta) debe "
        f"tener entre {words['min']} y {words['max']} palabras, "
        f"idealmente {words['target']}.\n"
        f"Esto es un requisito, no una sugerencia: un video más corto que "
        f"{b['min_seconds']:.0f}s o más largo que {b['max_seconds']:.0f}s se rechaza."
    )


# ───────────────────────────── repetition ─────────────────────────────

def repetition_pause() -> float:
    """Seconds of REAL silence between takes.

    Real, not a comma. A repeat with no gap is one long line and teaches
    nothing; the pause is where the learner says it back, which is the
    entire pedagogical claim being made here.
    """
    return float((_config().get("repetition") or {}).get("pause_seconds", 0.9))


def takes(video_type: str) -> int:
    """How many times the English is spoken, INCLUDING the first.

    1 means no repetition. Never 0 — a type configured to say the phrase
    zero times would silently drop the content it exists to teach.
    """
    cfg = (_config().get("repetition") or {}).get("takes") or {}
    return max(1, int(cfg.get((video_type or "").lower(), 1)))


def repeat_cost(video_type: str, phrase_seconds: float, n_phrases: int = 1) -> float:
    """Seconds this type's repetition adds. For projecting before synthesis.

    Each extra take costs the phrase plus one pause; the first take is the
    content that was always there.
    """
    extra = takes(video_type) - 1
    return n_phrases * extra * (float(phrase_seconds) + repetition_pause())


# ─────────────────────── the per-ITEM budget (A) ───────────────────────

def per_item_budget(video_type: str, target_seconds: float = None) -> Optional[int]:
    """Explanation words for the ONE item this type actually speaks.

    WHY PER ITEM AND NOT PER SCRIPT. Given "3 questions, 107 words total"
    the model treats the item count as binding and the word count as
    advisory: it writes three short questions and stops. quiz, fill_blank
    and true_false all landed under the floor that way, hitting 37-55% of
    an aggregate target. A budget it can count against a thing it is
    already counting — "this explanation, 76 words" — is a constraint of
    the same kind as "3 questions".

    WHY THE BUDGET IS SO MUCH LARGER THAN IT LOOKS. Only ONE item is
    synthesised. The prompt asks for three, GPT writes three, and the TTS
    reads the root-level question/options/correct/explanation only —
    script_schema calls `questions` DEAD PAYLOAD and says so. So the whole
    speech budget minus the fixed structure lands on a single explanation,
    which is why quiz's comes out near 76 words rather than the 22 it
    carries today.

    Returns None for a type with no fixed_words measurement, which is every
    single-item type: educational and pronunciation have no items to
    apportion and take the whole-script target instead.
    """
    spec = type_spec(video_type)
    if not spec or spec.get("fixed_words") is None:
        return None
    total = word_target(video_type, target_seconds)
    remaining = total - int(spec["fixed_words"])
    return max(1, round(remaining / max(1, spec["items_spoken"])))


def per_item_instruction(video_type: str) -> str:
    """The per-item sentence for a prompt, or "" when the type has no items."""
    budget = per_item_budget(video_type)
    if budget is None:
        return ""
    low, high = round(budget * 0.9), round(budget * 1.1)
    return (
        f"LONGITUD DE LA EXPLICACIÓN (obligatorio, cuéntalo): el campo "
        f"\"explanation\" de nivel raíz — el que se narra — debe tener entre "
        f"{low} y {high} palabras, idealmente {budget}.\n"
        f"Es una explicación DE ENSEÑANZA, no una frase: define el término, "
        f"contrasta con la opción incorrecta más tentadora, da UN ejemplo "
        f"real y añade un matiz de uso. Las explicaciones cortas de 20 "
        f"palabras son la razón por la que estos videos quedan cortos."
    )

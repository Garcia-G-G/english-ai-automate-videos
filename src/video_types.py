#!/usr/bin/env python3
"""THE list of video types, written once.

WHY THIS EXISTS. Adding a type meant editing fourteen places, and four of
them were the same list written out independently:

    script_schema.VIDEO_TYPES        the tuple
    script_schema.VideoType          the Literal, the same names again
    script_generator.VIDEO_TYPES     a third copy
    video/__init__ argparse choices  a fourth
    timing_contract.V3_TYPES         which family a type renders from
    clip_contrast.TEXT_ZONES         the band a background must not fight
    admin quick-buttons              the dashboard's own hand-written list
    tests/test_layout_pins.FRAME_FN  and one more in the tests

So a type could be legal in the schema, illegal in the generator, absent
from the CLI and missing from the dashboard all at once, and nothing failed
loudly -- it simply did not appear. That is this repo's signature defect:
una capacidad sin puerta es una capacidad que no existe. It is not
hypothetical and it is not only about future types. TODAY, on main, the
dashboard's quick-button row offers four of the six types; fill_blank and
pronunciation have no button. admin.py:2264 documents having fixed exactly
that defect in the scheduler, and it regrew in a different list in the same
file.

WHY THE CALLABLES ARE STRINGS. script_schema is imported by nearly
everything, including tools that never render. If this module imported the
renderers, `import script_schema` would pull in PIL, numpy and the whole
video stack. The entries name their functions as "module:attribute" and
`renderer_for()` resolves one on demand, so the registry stays a leaf and
costs nothing to import.

ADDING A TYPE, after this: write the renderer, write the audio generator,
add one entry here.
"""

from __future__ import annotations

from typing import Dict, Optional

#: One entry per type. Every list in the first paragraph reads from this.
#:
#: timing        "v3"    per-segment assembly; segment_times carries measured
#:                       boundaries (timing_contract.V3_TYPES)
#:               "turbo" word-by-word from a Whisper timeline (TURBO_TYPES)
#: text_band     (top, bottom) rows the on-screen text occupies, which a
#:               background must not fight (clip_contrast.TEXT_ZONES)
#: dashboard     the label on the Generate button, or None for no button
TYPES: Dict[str, dict] = {
    "educational": {
        "renderer":  "video.educational:create_frame_educational",
        "timing":    "turbo",
        "text_band": (700, 1060),   # the headline band, widened for shadow
        "dashboard": "Educational",
    },
    "quiz": {
        "renderer":  "video.quiz:create_frame_quiz",
        "resolver":  "video.quiz:resolve_quiz_timestamps",
        "audio":     "generate_quiz_audio_segmented",
        "timing":    "v3",
        "text_band": (270, 1450),   # question zone top .. countdown zone
        "dashboard": "Quiz",
    },
    "true_false": {
        "renderer":  "video.true_false:create_frame_true_false",
        "audio":     "generate_true_false_audio_segmented",
        "timing":    "v3",
        "text_band": (180, 1400),   # question .. explanation
        "dashboard": "True/False",
    },
    "fill_blank": {
        "renderer":  "video.fill_blank:create_frame_fill_blank",
        "audio":     "generate_fill_blank_audio_segmented",
        "timing":    "v3",
        "text_band": (230, 1120),   # sentence card .. translation pill
        "dashboard": "Fill Blank",
    },
    "pronunciation": {
        "renderer":  "video.pronunciation:create_frame_pronunciation",
        "timing":    "turbo",
        "text_band": (230, 1160),   # title .. correct text
        "dashboard": "Pronunciation",
    },
    "vocabulary": {
        "renderer":  "video.vocabulary:create_frame_vocabulary",
        "audio":     "generate_vocabulary_audio_segmented",
        "timing":    "v3",
        "text_band": (240, 1400),   # card top .. timer bar
        "dashboard": "Vocabulary",
    },
}

#: THE list. Order is the registry's order, which is the order every menu,
#: CLI choice list and schema Literal now shows.
VIDEO_TYPES = tuple(TYPES)

#: Derived, so a type cannot be legal in one family and unknown to the other.
V3_TYPES = frozenset(k for k, v in TYPES.items() if v.get("timing") == "v3")
TURBO_TYPES = frozenset(k for k, v in TYPES.items() if v.get("timing") == "turbo")

#: (top, bottom) per type, for the background contrast check.
TEXT_ZONES = {k: v["text_band"] for k, v in TYPES.items() if v.get("text_band")}

#: [(label, type)] for the dashboard's Generate buttons -- every type with a
#: label gets a door, which is the whole point.
DASHBOARD_BUTTONS = [(v["dashboard"], k) for k, v in TYPES.items()
                     if v.get("dashboard")]

#: {type: "create_frame_x"} — the bare function name, for callers that
#: already know which module they are looking in.
FRAME_FN = {k: v["renderer"].split(":", 1)[1] for k, v in TYPES.items()}


def spec(video_type: str) -> Optional[dict]:
    """The registry entry, or None for a type that does not exist."""
    return TYPES.get((video_type or "").lower())


def audio_generator_name(video_type: str) -> Optional[str]:
    """`generate_<type>_audio_segmented`, or None for a word-timeline type."""
    entry = spec(video_type)
    return entry.get("audio") if entry else None


def renderer_for(video_type: str):
    """Import and return the frame function. Resolved on demand, never at
    import, so this module stays free to import from anywhere."""
    entry = spec(video_type)
    if not entry:
        raise KeyError(f"unknown video type: {video_type!r}")
    module_name, attribute = entry["renderer"].split(":", 1)
    module = __import__(module_name, fromlist=[attribute])
    return getattr(module, attribute)


def resolver_for(video_type: str):
    """The timestamp resolver, or None when the type has none."""
    entry = spec(video_type)
    if not entry or not entry.get("resolver"):
        return None
    module_name, attribute = entry["resolver"].split(":", 1)
    module = __import__(module_name, fromlist=[attribute])
    return getattr(module, attribute)

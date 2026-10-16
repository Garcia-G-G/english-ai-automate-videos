"""Motion for the v1 renderers: entrances, idle drift, scene transitions.

    from video.motion import entrance, idle_dy, scene_cuts, apply_transition
    entrance(t, start)            -> (scale, dy)   a spring pop, settles to (1, 0)
    idle_dy(t, start, phase)      -> dy <= 0       a slow float while on screen
    scene_cuts(segment_times)     -> [seconds]     where a section begins
    apply_transition(frame, t, cuts)               a zoom punch + flash at a cut

WHY THIS EXISTS. The owner's note on the first 2-item quizzes: "super cool,
but I need more dynamism, more movement". Every v1 renderer faded text in,
slid it a few pixels and then held it perfectly still until it left, so a
seven-second countdown was seven seconds of a still image with a number
changing on it.

EXTRACTED, NOT IMPORTED. The easing curves are copied from v2/motion.py,
the same way timing_engine was. v2 is frozen, and its README says v1 must
not import anything else from it.

THREE RULES EVERY FUNCTION HERE KEEPS, because breaking any of them undoes
work this repo has already paid for:

  1. PURE FUNCTIONS OF t. The compositor may ask for frames in any order,
     and a render must be byte-reproducible. No randomness, no state.

  2. NEVER LATER THAN THE VOICE. An entrance only changes HOW an element
     arrives, never WHEN. Opacity stays with the caller's existing fade,
     so text is readable when it was readable before, and the synced
     timestamps are never touched.

  3. NEVER PAST A FLOOR. idle_dy() only ever moves UP from the resting
     position. Several cards are clamped to watermark_top() and other
     floors at their resting position; motion that went below it would
     reopen the overflow those clamps closed.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from segment_ids import split_item


def clamp01(p: float) -> float:
    return 0.0 if p < 0.0 else (1.0 if p > 1.0 else p)


# ── Easing curves (from v2/motion.py) ────────────────────────────────

def ease_out_back(p: float, overshoot: float = 1.70158) -> float:
    """Decelerates past 1.0 and settles back: the 'pop' in a pop-in."""
    p = clamp01(p)
    q = p - 1.0
    return 1.0 + (overshoot + 1.0) * q * q * q + overshoot * q * q


def ease_out_expo(p: float) -> float:
    p = clamp01(p)
    return 1.0 if p >= 1.0 else 1.0 - math.pow(2.0, -10.0 * p)


def ease_in_out_cubic(p: float) -> float:
    p = clamp01(p)
    if p < 0.5:
        return 4.0 * p * p * p
    return 1.0 - math.pow(-2.0 * p + 2.0, 3) / 2.0


def spring(p: float, damping: float = 6.0, frequency: float = 2.2) -> float:
    """Damped spring settling on exactly 1.0 at p = 1."""
    p = clamp01(p)
    if p >= 1.0:
        return 1.0
    return 1.0 - math.exp(-damping * p) * math.cos(frequency * math.pi * p)


# ── Entrances ────────────────────────────────────────────────────────

#: How long an entrance moves. Short on purpose: the eye reads the text
#: through the last third of it, so a longer one reads as sluggish rather
#: than lively.
ENTRANCE_SECONDS = 0.42

#: Where a pop starts. 0.9 and not 0: text that grows from nothing is
#: unreadable for most of its entrance, and rule 2 says an entrance must
#: not cost readability.
ENTRANCE_FROM_SCALE = 0.90

#: Pixels an element rises through on its way in.
ENTRANCE_RISE_PX = 36


def entrance(t: float, start: float, dur: float = ENTRANCE_SECONDS,
             rise: float = ENTRANCE_RISE_PX) -> Tuple[float, float]:
    """(scale, dy) for an element that arrives at `start`.

    A spring: scale 0.90 -> a little past 1 -> 1.0, while the element rises
    `rise` pixels into place. Before `start` it returns the first frame's
    values; after `start + dur` it returns exactly (1.0, 0.0), so a settled
    element draws precisely where it always did.

    dy is POSITIVE (below the resting position) while it arrives. A caller
    whose element sits on a floor must clamp -- quiz's explanation card
    already does, for its own slide.
    """
    if dur <= 0 or t >= start + dur:
        return 1.0, 0.0
    p = clamp01((t - start) / dur)
    s = spring(p, damping=5.5, frequency=1.6)
    scale = ENTRANCE_FROM_SCALE + (1.0 - ENTRANCE_FROM_SCALE) * s
    dy = rise * (1.0 - ease_out_expo(p))
    return scale, dy


def stagger(index: int, delay: float = 0.07) -> float:
    return max(0, index) * delay


# ── Idle motion ──────────────────────────────────────────────────────

#: Peak height of the float, in pixels. Three: enough that the frame is
#: never a still image, small enough that nobody reads it as a wobble.
IDLE_AMPLITUDE_PX = 3.0

#: One float cycle. Slow, so it reads as breathing, not as shaking.
IDLE_PERIOD_S = 3.2

#: The float fades in over this long after the element arrives, so it
#: never starts with a jump at the end of an entrance.
IDLE_RAMP_S = 0.8


def idle_dy(t: float, start: float, phase: float = 0.0,
            amplitude: float = IDLE_AMPLITUDE_PX,
            period: float = IDLE_PERIOD_S) -> float:
    """Vertical drift for an element resting on screen since `start`.

    Always <= 0: it floats UP from the resting position and back, never
    below it (rule 3). Starts at exactly 0 with zero velocity, so nothing
    jumps when it begins. `phase` in cycles (0..1) keeps a stack of cards
    from moving in lockstep, which reads as the whole screen shifting.
    """
    if t <= start or amplitude <= 0 or period <= 0:
        return 0.0
    elapsed = t - start
    ramp = ease_in_out_cubic(elapsed / IDLE_RAMP_S) if IDLE_RAMP_S > 0 else 1.0
    wave = 0.5 - 0.5 * math.cos(2.0 * math.pi * (elapsed / period + phase))
    # With a phase the wave does not start at 0; the ramp is what makes the
    # first frame 0 regardless, so a phase can never cause a jump.
    return -amplitude * ramp * wave


def idle_scale(t: float, start: float, phase: float = 0.0,
               amount: float = 0.012, period: float = 2.6) -> float:
    """A slow scale 'breath' for a focal element: 1.0 .. 1.0 + amount."""
    if t <= start or amount <= 0 or period <= 0:
        return 1.0
    elapsed = t - start
    ramp = ease_in_out_cubic(elapsed / IDLE_RAMP_S)
    wave = 0.5 - 0.5 * math.cos(2.0 * math.pi * (elapsed / period + phase))
    return 1.0 + amount * ramp * wave


# ── Scene transitions ────────────────────────────────────────────────

#: The bare segment names that open a new SECTION of a video. A transition
#: fires at each. Deliberately NOT the countdown: a punch on every number
#: would be seven seconds of the screen jumping while the viewer is trying
#: to think, and 'think' already marks the start of that section.
SECTION_KEYS = frozenset({
    "question", "statement", "sentence", "title", "word",
    "options", "option_a", "option_1",
    "think",
    "answer",
    "explanation",
})

#: `pair_3`, `example_2`: one section per vocabulary pair / example.
_NUMBERED_SECTIONS = ("pair_", "example_")

#: Cuts closer together than this collapse into the first. Two punches in
#: half a second read as a glitch, not as two sections.
MIN_CUT_GAP_S = 0.8

#: No transition this early: frame 0 IS the opening, and punching it would
#: hide the first words instead of introducing them.
FIRST_CUT_AFTER_S = 0.5


def scene_cuts(segment_times: Optional[Dict]) -> List[float]:
    """Seconds at which a new section begins, from a segment_times dict.

    Understands item-prefixed ids (`i2_question`), so the second item of a
    multi-item quiz opens with a transition too. Returns [] for a dict it
    cannot read -- a video without cuts simply has no transitions.
    """
    if not isinstance(segment_times, dict):
        return []
    starts = []
    for seg_id, span in segment_times.items():
        if not isinstance(span, dict):
            continue
        _item, name = split_item(seg_id)
        if name in SECTION_KEYS or name.startswith(_NUMBERED_SECTIONS):
            try:
                start = float(span.get("start"))
            except (TypeError, ValueError):
                continue
            starts.append(start)
    return spaced_cuts(starts)


def spaced_cuts(starts: Iterable[float]) -> List[float]:
    """Section starts -> transition times: sorted, none in the opening
    FIRST_CUT_AFTER_S, and none within MIN_CUT_GAP_S of the one before.

    Public for renderers whose sections do not come from segment_times
    (educational's English lines).
    """
    cuts: List[float] = []
    for s in sorted(float(x) for x in starts):
        if s < FIRST_CUT_AFTER_S:
            continue
        if not cuts or s - cuts[-1] >= MIN_CUT_GAP_S:
            cuts.append(s)
    return cuts


#: How long a transition lasts. It starts AT the cut, never before it, so
#: it can only ever follow the voice (rule 2).
TRANSITION_SECONDS = 0.36

#: Peak zoom of the punch. 3.5% on a 1080px frame is ~19px each side:
#: plainly a camera move, not enough to push text into the safe margins.
TRANSITION_ZOOM = 0.035

#: Peak opacity of the white flash that opens a transition.
TRANSITION_FLASH = 0.16


def transition_at(t: float, cuts: Sequence[float],
                  dur: float = TRANSITION_SECONDS) -> Tuple[float, float]:
    """(zoom, flash) at time t. (1.0, 0.0) whenever no cut is active.

    zoom rises fast to 1 + TRANSITION_ZOOM and eases back to exactly 1.0;
    the flash is brightest at the cut and gone by 40% of the way through.
    """
    active = None
    for c in cuts or ():
        if c <= t < c + dur:
            active = c
    if active is None:
        return 1.0, 0.0
    p = clamp01((t - active) / dur)
    # A bump that peaks early (p ~ 0.25) and settles: fast in, slow out.
    bump = math.sin(math.pi * math.pow(p, 0.6))
    zoom = 1.0 + TRANSITION_ZOOM * bump
    flash = TRANSITION_FLASH * max(0.0, 1.0 - p / 0.4)
    return zoom, flash


def apply_transition(frame, t: float, cuts: Iterable[float]):
    """Apply the transition at t to a PIL RGBA frame, in place.

    Called by finalize_frame BEFORE the character, progress bar and
    watermark are drawn, so the content punches and the chrome stays put.
    A no-op, and free, on every frame that is not inside a transition --
    which is nearly all of them.
    """
    zoom, flash = transition_at(t, list(cuts or ()))
    if zoom == 1.0 and flash == 0.0:
        return frame
    from PIL import Image

    w, h = frame.size
    if zoom > 1.0:
        cw, ch = w / zoom, h / zoom
        left, top = (w - cw) / 2.0, (h - ch) / 2.0
        zoomed = frame.resize((w, h), Image.BILINEAR,
                              box=(left, top, left + cw, top + ch))
        frame.paste(zoomed, (0, 0))
    if flash > 0.0:
        white = Image.new("RGBA", (w, h), (255, 255, 255, int(255 * flash)))
        frame.alpha_composite(white)
    return frame

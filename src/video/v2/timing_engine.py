"""Display-timing engine for on-screen text groups (v2 renderer).

Fixes the chronic bugs of the old pipeline:

* SubtitleProcessor trimmed a group's ``end`` to make room for the next
  one (``end = next_start - min_gap/2`` and ``next_start - 0.033``), so
  text vanished while the audio was still saying its last word.
* The renderer only faded a group AFTER its end and only when no other
  group was active, so back-to-back groups popped out with no exit
  animation (perceived as parpadeo), and long silences left black holes.

Rules implemented here (the audio timestamps are never modified — only
the *display* window):

1. Golden rule — a group NEVER leaves the screen before its last word
   ends in the audio + ``TAIL_PAD`` (350 ms).  The only exception is a
   hard clamp when the NEXT group's audio starts earlier than that
   (overlapping timestamps), because windows must not overlap.
2. Minimum on-screen duration: ``max(MIN_HOLD, chars * PER_CHAR)``.
3. If the gap to the next group allows it, the window extends right up
   to the next group's start (no dead air).
4. Long silence (> ``HOLD_GAP``) between groups: the previous group
   stays on screen ("hold") until ``HOLD_RELEASE`` before the next one.
5. No overlaps, strict monotonicity, full validation with asserts.

Each group dict gains:
    display_start / display_end   — the visibility window
    fade_in / fade_out            — transition durations (pre-clamped so
                                    entrance+exit always fit the window)
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

#: Length of the CTA tail reserved at the end of an educational video. Lives
#: here, with the timing logic, because BOTH engines need it: v2 for its
#: layout phases and v1 for timing_engine's `content_end`. Previously a
#: v2-private constant, which is why v1 had no CTA reservation at all.
CTA_LEN = 2.5

# ── INHERITED-UNVALIDATED ───────────────────────────────────────────
# Every constant below came from v2 and none has a recorded derivation. They
# are plausible and the engine's INVARIANTS are tested
# (tests/test_timing_engine.py), but the specific values are not measured
# against anything.
#
# This matters more now than it did: Step 3 wired this engine into the v1
# path, so these numbers affect EVERY video that ships, not a dormant renderer.
# The QA gate cannot check them — it reads audio, and these are display
# timings. Deriving them needs the layout work plus a way to measure
# on-screen text, which is a later step. Recorded in docs/recorded-debt.md.
TAIL_PAD = 0.35        # golden-rule cushion after the last word (s)
MIN_HOLD = 1.2         # absolute minimum display time (s)
PER_CHAR = 0.045       # reading-speed floor (s per character)
HOLD_GAP = 2.0         # silence longer than this triggers "hold" mode
HOLD_RELEASE = 0.4     # hold ends this long before the next group
FADE_IN = 0.24         # default entrance duration
FADE_OUT = 0.22        # default exit duration
_EPS = 1e-6


def _last_word_end(group: Dict) -> float:
    words = group.get("words") or []
    if words:
        return max(float(w.get("end", 0.0)) for w in words)
    return float(group.get("end", 0.0))


def _min_duration(group: Dict) -> float:
    return max(MIN_HOLD, len(group.get("text", "")) * PER_CHAR)


MERGE_MAX_CHARS = 64   # merged group text budget (fits 3 card lines)
MERGE_SHORT_AUDIO = 1.0  # groups whose audio lasts less than this are
                         # merge candidates when squeezed by neighbors
MERGE_MAX_GAP = 0.4      # only merge across near-continuous audio


def _merge_short_groups(groups: List[Dict]) -> List[Dict]:
    """Fuse tiny groups squeezed between continuous audio neighbors.

    A group whose audio span is < MERGE_SHORT_AUDIO and whose neighbor
    starts almost immediately can never satisfy the minimum display time
    without overlapping — instead of flashing it, merge it with the
    neighbor (keeping the combined text readable).
    """
    if len(groups) < 2:
        return groups

    def _can_merge(a: Dict, b: Dict) -> bool:
        gap = float(b.get("start", 0)) - float(a.get("end", 0))
        combined = len(a.get("text", "")) + len(b.get("text", "")) + 1
        return gap <= MERGE_MAX_GAP and combined <= MERGE_MAX_CHARS

    def _fuse(a: Dict, b: Dict) -> Dict:
        return {
            "words": (a.get("words") or []) + (b.get("words") or []),
            "text": (a.get("text", "") + " " + b.get("text", "")).strip(),
            "start": float(a.get("start", 0.0)),
            "end": max(float(a.get("end", 0.0)), float(b.get("end", 0.0))),
            "english": bool(a.get("english") or b.get("english")),
        }

    out: List[Dict] = []
    i = 0
    while i < len(groups):
        g = groups[i]
        audio_span = float(g.get("end", 0)) - float(g.get("start", 0))
        if audio_span < MERGE_SHORT_AUDIO:
            # Prefer merging forward (keeps sentence order natural)
            if i + 1 < len(groups) and _can_merge(g, groups[i + 1]):
                groups[i + 1] = _fuse(g, groups[i + 1])
                i += 1
                continue
            if out and _can_merge(out[-1], g):
                out[-1] = _fuse(out[-1], g)
                i += 1
                continue
        out.append(g)
        i += 1
    if len(out) != len(groups):
        logger.info("timing_engine: merged %d short groups -> %d groups",
                    len(groups) - len(out), len(out))
    return out


def compute_display_windows(groups: List[Dict], duration: float,
                            content_end: Optional[float] = None,
                            merge_short: bool = True) -> List[Dict]:
    """Assign non-overlapping display windows to ``groups`` (mutates+returns).

    Args:
        groups: SubtitleProcessor output (each has start/end/words/text),
            assumed sorted by start.
        duration: Total audio/video duration.
        content_end: Last usable instant for text (e.g., CTA start).
        merge_short: Fuse flash-prone tiny groups before windowing.
    """
    if not groups:
        return groups

    groups = sorted(groups, key=lambda g: float(g.get("start", 0.0)))
    if merge_short:
        groups = _merge_short_groups(groups)
    content_end = duration if content_end is None else min(content_end, duration)

    n = len(groups)
    for i, g in enumerate(groups):
        g_start = float(g.get("start", 0.0))
        prev_out = groups[i - 1]["display_end"] if i > 0 else 0.0

        # Entrance: at the group's audio start, but never before the
        # previous group has left the screen.
        t_in = max(g_start, prev_out)

        # Exit floor: golden rule + minimum reading time.
        t_out = max(_last_word_end(g) + TAIL_PAD, t_in + _min_duration(g))

        if i + 1 < n:
            next_in = float(groups[i + 1].get("start", 0.0))
            next_in = max(next_in, t_in + _EPS)   # keep ordering sane
            if next_in - t_out > HOLD_GAP:
                # Long silence: hold on screen until shortly before next.
                t_out = next_in - HOLD_RELEASE
            elif t_out < next_in:
                # Small gap: extend to the next group's entrance (no gap).
                t_out = next_in
            elif t_out > next_in:
                # Timestamps overlap — windows may not. Clamp. The audio
                # keeps flowing into the next group, so this is seamless.
                t_out = next_in
        else:
            # Last group: keep it up through trailing silence to the end
            # of the content zone (never past it).
            t_out = min(max(t_out, content_end), content_end)
            t_out = max(t_out, min(_last_word_end(g) + TAIL_PAD, duration))

        if t_out <= t_in:                 # degenerate input — force minimum
            t_out = t_in + max(0.5, _min_duration(g))
            if i + 1 < n:
                t_out = min(t_out, float(groups[i + 1].get("start", t_out)))
                if t_out <= t_in:
                    t_out = t_in + 0.25

        window = t_out - t_in
        g["display_start"] = round(t_in, 3)
        g["display_end"] = round(t_out, 3)
        # Transitions always fit inside the window and never overlap each
        # other (anti-flicker: entrance+exit <= 80% of the window).
        budget = max(window * 0.8, 0.05)
        g["fade_in"] = round(min(FADE_IN, budget * 0.55), 3)
        g["fade_out"] = round(min(FADE_OUT, budget * 0.45), 3)

    validate_windows(groups, duration)
    return groups


def validate_windows(groups: List[Dict], duration: float) -> None:
    """Assert the invariants. Raises AssertionError on violation."""
    prev_out = 0.0
    for i, g in enumerate(groups):
        t_in, t_out = g["display_start"], g["display_end"]
        assert t_out > t_in, f"group {i}: empty window {t_in}..{t_out}"
        assert t_in >= prev_out - 1e-3, (
            f"group {i}: overlaps previous (in={t_in} < prev_out={prev_out})")
        # Golden rule (except when clamped by the next group's audio)
        lwe = _last_word_end(g)
        next_in = (groups[i + 1]["display_start"] if i + 1 < len(groups)
                   else float("inf"))
        if lwe + TAIL_PAD <= next_in and lwe <= duration:
            # The pad can never extend past the end of the audio/video —
            # clamp the requirement to the total duration.
            required = min(lwe + TAIL_PAD, duration)
            assert t_out >= required - 1e-3, (
                f"group {i}: leaves at {t_out} before last word {lwe}+pad")
        # Transitions must fit
        assert g["fade_in"] + g["fade_out"] <= (t_out - t_in) + 1e-3, (
            f"group {i}: transitions larger than window")
        prev_out = t_out
    logger.info("timing_engine: %d windows validated (duration %.2fs)",
                len(groups), duration)


def group_alpha(g: Dict, t: float) -> float:
    """Visibility alpha (0..1) for group ``g`` at time ``t`` — clamped.

    Encapsulates the anti-flicker easing: smooth-in during fade_in,
    hold at 1, smooth-out during fade_out. Never returns <0 or >1.
    """
    t_in, t_out = g["display_start"], g["display_end"]
    if t < t_in or t >= t_out:
        return 0.0
    a = 1.0
    fi, fo = g.get("fade_in", FADE_IN), g.get("fade_out", FADE_OUT)
    if fi > 0 and t < t_in + fi:
        p = (t - t_in) / fi
        a = min(a, p * p * (3 - 2 * p))          # smoothstep
    if fo > 0 and t > t_out - fo:
        p = (t_out - t) / fo
        a = min(a, p * p * (3 - 2 * p))
    return 0.0 if a < 0.0 else (1.0 if a > 1.0 else a)


def debug_table(groups: List[Dict]) -> str:
    """Formatted table: text, t_in, t_out, duration, cushion vs last word."""
    header = (f"{'#':>3} {'t_in':>7} {'t_out':>7} {'dur':>6} "
              f"{'lastw':>7} {'cushion':>8}  text")
    lines = [header, "-" * len(header)]
    for i, g in enumerate(groups):
        lwe = _last_word_end(g)
        cushion = g["display_end"] - lwe
        lines.append(
            f"{i:>3} {g['display_start']:>7.2f} {g['display_end']:>7.2f} "
            f"{g['display_end'] - g['display_start']:>6.2f} {lwe:>7.2f} "
            f"{cushion:>+8.2f}  {g.get('text', '')[:52]}")
    return "\n".join(lines)

"""Tablero frames (STEP 82 §2): a pure function of t over the SAME measured beats as the notebook.

Per item: Spanish starts -> the tile goes active (0.18 s ease-out) -> the thinking pause (a coral
timer shrinks) -> at the English onset the letters fill the dashes left to right (0.35 s) -> the
tile flips yellow to blue (scaleX 1 -> 0 -> 1 over 0.25 s) and the counter ticks up. Frame 0 is
complete and static: all ten tiles blank, the question on screen; only the dots drift and Bubi
breathes. No timing is invented: it reads segment_times through the notebook's Timeline.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from ..motion import clamp01, ease_out_cubic
from . import kit

ROOT = kit.ROOT
ACTIVE_IN = 0.18
FILL_DUR = 0.35
FLIP_DUR = 0.25
COUNTER_BOUNCE = 0.25
BIEN_HECHO_HOLD = 1.6
OUTRO_IN = 0.35
TIMER_STEPS = 60              # the timer bar is quantised so the tile cache can hit
SAY_FIRST, SAY_ACTIVE = "¿Cuántas sabes?", "¡Dilo antes que yo!"
TITLE_EMOJI = re.compile(r"([\U0001F300-\U0001FAFF☀-➿]️?)\s*$")


def variant(data: Dict) -> str:
    """tablero | cuaderno. A script says which (design_ab assigns it); Tablero is the default."""
    return data.get("design_variant") or "tablero"


def topic(data: Dict) -> str:
    return str(data.get("theme") or "").split(" (")[0].strip()


def title_emoji(data: Dict) -> str:
    m = TITLE_EMOJI.search(str(data.get("video_title") or ""))
    return m.group(1) if m else str(data["items"][0]["emoji"])


@lru_cache(maxsize=32)
def has_sequel(theme: str) -> bool:
    """A sequel of this topic («más <tema>») is queued: the end card promises part 2."""
    want = f"más {theme}".lower()
    for p in (ROOT / "content" / "queue" / "how_do_you_say").glob("*.json"):
        try:
            import json
            if str(json.loads(p.read_text(encoding="utf-8")).get("theme", "")).lower().startswith(want):
                return True
        except (OSError, ValueError):
            continue
    return False


class Beats:
    """Per-item boundaries derived from the notebook Timeline."""

    def __init__(self, tl):
        self.tl = tl
        self.fill_end = [en[0] + FILL_DUR for en in tl.en]
        self.flip_end = [f + FLIP_DUR for f in self.fill_end]
        self.counted = [f + FLIP_DUR / 2 for f in self.fill_end]       # the counter ticks mid-flip

    def done_count(self, t: float) -> int:
        return sum(1 for c in self.counted if t >= c)


def _letters(english: str) -> int:
    return len(english.replace(" ", ""))


def _tile_state(i: int, t: float, tl, beats: Beats, item: Dict, pron: Optional[str]):
    """(image, scale, rot, glow, flip) for item i at t, or None when blank handled by caller."""
    es0, en0 = tl.es[i][0], tl.en[i][0]
    base = (i, item["emoji"], item["spanish"], item["english"], pron)
    if t < es0:
        return kit.tile(*base, "blank"), 1.0, 0.0, False, 1.0
    if t >= beats.flip_end[i]:
        return kit.tile(*base, "done"), 1.0, 0.0, False, 1.0
    p = ease_out_cubic(clamp01((t - es0) / ACTIVE_IN))
    scale, rot = 1 + (kit.ACTIVE_SCALE - 1) * p, kit.ACTIVE_ROT * p
    n = _letters(item["english"])
    if t < en0:
        th0, th1 = tl.think[i]
        timer = clamp01((t - th0) / max(1e-6, th1 - th0)) if t >= th0 else 0.0
        timer = round(timer * TIMER_STEPS) / TIMER_STEPS
        return kit.tile(*base, "active", 0, timer), scale, rot, True, 1.0
    if t < beats.fill_end[i]:
        k = min(n, int(n * clamp01((t - en0) / FILL_DUR)) + 1)
        return kit.tile(*base, "active", k, 1.0), scale, rot, True, 1.0
    q = (t - beats.fill_end[i]) / FLIP_DUR
    if q < 0.5:
        return kit.tile(*base, "active", n, 1.0), scale, rot, True, 1 - 2 * q
    return kit.tile(*base, "done"), 1.0, 0.0, False, 2 * q - 1


def bubi_state(t: float, tl, beats: Beats) -> Tuple[str, Optional[str]]:
    if t < tl.es[0][0]:
        return "simbolo", SAY_FIRST
    if t >= tl.recap[0]:
        return "lo_lograste", None
    for j in range(tl.n):
        if (j + 1) % 3 == 0 and beats.flip_end[j] <= t < beats.flip_end[j] + BIEN_HECHO_HOLD:
            return "bien_hecho", None
    return "wow", SAY_ACTIVE


def create_frame_tablero(t: float, data: Dict, duration: float, presentation=None) -> np.ndarray:
    from ..how_do_you_say import Timeline
    items: List[Dict] = data["items"]
    tl = data.get("_tablero_timeline")
    if tl is None:
        tl = data["_tablero_timeline"] = Timeline(data, duration)
        data["_tablero_beats"] = Beats(tl)
    beats: Beats = data["_tablero_beats"]
    family = data.get("tablero_family") or kit.family_for(topic(data))

    frame = kit.background(family, t)
    frame.alpha_composite(kit.header(title_emoji(data), topic(data)), (0, 0))

    active = None
    for i, item in enumerate(items):
        img, scale, rot, glow, flip = _tile_state(i, t, tl, beats, item, kit.pron_for(item))
        if glow:
            active = (i, img, scale, rot, flip)          # drawn last, over its neighbours
        else:
            kit.place_tile(frame, img, i)
    if active:
        i, img, scale, rot, flip = active
        kit.place_tile(frame, img, i, scale, rot, glow=True, flip=flip)

    done = beats.done_count(t)
    if done:
        q = clamp01((t - beats.counted[done - 1]) / COUNTER_BOUNCE)
        pop = 1 + 0.18 * math.sin(math.pi * q)
        c = kit.counter(done, len(items), round(pop * 50) / 50)
        frame.alpha_composite(c, (44 - kit.CARD_PAD + (190 - c.width + 80) // 2, 1505 - kit.CARD_PAD + (86 - c.height + 80) // 2))

    kit.draw_footer(frame)
    expr, say = bubi_state(t, tl, beats)
    if t >= tl.outro[0]:
        kit.draw_outro(frame, ease_out_cubic((t - tl.outro[0]) / OUTRO_IN), has_sequel(topic(data)))
    if say:
        frame.alpha_composite(kit.speech(say), (300, 1520))
    kit.place_bubi(frame, expr, t)
    return np.array(frame.convert("RGB"))


def sfx_events(data: Dict, duration: float):
    """(events, spoken spans): a soft pop as each tile lights, a swish on each flip."""
    from ..how_do_you_say import Timeline
    st = data["segment_times"]
    spoken = sorted((float(v["start"]), float(v["end"])) for k, v in st.items() if not k.startswith("think"))
    tl = Timeline(data, duration)
    beats = Beats(tl)
    events = [("pop", tl.es[i][0], 0.0) for i in range(tl.n)]
    events += [("swish", beats.fill_end[i], 0.0) for i in range(tl.n)]
    return sorted(events, key=lambda e: e[1]), spoken


# ── §6: phrases_level, one column of phrase tiles ────────────────────

PHRASE_SCALE = 1.04            # the tile is 960 wide: a gentler pop than the grid's 1.07


class PhraseBeats:
    """Per-item boundaries from the level timeline: lit with its prompt, flipped at the answer."""

    def __init__(self, tl):
        self.tl = tl
        self.flip_end = [a[0] + FLIP_DUR for a in tl.answer]
        self.counted = [a[0] + FLIP_DUR / 2 for a in tl.answer]

    def done_count(self, t: float) -> int:
        return sum(1 for c in self.counted if t >= c)


def _phrase_state(i: int, t: float, tl, beats: PhraseBeats, item: Dict):
    n = tl.n
    base = (i, n, item["spanish"], item["english"])
    if t < tl.row[i]:
        return kit.phrase_tile(*base, "blank"), 1.0, 0.0, False, 1.0
    if t >= beats.flip_end[i]:
        return kit.phrase_tile(*base, "done"), 1.0, 0.0, False, 1.0
    p = ease_out_cubic(clamp01((t - tl.row[i]) / ACTIVE_IN))
    scale, rot = 1 + (PHRASE_SCALE - 1) * p, kit.ACTIVE_ROT * p * 0.5
    a0 = tl.answer[i][0]
    if t < a0:
        th0, th1 = tl.think[i]
        timer = clamp01((t - th0) / max(1e-6, th1 - th0)) if t >= th0 else 0.0
        return kit.phrase_tile(*base, "active", round(timer * TIMER_STEPS) / TIMER_STEPS), scale, rot, True, 1.0
    q = (t - a0) / FLIP_DUR
    if q < 0.5:
        return kit.phrase_tile(*base, "active", 1.0), scale, rot, True, 1 - 2 * q
    return kit.phrase_tile(*base, "done"), 1.0, 0.0, False, 2 * q - 1


def phrases_bubi(t: float, tl, beats: PhraseBeats) -> Tuple[str, Optional[str]]:
    if t < tl.row[0]:
        return "simbolo", SAY_FIRST
    if t >= tl.outro[0]:
        return "lo_lograste", None
    for j in range(tl.n):
        if (j + 1) % 3 == 0 and beats.flip_end[j] <= t < beats.flip_end[j] + BIEN_HECHO_HOLD:
            return "bien_hecho", None
    return "wow", SAY_ACTIVE


def create_frame_tablero_phrases(t: float, data: Dict, duration: float, presentation=None) -> np.ndarray:
    from ..how_do_you_say import LevelTimeline
    items: List[Dict] = data["items"]
    tl = data.get("_tablero_timeline")
    if tl is None:
        tl = data["_tablero_timeline"] = LevelTimeline(data, duration)
        data["_tablero_beats"] = PhraseBeats(tl)
    beats: PhraseBeats = data["_tablero_beats"]
    n = len(items)
    frame = kit.background(data.get("tablero_family") or kit.family_for(topic(data)), t)
    frame.alpha_composite(kit.header("💬", topic(data) or "frases", "FRASES EN INGLÉS"), (0, 0))
    active = None
    for i, item in enumerate(items):
        img, scale, rot, glow, flip = _phrase_state(i, t, tl, beats, item)
        if glow:
            active = (i, img, scale, rot, flip)
        else:
            kit.place_phrase(frame, img, i, n)
    if active:
        i, img, scale, rot, flip = active
        kit.place_phrase(frame, img, i, n, scale, rot, flip=flip)
    done = beats.done_count(t)
    if done:
        q = clamp01((t - beats.counted[done - 1]) / COUNTER_BOUNCE)
        c = kit.counter(done, n, round((1 + 0.18 * math.sin(math.pi * q)) * 50) / 50)
        frame.alpha_composite(c, (44 - kit.CARD_PAD + (190 - c.width + 80) // 2,
                                  1505 - kit.CARD_PAD + (86 - c.height + 80) // 2))
    kit.draw_footer(frame)
    expr, say = phrases_bubi(t, tl, beats)
    if t >= tl.outro[0]:
        kit.draw_outro(frame, ease_out_cubic((t - tl.outro[0]) / OUTRO_IN), False)
    if say:
        frame.alpha_composite(kit.speech(say), (300, 1520))
    kit.place_bubi(frame, expr, t)
    return np.array(frame.convert("RGB"))


def phrases_sfx_events(data: Dict, duration: float):
    from ..how_do_you_say import LevelTimeline
    st = data["segment_times"]
    spoken = sorted((float(v["start"]), float(v["end"])) for k, v in st.items() if not k.startswith("think"))
    tl = LevelTimeline(data, duration)
    events = [("pop", tl.row[i], 0.0) for i in range(tl.n)] + [("swish", tl.answer[i][0], 0.0) for i in range(tl.n)]
    return sorted(events, key=lambda e: e[1]), spoken

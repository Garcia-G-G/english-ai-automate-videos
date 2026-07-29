"""CharacterDirector — narration-synced character clips for the kids window.

Replaces the random ClipLibraryBackground playlist (Momo throwing mud while
the voice explains grammar) with a state machine driven by the narration's
word timestamps:

    speaking (words flowing)          -> ``talking`` clips, looped
    pause > IDLE_GAP (1.2s)           -> ``idle``
    new group starting on an EN word  -> short ``reaction``
    final CTA                         -> ``celebrate``

Clip library layout (category by subfolder OR filename suffix):

    assets/clips/<profile>/<character>/talking/*.mp4
    assets/clips/<profile>/<character>/idle/*.mp4
    assets/clips/<profile>/<character>/reaction/*.mp4
    assets/clips/<profile>/<character>/celebrate/*.mp4
    assets/clips/<profile>/<character>/anything-talking.mp4   (suffix form)

Fallbacks never crash: a category without clips borrows from the nearest
one (talking -> idle -> reaction -> celebrate -> any clip found).

Cutting rules: clips change only at state boundaries or every BEAT
seconds inside a long state; cut points snap to word gaps when one is
close (never mid-word if avoidable); the same clip is never scheduled
twice in a row when an alternative exists.
"""

import logging
import random
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

CATEGORIES = ("talking", "idle", "reaction", "celebrate")

# Fallback chains — first existing category wins.
FALLBACK = {
    "talking": ("talking", "idle", "reaction", "celebrate"),
    "idle": ("idle", "talking", "reaction", "celebrate"),
    "reaction": ("reaction", "talking", "idle", "celebrate"),
    "celebrate": ("celebrate", "reaction", "talking", "idle"),
}

IDLE_GAP = 1.2        # narration silence longer than this -> idle
REACTION_LEN = 2.2    # max length of a reaction beat
BEAT = 5.0            # re-cut interval inside a long state (4-6s)
SNAP_WINDOW = 0.35    # cut points snap to a word gap within this radius


def _probe(path: Path) -> Optional[Dict]:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    if frames <= 0 or fps <= 0:
        logger.warning("CharacterDirector: unreadable clip %s", path)
        return None
    return {"path": str(path), "fps": fps, "frames": frames,
            "duration": frames / fps}


def _scan_library(root: Path) -> Dict[str, List[Dict]]:
    """Collect clips per category from subfolders and filename suffixes."""
    lib: Dict[str, List[Dict]] = {c: [] for c in CATEGORIES}
    if not root.exists():
        return lib
    for p in sorted(root.rglob("*.mp4")):
        rel_parts = [x.lower() for x in p.relative_to(root).parts]
        category = next((c for c in CATEGORIES if c in rel_parts[:-1]), None)
        if category is None:
            stem = p.stem.lower()
            category = next((c for c in CATEGORIES
                             if stem.endswith(f"-{c}") or stem.endswith(f"_{c}")),
                            None)
        if category is None:
            category = "talking"     # uncategorized: assume general narration
        info = _probe(p)
        if info:
            info["category"] = category
            lib[category].append(info)
    return lib


class CharacterDirector:
    """Callable clip scheduler + frame server for the character window.

    Args:
        clips_root: Character library root (e.g. assets/clips/kids/momo)
            or a profile root (assets/clips/kids) — scanned recursively.
        width/height: Output frame size.
        duration: Video duration in seconds.
        words: Global word timestamps [{word,start,end,is_english},...].
        groups: Display groups (used for EN reactions), may be None.
        cta_start: When the final CTA begins (celebrate state).
        seed: Deterministic clip choice.
    """

    def __init__(self, clips_root: str, width: int, height: int,
                 duration: float, words: List[Dict] = None,
                 groups: List[Dict] = None, cta_start: float = None,
                 seed: int = 7):
        self.width, self.height = width, height
        self.duration = duration
        self.words = sorted(words or [], key=lambda w: w.get("start", 0.0))
        self.groups = groups or []
        self.cta_start = duration if cta_start is None else cta_start
        self._rng = random.Random(seed)

        self.library = _scan_library(Path(clips_root))
        total = sum(len(v) for v in self.library.values())
        if total == 0:
            raise ValueError(
                f"No .mp4 clips found under '{clips_root}'. "
                "Add clips per category (talking/idle/reaction/celebrate).")
        logger.info("CharacterDirector: %s", {c: len(v) for c, v in
                                              self.library.items() if v})

        self.states = self._build_state_timeline()
        self.plan = self._assign_clips(self.states)
        logger.info("CharacterDirector plan:\n%s", self.describe_plan())

        # Sequential decode state (same pattern as ClipLibraryBackground)
        self._cap = None
        self._cap_path = None
        self._cap_frame_idx = -1
        self._last_frame = None

    # ── Timeline construction ────────────────────────────────────────

    def _speech_intervals(self) -> List[List[float]]:
        """Merge word spans separated by gaps < IDLE_GAP."""
        spans: List[List[float]] = []
        for w in self.words:
            s, e = float(w.get("start", 0)), float(w.get("end", 0))
            if spans and s - spans[-1][1] < IDLE_GAP:
                spans[-1][1] = max(spans[-1][1], e)
            else:
                spans.append([s, e])
        return spans

    def _reaction_starts(self) -> List[float]:
        """Group starts whose first words include an English keyword."""
        starts = []
        for g in self.groups:
            words = g.get("words") or []
            if any(w.get("is_english") for w in words[:3]):
                starts.append(float(g.get("display_start", g.get("start", 0))))
        return starts

    def _build_state_timeline(self) -> List[Dict]:
        """Ordered, gap-free [{start, end, state}] covering [0, duration]."""
        cta = min(self.cta_start, self.duration)
        speech = self._speech_intervals()

        # Base layer: talking during speech, idle in the gaps.
        timeline: List[Dict] = []
        cursor = 0.0
        for s, e in speech:
            s, e = max(0.0, min(s, cta)), max(0.0, min(e, cta))
            if s - cursor > 1e-3:
                timeline.append({"start": cursor, "end": s, "state": "idle"})
            if e - s > 1e-3:
                timeline.append({"start": s, "end": e, "state": "talking"})
            cursor = max(cursor, e)
        if cta - cursor > 1e-3:
            timeline.append({"start": cursor, "end": cta, "state": "idle"})
        if self.duration - cta > 1e-3:
            timeline.append({"start": cta, "end": self.duration,
                             "state": "celebrate"})
        if not timeline:
            timeline = [{"start": 0.0, "end": self.duration,
                         "state": "talking"}]

        # Overlay short reactions at EN group starts.
        for rs in self._reaction_starts():
            re_ = min(rs + REACTION_LEN, self.duration)
            timeline = self._overlay(timeline, rs, re_, "reaction")

        # Merge adjacent identical states.
        merged: List[Dict] = []
        for seg in timeline:
            if seg["end"] - seg["start"] <= 1e-3:
                continue
            if merged and merged[-1]["state"] == seg["state"] and \
                    abs(merged[-1]["end"] - seg["start"]) < 1e-3:
                merged[-1]["end"] = seg["end"]
            else:
                merged.append(dict(seg))
        return merged

    @staticmethod
    def _overlay(timeline: List[Dict], s: float, e: float,
                 state: str) -> List[Dict]:
        """Overwrite [s, e) with ``state`` (except celebrate segments)."""
        out: List[Dict] = []
        for seg in timeline:
            if seg["state"] == "celebrate" or seg["end"] <= s or seg["start"] >= e:
                out.append(seg)
                continue
            if seg["start"] < s:
                out.append({"start": seg["start"], "end": s,
                            "state": seg["state"]})
            out.append({"start": max(seg["start"], s),
                        "end": min(seg["end"], e), "state": state})
            if seg["end"] > e:
                out.append({"start": e, "end": seg["end"],
                            "state": seg["state"]})
        out.sort(key=lambda x: x["start"])
        return out

    # ── Clip assignment ──────────────────────────────────────────────

    def _clips_for(self, state: str) -> List[Dict]:
        for cat in FALLBACK.get(state, FALLBACK["talking"]):
            if self.library.get(cat):
                return self.library[cat]
        return [c for v in self.library.values() for c in v]

    def _word_gap_near(self, t: float) -> Optional[float]:
        """Nearest word boundary (gap between words) within SNAP_WINDOW."""
        best, best_d = None, SNAP_WINDOW
        for w in self.words:
            for edge in (float(w.get("start", 0)), float(w.get("end", 0))):
                d = abs(edge - t)
                if d < best_d:
                    # Only snap to an edge that is not inside another word
                    inside = any(x.get("start", 0) < edge < x.get("end", 0)
                                 for x in self.words if x is not w)
                    if not inside:
                        best, best_d = edge, d
        return best

    def _assign_clips(self, states: List[Dict]) -> List[Dict]:
        """Cut each state into beats and pick a clip per beat."""
        plan: List[Dict] = []
        prev_clip_path = None
        for seg in states:
            s, e, state = seg["start"], seg["end"], seg["state"]
            # Beat boundaries inside long states, snapped to word gaps.
            cuts = [s]
            t = s + BEAT
            while t < e - 1.5:
                snap = self._word_gap_near(t)
                cuts.append(snap if snap is not None and s < snap < e else t)
                t += BEAT
            cuts.append(e)

            clips = self._clips_for(state)
            for c0, c1 in zip(cuts, cuts[1:]):
                if c1 - c0 <= 1e-3:
                    continue
                pool = [c for c in clips if c["path"] != prev_clip_path]
                clip = self._rng.choice(pool or clips)
                offset = 0.0
                if clip["duration"] > (c1 - c0) + 0.5:
                    offset = self._rng.uniform(
                        0.0, clip["duration"] - (c1 - c0) - 0.25)
                plan.append({"start": c0, "end": c1, "state": state,
                             "clip": clip, "offset": offset})
                prev_clip_path = clip["path"]
        return plan

    def describe_plan(self) -> str:
        rows = [f"{'start':>7} {'end':>7}  {'state':9}  clip"]
        for p in self.plan:
            rows.append(f"{p['start']:>7.2f} {p['end']:>7.2f}  "
                        f"{p['state']:9}  {Path(p['clip']['path']).name}"
                        f" (+{p['offset']:.1f}s)")
        return "\n".join(rows)

    # ── Frame serving ────────────────────────────────────────────────

    def _entry_for(self, t: float) -> Dict:
        t = max(0.0, min(t, self.duration))
        for p in reversed(self.plan):
            if t >= p["start"] - 1e-6:
                return p
        return self.plan[0]

    def _read_frame(self, clip: Dict, frame_idx: int) -> np.ndarray:
        frame_idx = max(0, min(frame_idx, clip["frames"] - 1))
        if self._cap_path != clip["path"]:
            if self._cap is not None:
                self._cap.release()
            self._cap = cv2.VideoCapture(clip["path"])
            self._cap_path = clip["path"]
            self._cap_frame_idx = 0
        if frame_idx == self._cap_frame_idx - 1 and self._last_frame is not None:
            return self._last_frame
        if frame_idx < self._cap_frame_idx or \
                frame_idx - self._cap_frame_idx > 10:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            self._cap_frame_idx = frame_idx
        frame = None
        while self._cap_frame_idx <= frame_idx:
            ok, frame = self._cap.read()
            if not ok:
                break
            self._cap_frame_idx += 1
        if frame is None:
            if self._last_frame is not None:
                return self._last_frame
            return np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self._last_frame = frame
        return frame

    def _fit(self, frame: np.ndarray) -> np.ndarray:
        fh, fw = frame.shape[:2]
        if (fw, fh) != (self.width, self.height):
            scale = max(self.width / fw, self.height / fh)
            nw, nh = int(round(fw * scale)), int(round(fh * scale))
            frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
            x0, y0 = (nw - self.width) // 2, (nh - self.height) // 2
            frame = frame[y0:y0 + self.height, x0:x0 + self.width]
        return frame

    def get_frame(self, t: float) -> np.ndarray:
        """RGB uint8 (height, width, 3) character frame at global time t."""
        entry = self._entry_for(t)
        clip = entry["clip"]
        local = entry["offset"] + (t - entry["start"])
        # Loop the clip if the beat outlasts it (talking loops naturally)
        local = local % max(clip["duration"] - 1e-3, 1e-3)
        frame = self._read_frame(clip, int(local * clip["fps"]))
        return cv2.cvtColor(self._fit(frame), cv2.COLOR_BGR2RGB)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._cap_path = None

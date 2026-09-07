"""Video-clip library background — plays real mp4 clips as the frame background.

Scans a directory recursively for *.mp4 clips, builds a shuffled playlist
that covers the requested duration, and serves RGB frames by time.
Optimized for sequential reads (one open cv2.VideoCapture at a time).
"""

import logging
import random
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ClipLibraryBackground:
    """Serves background frames from a library of mp4 clips.

    Args:
        clips_dir: Directory scanned recursively for *.mp4 files.
        width: Output frame width.
        height: Output frame height.
        duration: Total video duration to cover (seconds).
        seed: Optional shuffle seed for reproducible playlists.
        video_type: Which layout's text zone the readability band covers.
        dim: FLAT darkening of every pixel. Defaults to 0.0 now — see below.
        scrim: Band strength, or None to measure the clips and derive it.

    READABILITY: A MEASURED BAND, NOT A FLAT DIM.

    `dim` used to default to 0.35 and darken every pixel of every frame. The
    P1 contact sheet showed that failing in both directions at once:

      · technology videos rendered BLACK. Night city, a server room and
        fibre optic cables are already dark, and 35% off the whole frame
        left nothing to see — the same black-frame outcome F3 hit with
        generated images, reached by a different route.
      · the faded quiz option cards died over BRIGHT footage — tomatoes
        under a spray, a kitten on a pale floor — where 35% was nowhere
        near enough.

    One constant cannot fix both, because the two failures pull in opposite
    directions. What works is what F3 already established: darken only the
    rows that carry text and leave the picture alone. Brightness outside the
    text zone is not a readability problem — it is the footage we went and
    fetched.

    So the flat dim defaults to zero, and the band is the raised cosine from
    clip_contrast.scrim_profile — the SAME function topic_background uses on
    stills, imported rather than reimplemented. Its strength is solved from
    a measurement of these actual clips (clip_contrast.treatment_for_dir),
    sampled across each clip's duration and sized for the worst moment any
    of them reaches, so a cut to a brighter clip cannot surprise it.

    TWO TREATMENTS, BECAUSE THE BAND CANNOT REACH THE BRAND MARK.

    The watermark is white text at rows 1555..1609. The band ends at 1450 on
    quiz and at 1060 on educational, so on three of six types the mark is
    outside the band AND its feather. Widening the band to cover it would
    darken the bottom of every video — the flat dim's mistake again.

    So there is a second, LOCAL scrim over the mark's own box, solved the
    same way from the same samples but against white. It multiplies a
    507x214 rectangle rather than the frame, and on footage dark enough to
    carry the mark already it solves to zero and touches nothing.
    """

    def __init__(self, clips_dir: str, width: int, height: int,
                 duration: float, seed: int = None, dim: float = 0.0,
                 video_type: str = None, scrim: float = None):
        self.clips_dir = Path(clips_dir)
        self.width = width
        self.height = height
        self.duration = duration
        self.dim = dim
        self.video_type = video_type

        clip_paths = sorted(self.clips_dir.rglob("*.mp4"))
        if not clip_paths:
            raise ValueError(
                f"No .mp4 clips found in '{self.clips_dir}' (searched recursively). "
                "Add clips or point the 'clips' background to another directory."
            )

        # Probe real duration/fps of each clip once
        self._clips = []  # list of dicts: path, duration, fps, frames
        for p in clip_paths:
            cap = cv2.VideoCapture(str(p))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            cap.release()
            if frames <= 0 or fps <= 0:
                logger.warning("Skipping unreadable clip: %s", p)
                continue
            self._clips.append({
                "path": str(p),
                "fps": fps,
                "frames": frames,
                "duration": frames / fps,
            })

        if not self._clips:
            raise ValueError(f"No readable .mp4 clips in '{self.clips_dir}'")

        # Build playlist: shuffle and repeat until it covers duration
        rng = random.Random(seed)
        self._playlist = []  # list of (clip, start_t) entries
        t = 0.0
        while t < duration:
            batch = list(self._clips)
            rng.shuffle(batch)
            for clip in batch:
                self._playlist.append({"clip": clip, "start": t})
                t += clip["duration"]
                if t >= duration:
                    break

        logger.info("Clip background: %d clips, playlist of %d entries covering %.1fs",
                    len(self._clips), len(self._playlist), t)

        # ── the readability band ──
        # Measurement is one decode pass over each clip at 0.5s and happens
        # once per video, not per frame. Both zones come off the same
        # decoded frames, so measuring the mark as well is free.
        from clip_contrast import (VIDEO_HEIGHT, VIDEO_WIDTH, mark_profile,
                                   mark_rect, scrim_profile, text_zone,
                                   treatment_for_dir)

        self.zone = text_zone(video_type)
        # Measured even when the caller pins the band, because `scrim=` pins
        # the BAND — the mark is a different zone measured against a
        # different colour, and letting a pinned band switch it off silently
        # is how it shipped illegible in the first place.
        plan = treatment_for_dir(self.clips_dir, video_type,
                                 band_strength=scrim)
        self.contrast_report = plan
        self.scrim = plan["strength"]
        self.mark_scrim = plan["mark_strength"]
        logger.info(
            "Clip background: band %.3f for %s (worst %.2f:1 untreated "
            "on %s at t=%.1fs, %d clips sampled every %.1fs)",
            self.scrim, video_type or "unknown",
            plan["worst_contrast"] or 0.0,
            Path(plan.get("worst_clip") or "-").name,
            plan.get("worst_at") or 0.0, len(plan["clips"]), plan["interval"])
        logger.info(
            "Clip background: watermark scrim %.3f over %s (worst %.2f:1 "
            "untreated, %.2f:1 treated, band already credited %.3f)",
            self.mark_scrim, plan.get("mark_rect"),
            plan.get("mark_worst_contrast") or 0.0,
            plan.get("mark_treated_contrast") or 0.0,
            plan.get("mark_band_credit") or 1.0)
        if not plan.get("mark_meets_floor", True):
            logger.warning(
                "Clip background: the watermark still reads %.2f:1 after "
                "treatment — below the %.1f floor",
                plan.get("mark_treated_contrast") or 0.0, 3.0)

        # Precomputed once. Per-frame this is one broadcast multiply.
        self._scrim = (scrim_profile(self.height, self.zone,
                                     strength=self.scrim)
                       if self.scrim > 0 else None)

        # The mark's patch is LOCAL, so it is stored as its own rectangle and
        # multiplied into that slice only — 507x214 pixels rather than the
        # 1080x1920 the band has to touch.
        #
        # Only on the canonical canvas. mark_rect() is in absolute 1920-row
        # coordinates because the mark itself is — brand.py positions it off
        # SAFE_AREA_BOTTOM, not off a fraction of the frame — so on any other
        # size the rows to darken are not where the mark is drawn anyway. The
        # band scales (scrim_profile takes a height) and this deliberately
        # does not; skipping is honest, and slicing would be a shape mismatch
        # in the middle of a render.
        canonical = (self.width, self.height) == (VIDEO_WIDTH, VIDEO_HEIGHT)
        if self.mark_scrim > 0 and not canonical:
            logger.warning(
                "Clip background: watermark scrim %.3f NOT applied — canvas "
                "is %dx%d, and the mark's box is fixed to %dx%d",
                self.mark_scrim, self.width, self.height,
                VIDEO_WIDTH, VIDEO_HEIGHT)
        apply_mark = self.mark_scrim > 0 and canonical
        self._mark_rect = mark_rect() if apply_mark else None
        self._mark = mark_profile(strength=self.mark_scrim) if apply_mark else None

        # Sequential-read state
        self._cap = None
        self._cap_path = None
        self._cap_frame_idx = -1  # index of the NEXT frame cap.read() returns
        self._last_frame = None

    def _entry_for(self, t: float):
        """Find playlist entry and local time for global time t."""
        t = max(0.0, t)
        for entry in reversed(self._playlist):
            if t >= entry["start"] - 1e-6:
                local_t = min(t - entry["start"], entry["clip"]["duration"] - 1e-3)
                return entry["clip"], local_t
        return self._playlist[0]["clip"], 0.0

    def _read_frame(self, clip: dict, frame_idx: int) -> np.ndarray:
        """Read a frame, keeping the capture open for sequential access."""
        frame_idx = max(0, min(frame_idx, clip["frames"] - 1))

        if self._cap_path != clip["path"]:
            if self._cap is not None:
                self._cap.release()
            self._cap = cv2.VideoCapture(clip["path"])
            self._cap_path = clip["path"]
            self._cap_frame_idx = 0

        # Same frame as last time — reuse it
        if frame_idx == self._cap_frame_idx - 1 and self._last_frame is not None:
            return self._last_frame

        # Backwards or a large forward jump — seek directly
        if frame_idx < self._cap_frame_idx or frame_idx - self._cap_frame_idx > 10:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            self._cap_frame_idx = frame_idx

        # Advance sequentially to the target frame
        frame = None
        while self._cap_frame_idx <= frame_idx:
            ok, frame = self._cap.read()
            if not ok:
                break
            self._cap_frame_idx += 1

        if frame is None:
            # Decode hiccup — fall back to last good frame or black
            if self._last_frame is not None:
                return self._last_frame
            return np.zeros((self.height, self.width, 3), dtype=np.uint8)

        self._last_frame = frame
        return frame

    def _fit(self, frame: np.ndarray) -> np.ndarray:
        """Scale + center-crop a BGR frame to (width, height), keeping aspect."""
        fh, fw = frame.shape[:2]
        if (fw, fh) != (self.width, self.height):
            scale = max(self.width / fw, self.height / fh)
            new_w, new_h = int(round(fw * scale)), int(round(fh * scale))
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            x0 = (new_w - self.width) // 2
            y0 = (new_h - self.height) // 2
            frame = frame[y0:y0 + self.height, x0:x0 + self.width]
        return frame

    def get_frame(self, t: float) -> np.ndarray:
        """Return the RGB uint8 background frame (height, width, 3) at time t."""
        clip, local_t = self._entry_for(t)
        frame_idx = int(local_t * clip["fps"])
        frame = self._read_frame(clip, frame_idx)
        frame = self._fit(frame)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if self.dim <= 0 and self._scrim is None and self._mark is None:
            return rgb

        out = rgb.astype(np.float32)
        if self.dim > 0:
            # Still honoured when a caller asks for it explicitly, so
            # "clips" with background_options can pin a flat dim. Nothing
            # sets it by default any more.
            out *= (1.0 - self.dim)
        if self._scrim is not None:
            out *= self._scrim
        if self._mark is not None:
            # In place, on the mark's rectangle only. The band's contribution
            # over these rows was already credited when mark_scrim was
            # solved, so the two multiply to the solved total rather than
            # stacking past it.
            x0, y0, x1, y1 = self._mark_rect
            out[y0:y1, x0:x1] *= self._mark
        return np.clip(out, 0, 255).astype(np.uint8)

    def close(self):
        """Release the open video capture."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._cap_path = None

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
        dim: Black-overlay strength (0-1) so overlaid text stays readable.
    """

    def __init__(self, clips_dir: str, width: int, height: int,
                 duration: float, seed: int = None, dim: float = 0.35):
        self.clips_dir = Path(clips_dir)
        self.width = width
        self.height = height
        self.duration = duration
        self.dim = dim

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
        if self.dim > 0:
            rgb = (rgb.astype(np.float32) * (1.0 - self.dim)).astype(np.uint8)
        return rgb

    def close(self):
        """Release the open video capture."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._cap_path = None

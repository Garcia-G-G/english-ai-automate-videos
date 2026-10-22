"""
PIL + FFmpeg video compositor.

Pre-renders all frames with PIL, then pipes raw RGB to FFmpeg for
H.264 encoding.  Significantly faster than the MoviePy approach
because it avoids per-frame Python ↔ MoviePy overhead and lets
FFmpeg handle muxing/encoding in a single pass.
"""

import logging
import os
import subprocess
import time as _time
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)


#: STEP 75 §4: one software encode. VideoToolbox at -q:v 65 gave 2.7 Mb/s, no B-frames
#: and a keyframe every 0.4 s on a mostly still card; colour went out untagged, so
#: players guessed BT.601 and shifted the brand colours.
X264_PARAMS = ["-g", "60", "-bf", "3", "-profile:v", "high"]
# setparams too: on ffmpeg 9 the frames' own (unset) primaries/trc win over -color_primaries
# and -color_trc, so without it the file says bt709/unknown/unknown.
BT709_FILTER = ("scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int,"
                "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv")
BT709_TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]


def render_video_ffmpeg(
    frame_generator: Callable[[float], np.ndarray],
    audio_path: str,
    output_path: str,
    duration: float,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    crf: int = 17,
    preset: str = "slow",
    progress_callback: Optional[Callable[[float], None]] = None,
    workers: int = 1,
) -> str:
    """Render video by piping PIL frames to FFmpeg (libx264, BT.709).

    Args:
        frame_generator: ``f(t: float) -> np.ndarray`` returning an
            RGB uint8 array of shape ``(height, width, 3)``.
        audio_path: Path to the audio file to mux in.
        output_path: Destination ``.mp4`` path.
        duration: Video duration in seconds.
        fps: Frames per second.
        width, height: Expected frame dimensions.
        crf: libx264 CRF (17: transparent for flat cards and text).
        preset: libx264 preset; ``ultrafast`` only for --fast drafts.
        progress_callback: Called with a float in ``[0, 1]`` once per
            second of rendered video.
        workers: Processes that render frames (STEP 77 §2). Above 1 the
            frame_generator runs in forked processes over contiguous chunks
            of frames, written to ffmpeg in order; it must be a pure
            function of t, as every renderer here already is.

    Returns:
        *output_path* on success.

    Raises:
        RuntimeError: If FFmpeg exits non-zero or closes its input early.
    """
    total_frames = int(duration * fps)
    if total_frames <= 0:
        raise ValueError(f"Invalid duration ({duration}) or fps ({fps})")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    return _encode(
        frame_generator, audio_path, output_path,
        total_frames, fps, width, height,
        codec="libx264",
        extra_params=["-crf", str(crf), "-preset", preset, *X264_PARAMS],
        progress_callback=progress_callback,
        workers=workers,
    )


# ── frames, in one process or several (STEP 77 §2) ──────────────────

_POOL_GENERATOR: Optional[Callable[[float], np.ndarray]] = None


def _pool_frame(args) -> np.ndarray:
    index, fps = args
    frame = _POOL_GENERATOR(index / fps)
    if frame.dtype != np.uint8:
        frame = np.clip(frame, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(frame)


def frames(frame_generator: Callable[[float], np.ndarray], total_frames: int, fps: int,
           workers: int = 1):
    """Every frame in order. With workers > 1, forked processes render contiguous chunks
    (each keeps its own caches and reads the footage forward); a semaphore holds back the
    task feed so finished frames never pile up faster than ffmpeg takes them."""
    import multiprocessing
    import threading
    if workers <= 1 or "fork" not in multiprocessing.get_all_start_methods():
        for i in range(total_frames):
            yield frame_generator(i / fps)
        return
    global _POOL_GENERATOR
    _POOL_GENERATOR = frame_generator
    # Warm up once here so the children inherit the background (softened clips, scrims), the
    # static pages and the font caches instead of each building them: that setup cost every
    # worker more than its frames did (~0.5 CPU-s per frame with 6 workers, 0.04 without).
    frame_generator(0.0)
    from .backgrounds import before_fork
    before_fork()
    try:
        import cv2
        cv2.setNumThreads(1)                     # six processes already; no thread pool per process
    except ImportError:
        pass
    chunk = max(1, min(60, total_frames // (workers * 6)))
    ahead = threading.Semaphore(workers * chunk * 2)
    stop = threading.Event()

    def tasks():
        for i in range(total_frames):
            ahead.acquire()
            if stop.is_set():                    # the render ended early: feed nothing more
                return
            yield (i, fps)

    logger.info("Rendering frames in %d processes, chunks of %d", workers, chunk)
    pool = multiprocessing.get_context("fork").Pool(workers)
    try:
        for frame in pool.imap(_pool_frame, tasks(), chunksize=chunk):
            ahead.release()
            yield frame
        pool.close()
    finally:
        # A failed frame (or a dead ffmpeg) ends the render: unblock the task feed first, or
        # terminate() waits forever on the thread parked in ahead.acquire().
        stop.set()
        for _ in range(workers * chunk * 2 + 1):
            ahead.release()
        pool.terminate()
        pool.join()


def render_workers() -> int:
    """Processes for a render: VIDEO_RENDER_WORKERS, else the cores minus two for ffmpeg and
    the panel, at most 6."""
    env = os.environ.get("VIDEO_RENDER_WORKERS")
    if env:
        return max(1, int(env))
    return max(1, min(6, (os.cpu_count() or 2) - 2))


def _encode(
    frame_generator: Callable[[float], np.ndarray],
    audio_path: str,
    output_path: str,
    total_frames: int,
    fps: int,
    width: int,
    height: int,
    codec: str,
    extra_params: list,
    progress_callback: Optional[Callable[[float], None]],
    workers: int = 1,
) -> str:
    """Run the actual FFmpeg pipe encode."""

    cmd = [
        "ffmpeg", "-y",
        # Quiet stderr: stats/progress lines can fill the un-drained
        # stderr PIPE (64KB) mid-encode and deadlock the whole pipeline.
        "-nostats", "-loglevel", "error",
        # --- raw video from stdin ---
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "rgb24",
        "-r", str(fps),
        "-i", "-",
        # --- audio file ---
        "-i", audio_path,
        # --- video codec ---
        "-vf", BT709_FILTER,
        "-c:v", codec,
        *extra_params,
        "-pix_fmt", "yuv420p",
        *BT709_TAGS,
        # --- audio codec ---
        "-c:a", "aac",
        "-b:a", "192k",
        # --- general ---
        "-movflags", "+faststart",
        "-shortest",
        # No thread cap (was 4): x264 slow at 1080x1920 encodes 54 fps with 4, 60 with its own
        # count, and the encoder is a render's longest stage once frames come from a pool (STEP 77 §2).
        output_path,
    ]

    logger.info("Encoding: %s (%d frames @ %d fps)", codec, total_frames, fps)

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    t_start = _time.time()
    t_last = t_start

    try:
        for frame_num, frame_rgb in enumerate(frames(frame_generator, total_frames, fps, workers)):

            # Progress every 100 frames. A timeout that shows these lines
            # advancing was slow; one that shows them stop dead was stalled.
            if frame_num and frame_num % 100 == 0:
                now = _time.time()
                logger.info(
                    "  frame %d/%d (%.0f%%) elapsed=%.1fs last100=%.4f s/frame "
                    "avg=%.4f s/frame eta=%.0fs",
                    frame_num, total_frames, 100.0 * frame_num / total_frames,
                    now - t_start, (now - t_last) / 100,
                    (now - t_start) / frame_num,
                    (now - t_start) / frame_num * (total_frames - frame_num),
                )
                t_last = now

            if frame_rgb.shape[:2] != (height, width):
                raise ValueError(
                    f"Frame {frame_num} has shape {frame_rgb.shape[:2]}, "
                    f"expected ({height}, {width})"
                )

            if frame_rgb.dtype != np.uint8:
                frame_rgb = np.clip(frame_rgb, 0, 255).astype(np.uint8)

            # Ensure contiguous memory for .tobytes()
            if not frame_rgb.flags["C_CONTIGUOUS"]:
                frame_rgb = np.ascontiguousarray(frame_rgb)

            try:
                process.stdin.write(frame_rgb.tobytes())
            except BrokenPipeError:
                # ffmpeg died mid-encode; its own words say why, the pipe does not.
                process.kill()
                err_tail = process.stderr.read().decode(errors="replace")[-800:]
                process.wait()
                logger.error("FFmpeg closed its input at frame %d (rc=%s): …%s",
                             frame_num, process.returncode, err_tail)
                raise RuntimeError(f"FFmpeg stopped reading frames at {frame_num}/{total_frames} "
                                   f"(rc={process.returncode}): {err_tail.strip()[-300:]}") from None

            if progress_callback and frame_num % fps == 0:
                progress_callback(frame_num / total_frames)

        process.stdin.close()
        stderr = process.stderr.read()
        process.wait(timeout=300)

        if process.returncode != 0:
            err_tail = stderr.decode(errors="replace")[-500:]
            logger.error("FFmpeg failed (rc=%d): …%s", process.returncode, err_tail)
            raise RuntimeError(
                f"FFmpeg encoding failed (codec={codec}, rc={process.returncode}). "
                "Try --renderer moviepy as a fallback."
            )

        elapsed = _time.time() - t_start
        render_fps = total_frames / elapsed if elapsed > 0 else 0
        from . import peak_rss_mb
        logger.info(
            "RENDER DONE %s (%.1fs, %.0f fps, %.4f s/frame, peak_rss=%.0fMB)",
            output_path, elapsed, render_fps, elapsed / total_frames,
            peak_rss_mb(),
        )
        return output_path

    except Exception:
        process.kill()
        process.wait()
        raise

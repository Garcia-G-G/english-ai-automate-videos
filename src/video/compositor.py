"""
PIL + FFmpeg video compositor.

Pre-renders all frames with PIL, then pipes raw RGB to FFmpeg for
H.264 encoding.  Significantly faster than the MoviePy approach
because it avoids per-frame Python ↔ MoviePy overhead and lets
FFmpeg handle muxing/encoding in a single pass.
"""

import logging
import os
import platform
import subprocess
import time as _time
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)


def render_video_ffmpeg(
    frame_generator: Callable[[float], np.ndarray],
    audio_path: str,
    output_path: str,
    duration: float,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    crf: int = 18,
    preset: str = "medium",
    use_hardware: bool = True,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> str:
    """Render video by piping PIL frames to FFmpeg.

    Args:
        frame_generator: ``f(t: float) -> np.ndarray`` returning an
            RGB uint8 array of shape ``(height, width, 3)``.
        audio_path: Path to the audio file to mux in.
        output_path: Destination ``.mp4`` path.
        duration: Video duration in seconds.
        fps: Frames per second.
        width, height: Expected frame dimensions.
        crf: FFmpeg CRF quality (lower = better, 18 ≈ visually
            lossless for libx264).
        preset: FFmpeg encoding preset (``ultrafast`` … ``veryslow``).
            Ignored when hardware encoding is active.
        use_hardware: Attempt macOS VideoToolbox hardware encoding
            before falling back to libx264.
        progress_callback: Called with a float in ``[0, 1]`` once per
            second of rendered video.

    Returns:
        *output_path* on success.

    Raises:
        RuntimeError: If FFmpeg exits with a non-zero code and no
            fallback is available.
    """
    total_frames = int(duration * fps)
    if total_frames <= 0:
        raise ValueError(f"Invalid duration ({duration}) or fps ({fps})")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Decide codec
    is_mac = platform.system() == "Darwin"
    try_hw = use_hardware and is_mac

    if try_hw:
        try:
            return _encode(
                frame_generator, audio_path, output_path,
                total_frames, fps, width, height,
                codec="h264_videotoolbox",
                extra_params=["-q:v", "65"],
                progress_callback=progress_callback,
            )
        except RuntimeError:
            logger.warning(
                "Hardware encoding (VideoToolbox) failed, "
                "falling back to libx264"
            )

    return _encode(
        frame_generator, audio_path, output_path,
        total_frames, fps, width, height,
        codec="libx264",
        extra_params=["-crf", str(crf), "-preset", preset],
        progress_callback=progress_callback,
    )


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
) -> str:
    """Run the actual FFmpeg pipe encode."""

    cmd = [
        "ffmpeg", "-y",
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
        "-c:v", codec,
        *extra_params,
        "-pix_fmt", "yuv420p",
        # --- audio codec ---
        "-c:a", "aac",
        "-b:a", "192k",
        # --- general ---
        "-shortest",
        "-threads", "4",
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

    try:
        for frame_num in range(total_frames):
            t = frame_num / fps

            frame_rgb = frame_generator(t)

            if frame_rgb.dtype != np.uint8:
                frame_rgb = np.clip(frame_rgb, 0, 255).astype(np.uint8)

            # Ensure contiguous memory for .tobytes()
            if not frame_rgb.flags["C_CONTIGUOUS"]:
                frame_rgb = np.ascontiguousarray(frame_rgb)

            process.stdin.write(frame_rgb.tobytes())

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
        logger.info(
            "Video rendered: %s (%.1fs, %.0f fps)",
            output_path, elapsed, render_fps,
        )
        return output_path

    except Exception:
        process.kill()
        process.wait()
        raise

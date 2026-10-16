import subprocess

import numpy as np


def test_synthetic_local_compositor_has_duration_frames_portrait_and_audio(tmp_path):
    from studio.media_validation import inspect_frames, probe_media, validate_video
    from video.compositor import render_video_ffmpeg

    audio = tmp_path / "tone.wav"
    video = tmp_path / "synthetic.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-nostats", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=0.6", str(audio)],
        check=True,
    )

    def frame(t):
        image = np.zeros((1920, 1080, 3), dtype=np.uint8)
        image[:, :, 1] = 35
        left = min(900, int(100 + t * 900))
        image[760:1160, left:left + 120] = (255, 220, 40)
        return image

    render_video_ffmpeg(frame, str(audio), str(video), 0.6, fps=5,
                        width=1080, height=1920, preset="ultrafast",
                        use_hardware=False)
    probe = probe_media(video)
    frames = inspect_frames(video)
    validate_video(probe, frames, 0.6)

    assert probe["duration"] > 0
    assert probe["audio_streams"] == probe["video_streams"] == 1
    assert (probe["width"], probe["height"]) == (1080, 1920)
    assert frames == {"nonblank": True, "changing": True}

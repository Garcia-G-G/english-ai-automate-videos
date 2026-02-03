"""
Video Generator for English AI Videos — Multi-Type Support
Supports: educational, quiz, true_false, fill_blank, pronunciation

Public API: generate_video(), main(), set_background(), reset_background()
"""

import argparse
import logging
import os
import sys

from animations.subtitle_processor import SubtitleProcessor

from .constants import FPS, VIDEO_WIDTH, VIDEO_HEIGHT
from .backgrounds import (
    set_background, reset_background, get_background_generator,
    get_default_background, BACKGROUNDS_AVAILABLE,
    CURRENT_BACKGROUND,
)
from .utils import load_data
from .educational import create_frame_educational, add_sentence_boundaries
from .karaoke import create_frame_karaoke
from .quiz import create_frame_quiz, parse_quiz_timestamps, resolve_quiz_timestamps
from .true_false import create_frame_true_false, resolve_true_false_timestamps
from .fill_blank import create_frame_fill_blank
from .pronunciation import create_frame_pronunciation

# Re-export for backwards compatibility
try:
    from backgrounds import BACKGROUND_PRESETS, get_recommended_preset
except ImportError:
    BACKGROUND_PRESETS = {}
    def get_recommended_preset():
        return None

logger = logging.getLogger(__name__)


def generate_video(
    audio_path: str,
    data_path: str,
    output_path: str,
    video_type: str = None,
    fps: int = FPS,
    background: str = None,
    background_options: dict = None,
    fast_mode: bool = False,
    renderer: str = "ffmpeg",
    karaoke_mode: bool = False,
) -> str:
    """
    Generate video based on type.

    Args:
        audio_path: Path to audio file
        data_path: Path to JSON data file
        output_path: Output video path
        video_type: Video type (educational, quiz, etc.)
        fps: Frames per second
        background: Background preset name or type
        background_options: Custom background options
        fast_mode: Use static background and optimized settings for speed
        renderer: "ffmpeg" (fast, default) or "moviepy" (legacy fallback)
        karaoke_mode: Use karaoke-style renderer with inline translations
    """

    logger.info(f"Loading audio: {audio_path}")

    # Get duration without importing MoviePy when using ffmpeg renderer
    if renderer == "ffmpeg":
        from tts_common import get_audio_duration
        duration = get_audio_duration(audio_path)
    else:
        from moviepy import AudioFileClip
        audio = AudioFileClip(audio_path)
        duration = audio.duration

    logger.info(f"Loading data: {data_path}")
    data = load_data(data_path)

    # Configure background with pre-rendering for speed
    if background:
        if BACKGROUNDS_AVAILABLE and background in BACKGROUND_PRESETS:
            set_background(preset=background, duration=duration)
            logger.info(f"Background: {background} (preset)")

            bg = get_background_generator()
            if bg:
                import time as _time
                _bg_start = _time.time()

                if fast_mode:
                    logger.info("Fast mode: rendering static background...")
                    bg.render_static_once(background)
                    logger.info(f"Background rendered in {_time.time() - _bg_start:.1f}s")
                else:
                    logger.info("Pre-rendering background loop...")
                    loop_duration = min(5.0, duration)
                    bg.pre_render_loop(background, loop_duration=loop_duration, show_progress=False)
                    logger.info(f"Background pre-rendered in {_time.time() - _bg_start:.1f}s")

        elif BACKGROUNDS_AVAILABLE:
            set_background(bg_type=background, options=background_options or {}, duration=duration)
            logger.info(f"Background: {background} (custom)")
        else:
            logger.warning("Background system not available, using legacy gradient")
    else:
        reset_background()
        logger.info("Background: legacy gradient")

    # Determine video type
    if video_type is None:
        video_type = data.get('type', 'educational')

    logger.info(f"Video type: {video_type}")
    logger.info(f"Duration: {duration:.2f}s")

    # Create appropriate frame generator
    if video_type == 'educational':
        words = data.get('words', [])

        processor = SubtitleProcessor()
        if not words:
            segments = data.get('segments', [])
            if segments:
                logger.info("No word timestamps found, estimating from segments...")
                english_phrases = data.get('english_phrases', [])
                words = processor.estimate_words_from_segments(segments, english_phrases)
                logger.info(f"Estimated {len(words)} word timestamps from {len(segments)} segments")
            else:
                logger.error("No word timestamps or segments found for educational video!")
                return None

        full_script = data.get('full_script', '')
        words = add_sentence_boundaries(words, full_script)

        groups = processor.group_words(words)
        translations = data.get('translations', {})
        logger.info(f"Phrase groups: {len(groups)}")

        for i, g in enumerate(groups):
            seg_ids = set(w.get('segment_id', '?') for w in g.get('words', []))
            logger.debug(f"{i+1}. [{g['start']:.2f}s-{g['end']:.2f}s] seg={seg_ids} \"{g['text']}\"")

        if karaoke_mode:
            logger.info("Using karaoke-style renderer with inline translations")
            def frame_gen(t):
                return create_frame_karaoke(t, words, duration, translations, full_script)
        else:
            def frame_gen(t):
                return create_frame_educational(t, groups, duration, translations)

    elif video_type == 'quiz':
        logger.info(f"Question: {data.get('question', 'N/A')}")
        logger.info(f"Options: {data.get('options', {})}")
        logger.info(f"Correct: {data.get('correct', 'N/A')}")

        # Ensure segment_times is populated (exact TTS or keyword fallback)
        data = resolve_quiz_timestamps(data, duration)

        st = data.get('segment_times', {})
        for key in ('option_a', 'option_b', 'option_c', 'option_d', 'countdown_3', 'answer'):
            if key in st:
                logger.debug(f"{key}: {st[key].get('start', 0):.2f}s")

        def frame_gen(t):
            return create_frame_quiz(t, data, duration)

    elif video_type == 'true_false':
        logger.info(f"Statement: {data.get('statement', 'N/A')}")
        logger.info(f"Correct: {data.get('correct', 'N/A')}")

        data = resolve_true_false_timestamps(data, duration)

        def frame_gen(t):
            return create_frame_true_false(t, data, duration)

    elif video_type == 'fill_blank':
        logger.info(f"Sentence: {data.get('sentence', 'N/A')}")
        logger.info(f"Options: {data.get('options', [])}")
        logger.info(f"Correct: {data.get('correct', 'N/A')}")

        def frame_gen(t):
            return create_frame_fill_blank(t, data, duration)

    elif video_type == 'pronunciation':
        logger.info(f"Word: {data.get('word', 'N/A')}")
        logger.info(f"Phonetic: {data.get('phonetic', 'N/A')}")

        def frame_gen(t):
            return create_frame_pronunciation(t, data, duration)

    else:
        logger.error(f"Unknown video type: {video_type}")
        return None

    logger.info("Generating video frames...")

    if renderer == "ffmpeg":
        try:
            from .compositor import render_video_ffmpeg
            return render_video_ffmpeg(
                frame_gen,
                audio_path,
                output_path,
                duration,
                fps=fps,
                width=VIDEO_WIDTH,
                height=VIDEO_HEIGHT,
                preset="ultrafast" if fast_mode else "medium",
                use_hardware=True,
            )
        except Exception as e:
            logger.warning(f"FFmpeg renderer failed: {e}")
            logger.warning("Falling back to MoviePy renderer")
            renderer = "moviepy"

    # MoviePy renderer (legacy fallback)
    from moviepy import VideoClip, AudioFileClip

    if not isinstance(audio_path, str):
        audio = audio_path
    else:
        audio = AudioFileClip(audio_path)

    video = VideoClip(frame_gen, duration=duration)
    video = video.with_fps(fps)
    video = video.with_audio(audio)

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    logger.info(f"Writing video: {output_path}")

    import platform
    if platform.system() == 'Darwin':
        try:
            video.write_videofile(
                output_path,
                fps=fps,
                codec='h264_videotoolbox',
                audio_codec='aac',
                threads=4,
                logger='bar',
                ffmpeg_params=['-q:v', '65']
            )
        except Exception as e:
            logger.warning(f"Hardware encoding failed, falling back to software: {e}")
            video.write_videofile(
                output_path,
                fps=fps,
                codec='libx264',
                audio_codec='aac',
                preset='ultrafast',
                threads=4,
                logger='bar'
            )
    else:
        video.write_videofile(
            output_path,
            fps=fps,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            threads=4,
            logger='bar'
        )

    logger.info(f"Video created: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate TikTok-style video (multi-type)")
    parser.add_argument("-a", "--audio", help="MP3 audio file")
    parser.add_argument("-d", "--data", help="JSON data file (defaults to audio path with .json)")
    parser.add_argument("-o", "--output", default="output/video/output.mp4", help="Output MP4")
    parser.add_argument("-t", "--type", choices=['educational', 'quiz', 'true_false', 'fill_blank', 'pronunciation'],
                        help="Video type (auto-detected from data if not specified)")
    parser.add_argument("--fps", type=int, default=FPS, help="FPS")
    parser.add_argument("-b", "--background", default=None,
                        help="Background preset (bokeh_soft, purple_vibes, dark_professional, etc.) or type")
    parser.add_argument("--fast", action="store_true",
                        help="Fast mode: use static background and optimized settings")
    parser.add_argument("--renderer", choices=["ffmpeg", "moviepy"], default="ffmpeg",
                        help="Rendering backend: ffmpeg (fast, default) or moviepy (legacy)")
    parser.add_argument("--karaoke", action="store_true",
                        help="Use karaoke-style renderer with inline translations")
    parser.add_argument("--list-backgrounds", action="store_true",
                        help="List available background presets")

    args = parser.parse_args()

    if args.list_backgrounds:
        if BACKGROUNDS_AVAILABLE:
            print("Available background presets:")
            for name, preset in BACKGROUND_PRESETS.items():
                print(f"  {name}: {preset['type']}")
            print(f"\nRecommended: {get_recommended_preset()}")
        else:
            print("Background system not available")
        sys.exit(0)

    if not args.audio:
        print("Error: Audio file (-a/--audio) is required", file=sys.stderr)
        sys.exit(1)

    if not args.data:
        args.data = args.audio.rsplit('.', 1)[0] + '.json'

    if not os.path.exists(args.audio):
        print(f"Error: Audio not found: {args.audio}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.data):
        print(f"Error: Data file not found: {args.data}", file=sys.stderr)
        sys.exit(1)

    background = args.background

    if args.fast:
        background = "dark_professional"
        print("Fast mode: using static background")
    elif background is None:
        background = get_default_background()

    generate_video(args.audio, args.data, args.output, args.type, args.fps, background,
                   fast_mode=args.fast, renderer=args.renderer,
                   karaoke_mode=getattr(args, 'karaoke', False))


if __name__ == "__main__":
    main()

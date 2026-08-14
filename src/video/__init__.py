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
from script_schema import validate_render_data

from .constants import FPS, VIDEO_WIDTH, VIDEO_HEIGHT
from .backgrounds import (
    set_background, reset_background, get_background_generator,
    get_default_background, BACKGROUNDS_AVAILABLE,
    CURRENT_BACKGROUND,
)
from .utils import load_data
from .educational import create_frame_educational, add_sentence_boundaries
from .karaoke import create_frame_karaoke
from .quiz import create_frame_quiz, resolve_quiz_timestamps
from .true_false import create_frame_true_false, resolve_true_false_timestamps
from .fill_blank import create_frame_fill_blank
from .pronunciation import create_frame_pronunciation
from .vocabulary import create_frame_vocabulary
from tts_common import SPANISH_FILTER  # canonical Spanish stoplist

# Re-export from top-level src/backgrounds.py (on sys.path via main.py)
try:
    from backgrounds import BACKGROUND_PRESETS, get_recommended_preset  # noqa: E402
except ImportError:
    BACKGROUND_PRESETS = {}
    def get_recommended_preset():
        return None

logger = logging.getLogger(__name__)


def peak_rss_mb() -> float:
    """Peak resident set size of this process, in MB.

    ru_maxrss is bytes on macOS/BSD and kilobytes on Linux.
    """
    import platform
    import resource
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw / (1024 * 1024) if platform.system() == "Darwin" else raw / 1024


def prepare_background_cache(bg, preset: str, duration: float,
                             fast_mode: bool = False) -> None:
    """Warm `bg` for `preset`: one frame if it is static, a loop if it moves.

    render_from_preset ignores t for a static_gradient, so pre-rendering a
    loop of them produces N byte-identical 1080x1920x3 arrays and retains all
    of them (150 frames ~ 930MB nominal). 69 of the 76 enabled presets are
    static_gradient, so the loop path was the common one.
    """
    import time as _time

    preset_type = (BACKGROUND_PRESETS.get(preset) or {}).get("type")
    static = fast_mode or preset_type == "static_gradient"

    _bg_start = _time.time()

    if static:
        logger.info("Rendering static background once (%s)...", preset_type or "fast mode")
        bg.render_static_once(preset)
        logger.info("Background rendered in %.1fs (peak RSS %.0f MB)",
                    _time.time() - _bg_start, peak_rss_mb())
        return

    logger.info("Pre-rendering background loop...")
    bg.pre_render_loop(preset, loop_duration=min(5.0, duration),
                       show_progress=False)
    logger.info("Background pre-rendered in %.1fs (peak RSS %.0f MB)",
                _time.time() - _bg_start, peak_rss_mb())


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
    engine_version: str = "v1",
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
        engine_version: "v1" (legacy renderers) or "v2" (design-system
            renderer; educational only — other types fall back to v1)
    """

    logger.info(f"Loading data: {data_path}")
    data = load_data(data_path)

    # VALIDATION POINT 3 of 3: renderer input.
    #
    # This is the last gate before pixels, and the renderers below now depend
    # on it: their plausible-wrong defaults have been deleted, so they index
    # load-bearing keys directly. `correct` used to default to 'A',
    # `sentence` to "I ___ to school", `word` to the literal string "word".
    # There is no "unknown" state anywhere in the render path, so a data
    # failure that got this far did not look like a failure — it shipped as a
    # polished, confidently incorrect lesson that no audio or visual check
    # catches, because the video is technically perfect.
    #
    # Loud is the whole point. Nothing renders unless the data is right.
    #
    # Runs BEFORE the audio probe on purpose: the cheap failure should come
    # first, and there is no reason to spend an ffprobe subprocess on a
    # script we are about to reject.
    validate_render_data(data, video_type, source=str(data_path))

    logger.info(f"Loading audio: {audio_path}")

    # Get duration without importing MoviePy when using ffmpeg renderer
    if renderer == "ffmpeg":
        from tts_common import get_audio_duration
        duration = get_audio_duration(audio_path)
    else:
        from moviepy import AudioFileClip
        audio = AudioFileClip(audio_path)
        duration = audio.duration

    # Resolve v2 engine early — v2 renders its own background, so the
    # background system below is skipped entirely when it is active.
    #
    # No default: falling back to 'educational' routed a quiz through the
    # educational renderer in silence. validate_render_data above has already
    # required `type`.
    if video_type is None:
        video_type = data['type']

    use_v2 = engine_version == "v2"
    if use_v2 and video_type != "educational":
        logger.warning(
            "v2 engine only supports 'educational' (got '%s') — falling back to v1",
            video_type)
        use_v2 = False
    if use_v2:
        background = None

    # Configure background with pre-rendering for speed
    # Auto-select from config.yaml if no background specified
    if not background and BACKGROUNDS_AVAILABLE and not use_v2:
        background = get_default_background()
        if background:
            logger.info(f"Auto-selected background: {background}")

    # Clip-library background: "clips" (with background_options) or "clips:<dir>"
    if background == "clips" or (background and background.startswith("clips:")):
        options = dict(background_options or {})
        if background.startswith("clips:"):
            options["dir"] = background.split(":", 1)[1]
        clips_dir = options.get("dir", "")
        if clips_dir and not os.path.isabs(clips_dir):
            # Resolve relative to project root (parent of src/)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            options["dir"] = os.path.join(project_root, clips_dir)
        set_background(bg_type="clips", options=options, duration=duration)
        logger.info(f"Background: clips from {options.get('dir')}")

    elif background:
        if BACKGROUNDS_AVAILABLE and background in BACKGROUND_PRESETS:
            set_background(preset=background, duration=duration)
            logger.info(f"Background: {background} (preset)")

            bg = get_background_generator()
            if bg:
                prepare_background_cache(bg, background, duration,
                                         fast_mode=fast_mode)

        elif BACKGROUNDS_AVAILABLE:
            set_background(bg_type=background, options=background_options or {}, duration=duration)
            logger.info(f"Background: {background} (custom)")
        else:
            logger.warning("Background system not available, using legacy gradient")
    else:
        reset_background()
        logger.info("Background: legacy gradient (no presets available)")

    # Determine video type (second, redundant resolution — see line 117)
    if video_type is None:
        video_type = data['type']

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
                # No default: EducationalScript requires english_phrases
                # (min_length 1), and this list drives is_english — which
                # controls both word styling and the TTS accent.
                english_phrases = data['english_phrases']
                words = processor.estimate_words_from_segments(segments, english_phrases)
                logger.info(f"Estimated {len(words)} word timestamps from {len(segments)} segments")
            else:
                logger.error("No word timestamps or segments found for educational video!")
                return None

        # Sanitize is_english flags: rebuild from english_phrases with filtering
        # This fixes bad data where entire Spanish sentences are in english_phrases
        # No default — required by EducationalScript. See above.
        english_phrases = data['english_phrases']
        if english_phrases and words:
            import re as _re
            # Was a local 194-word fork of the Spanish stoplist. All five
            # copies are now one canonical 275-word set in tts_common, whose
            # comment records why. ADD WORDS THERE, never here.
            SPANISH_COMMON = SPANISH_FILTER
            english_set = set()
            for phrase in english_phrases:
                phrase_words = phrase.lower().split()
                # Skip phrases with 4+ words — likely full Spanish sentences
                if len(phrase_words) > 3:
                    continue
                for w in phrase_words:
                    cleaned = _re.sub(r'[^\w]', '', w)
                    # Reject words with Spanish accents/ñ
                    if any(c in cleaned for c in 'áéíóúñü'):
                        continue
                    if cleaned and cleaned not in SPANISH_COMMON and len(cleaned) > 1:
                        english_set.add(cleaned)

            fixed_count = 0
            for w in words:
                w_clean = _re.sub(r'[^\w]', '', w['word']).lower()
                new_is_english = w_clean in english_set
                if w.get('is_english') != new_is_english:
                    fixed_count += 1
                w['is_english'] = new_is_english

            if fixed_count:
                logger.info(f"Sanitized is_english flags: fixed {fixed_count} words")
                logger.info(f"English words: {english_set}")

        # No default: sentence boundaries derived from '' silently drop
        # every boundary. full_script is required by the schema.
        full_script = data['full_script']
        words = add_sentence_boundaries(words, full_script)

        groups = processor.group_words(words)
        translations = data.get('translations', {})
        logger.info(f"Phrase groups: {len(groups)}")

        for i, g in enumerate(groups):
            seg_ids = set(w.get('segment_id', '?') for w in g.get('words', []))
            logger.debug(f"{i+1}. [{g['start']:.2f}s-{g['end']:.2f}s] seg={seg_ids} \"{g['text']}\"")

        # Display windows, for BOTH engines.
        #
        # timing_engine used to be reachable only from v2, so the v1 path —
        # which is what actually renders today — kept using raw audio
        # timestamps as display windows and faded a group only AFTER its end,
        # and only when no other group was active. Back-to-back groups
        # therefore popped out with no exit animation.
        #
        # It derives display_start / display_end from the audio timestamps
        # WITHOUT modifying them, and enforces the golden rule: a group never
        # leaves the screen before its last word ends + 350 ms. It replaces
        # the SubtitleProcessor end-trim removed in the same commit.
        #
        # content_end reserves the CTA tail so text never collides with it.
        from .v2 import timing_engine as TE
        cta_start = max(0.0, duration - TE.CTA_LEN)
        try:
            groups = TE.compute_display_windows(groups, duration,
                                                content_end=cta_start)
            logger.info("Timing windows (v1):\n%s", TE.debug_table(groups))
        except AssertionError:
            # validate_windows found an invariant violation. Render rather
            # than abort — but say so loudly, because it means the windows
            # are not trustworthy and the frame logic will fall back to raw
            # audio timestamps for any group missing display_start.
            logger.exception("timing_engine rejected its own windows; "
                             "falling back to raw audio timestamps")

        # Pack computed data into the data dict for uniform (t, data, duration) signature
        data['_groups'] = groups

        if use_v2:
            from .v2 import EducationalRendererV2
            try:
                from profiles import get_active_profile
                profile_name = get_active_profile().get("name", "adults")
            except Exception:
                # SAFE WITHOUT .env, deliberately. This is the except branch
                # for get_active_profile() failing, and "adults" is the
                # intended default rather than a fallback standing in for a
                # missing credential. Nothing here can silently authenticate
                # as the wrong thing.
                profile_name = os.getenv("VIDEO_PROFILE", "adults")
            logger.info(f"Engine v2 active (profile: {profile_name})")
            frame_gen = EducationalRendererV2(data, duration, profile_name)
        elif karaoke_mode:
            logger.info("Using karaoke-style renderer with inline translations")
            def frame_gen(t):
                return create_frame_karaoke(t, data, duration)
        else:
            def frame_gen(t):
                return create_frame_educational(t, data, duration)

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

    elif video_type == 'vocabulary':
        pairs = data.get('pairs', [])
        logger.info(f"Vocabulary: {len(pairs)} pairs")
        logger.info(f"Difficulty: {data.get('difficulty', 'N/A')}")

        def frame_gen(t):
            return create_frame_vocabulary(t, data, duration)

    else:
        logger.error(f"Unknown video type: {video_type}")
        return None

    # One-line render summary — if this render ever times out, the log alone
    # must say what it was doing (type, size, how many frames, how much RAM).
    logger.info(
        "RENDER START type=%s frames=%d res=%dx%d fps=%d duration=%.2fs "
        "background=%s engine=%s peak_rss=%.0fMB",
        video_type, int(duration * fps), VIDEO_WIDTH, VIDEO_HEIGHT, fps,
        duration, background or "none", "v2" if use_v2 else "v1", peak_rss_mb())

    if renderer == "ffmpeg":
        # No fallback. This used to be wrapped in a bare `except Exception`
        # that retried under MoviePy, which turned every data bug into a
        # misattributed "FFmpeg renderer failed" and hid the real error.
        # MoviePy is still reachable, but only by asking for it explicitly
        # with --renderer moviepy.
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

    # MoviePy renderer (legacy, explicit opt-in only)
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

    if output_path and os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        if file_size < 1000:
            logger.error(f"Generated video is suspiciously small ({file_size} bytes)")
            return None
        logger.info(f"Video created: {output_path} ({file_size:,} bytes)")
    else:
        logger.error(f"Video file was not created: {output_path}")
        return None

    return output_path


def main():
    # This process runs as a subprocess of main.py / admin.py. Without a
    # handler every logger.info() below is discarded, which is why the
    # 2026-04-16 render timeouts left no evidence of what they were doing.
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )

    parser = argparse.ArgumentParser(description="Generate TikTok-style video (multi-type)")
    parser.add_argument("-a", "--audio", help="MP3 audio file")
    parser.add_argument("-d", "--data", help="JSON data file (defaults to audio path with .json)")
    parser.add_argument("-o", "--output", default="output/video/output.mp4", help="Output MP4")
    parser.add_argument("-t", "--type", choices=['educational', 'quiz', 'true_false', 'fill_blank', 'pronunciation', 'vocabulary'],
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
    parser.add_argument("--v2", action="store_true",
                        help="Use the v2 render engine (educational only; "
                             "other types fall back to v1)")
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

    result = generate_video(args.audio, args.data, args.output, args.type, args.fps, background,
                            fast_mode=args.fast, renderer=args.renderer,
                            karaoke_mode=getattr(args, 'karaoke', False),
                            engine_version="v2" if getattr(args, 'v2', False) else "v1")
    if result is None:
        print("Error: Video generation failed - no output produced", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

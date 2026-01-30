# Creating TikTok-style animated subtitles in Python

**Word-by-word animated captions—the kind that "pop" in viral TikTok and YouTube Shorts content—require three core components: precise word-level timestamps, smooth animation easing, and efficient rendering.** The best Python approach combines **WhisperX** for ±20-50ms timing accuracy with **PIL/Pillow frame-by-frame rendering** composited via FFmpeg, though the emerging **pycaps** library now offers a simpler all-in-one solution with CSS styling support. Commercial tools like CapCut achieve their polish through 60fps rendering, spring-physics easing, and **100-200ms pop animations** with 10-20% scale overshoot—all reproducible in Python.

## MoviePy works for prototyping but has serious limitations

MoviePy remains the most accessible Python library for video text composition, using `TextClip` and `CompositeVideoClip` for basic overlays:

```python
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip

def create_word_clips(words_with_timestamps, fontsize=70):
    clips = []
    for word in words_with_timestamps:
        clip = TextClip(
            word["text"], fontsize=fontsize,
            font="Arial-Bold", color="white",
            stroke_color="black", stroke_width=3
        ).set_start(word["start"]).set_end(word["end"]).set_position("center")
        clips.append(clip)
    return clips
```

**The critical limitation**: TextClip is notoriously slow—creating 100+ clips can take hours for a 5-minute video. Version 2.x introduced 10x performance regressions for some operations. Text quality is mediocre compared to PIL rendering, and `crossfadein()` effects don't work reliably. MoviePy suits quick prototypes, not production pipelines.

**Manim** produces cinema-quality vector animations with built-in `Write()` and `AddTextWordByWord()` effects, but it's designed for mathematical explainers—not TikTok-style subtitle compositing. It lacks native video/audio integration and requires separate compositing steps.

**The recommended hybrid approach** for production: render text frames with PIL (superior anti-aliasing), composite with FFmpeg (fast), use pycaps if you need TikTok-specific presets.

## pycaps delivers CapCut-style results with CSS control

The **pycaps** library (github.com/francozanardi/pycaps) now offers the most direct path to professional animated captions:

```python
from pycaps import CapsPipelineBuilder

pipeline = (
    CapsPipelineBuilder()
    .with_input_video("input.mp4")
    .add_css("styles.css")  # CSS styling for subtitles
    .build()
)
pipeline.run()
```

Key features include CSS selectors like `.word-being-narrated` for karaoke highlighting, built-in templates matching TikTok aesthetics, automatic Whisper transcription, and browser-based rendering via Playwright for crisp text. This eliminates the MoviePy performance penalty while producing CapCut-quality output.

For maximum control, **Remotion** (JavaScript-based but callable from Python via subprocess) uses React components with frame-perfect `useCurrentFrame()` animation:

```javascript
// Remotion spring animation for word pop
const scale = spring({ frame, fps, config: { damping: 200, stiffness: 300 } });
return <div style={{ transform: `scale(${scale})` }}>{word}</div>;
```

## Easing functions determine whether animations feel smooth or robotic

Commercial tools achieve their "smooth" feel through spring-physics easing, not linear interpolation. The **ease-out-back** curve creates the signature TikTok "pop" effect:

```python
import math

def ease_out_back(t, overshoot=1.70158):
    """Scale overshoot then settle. t: normalized time 0-1"""
    t = t - 1
    return t * t * ((overshoot + 1) * t + overshoot) + 1

def spring_animation(t, stiffness=100, damping=10):
    """Physics-based spring for bouncy entrance"""
    w0 = math.sqrt(stiffness)
    zeta = damping / (2 * math.sqrt(stiffness))
    if zeta < 1:  # Underdamped = bouncy
        wd = w0 * math.sqrt(1 - zeta**2)
        return 1 - math.exp(-zeta * w0 * t) * math.cos(wd * t)
    return 1 - math.exp(-w0 * t) * (1 + w0 * t)
```

**Optimal timing parameters** based on commercial tool analysis:

| Animation Type | Duration | Easing | Scale Overshoot |
|---------------|----------|--------|-----------------|
| Word pop | 150-250ms | ease-out-back | 110-120% |
| Fade-in | 100-200ms | ease-out-quad | N/A |
| Slide-up | 150-300ms | ease-out-cubic | N/A |
| Karaoke highlight | 0ms transition | linear sweep | N/A |

The **pre-roll timing trick** that makes subtitles feel perfectly synced: display text **50-100ms before** the audio plays. Netflix standards require captions within 1-2 frames of audio onset.

## WhisperX provides the most accurate word timestamps

Native Whisper word timestamps have ±100-200ms accuracy—often noticeable as desync. **WhisperX** uses a two-stage pipeline (transcription + wav2vec2 forced alignment) achieving **±20-50ms accuracy**:

```python
import whisperx

# Stage 1: Transcription
model = whisperx.load_model("large-v2", device="cuda", compute_type="float16")
audio = whisperx.load_audio("video.mp4")
result = model.transcribe(audio, batch_size=16)

# Stage 2: Word-level alignment
model_a, metadata = whisperx.load_align_model(language_code="en", device="cuda")
aligned = whisperx.align(result["segments"], model_a, metadata, audio, device="cuda")

# Extract precise word timings
for segment in aligned["segments"]:
    for word in segment["words"]:
        print(f"{word['word']}: {word['start']:.3f}s - {word['end']:.3f}s")
```

**For simpler setups**, stable-ts adds silence suppression to standard Whisper, improving timing without additional models:

```python
import stable_whisper
model = stable_whisper.load_model('base')
result = model.transcribe('video.mp4', vad=True, suppress_silence=True)
```

**Accuracy comparison**: WhisperX (±20-50ms) > stable-ts/whisper-timestamped (±50-100ms) > native Whisper (±100-200ms). For karaoke-style word highlighting, WhisperX's precision is worth the extra GPU memory.

## Common bugs and prevention strategies

**Text overlapping** occurs when AI-generated timestamps have conflicting end/start times. Prevention: validate all subtitle files and implement collision detection:

```python
def fix_overlapping_timestamps(words, min_gap_ms=50):
    for i in range(1, len(words)):
        gap = words[i]["start"] - words[i-1]["end"]
        if gap < min_gap_ms / 1000:
            # Adjust previous word's end time
            words[i-1]["end"] = words[i]["start"] - (min_gap_ms / 1000)
    return words
```

**Progressive timing drift** results from frame rate mismatches. A 23.976fps video with 24fps subtitle timing drifts ~4 seconds per hour. Always match subtitle timing to actual video frame rate, and test sync at beginning, middle, and end of videos.

**Sentence boundary problems** manifest as text appearing before it's spoken (spoiling content) or overwhelming blocks. BBC guidelines: maximum 2 lines per subtitle, 37-42 characters per line, split at natural punctuation, maintain 250ms gaps between changes.

**Performance issues with complex animations** stem from real-time glow/shadow calculations. Limit effects to **under 4px blur**, pre-render complex effects, use GPU-accelerated text rendering, and object-pool text elements rather than creating/destroying per frame.

## CapCut and Captions.ai reveal the "Hormozi style" formula

Analyzing commercial tools reveals consistent patterns. **CapCut** uses ByteDance's proprietary engine with native Metal/OpenGL rendering, **real-time 60fps preview**, and pre-rendered animation templates combined with text substitution. Their "Caption Boost" presets apply spring-physics pop animations with automatic karaoke timing.

**Captions.ai's "Hormozi style"** (named after entrepreneur Alex Hormozi's viral content) consists of:
- **Font**: Montserrat Black 900, ALL CAPS
- **Colors**: White base, yellow/green keyword highlights
- **Effects**: Pop-in from bottom with slight rotation, 2-3px black stroke
- **Timing**: Single word displayed at a time, replaced as spoken
- **Emojis**: Strategic placement for emphasis

This style is reproducible in Python by combining WhisperX timestamps with PIL rendering:

```python
from PIL import Image, ImageDraw, ImageFont

def render_hormozi_word(word, frame_progress, size=(1080, 1920)):
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("Montserrat-Black.ttf", 96)
    
    # Pop animation with overshoot
    if frame_progress < 0.6:
        scale = (frame_progress / 0.6) * 1.15
    else:
        scale = 1.15 - (0.15 * (frame_progress - 0.6) / 0.4)
    
    # Draw with stroke for readability
    text = word.upper()
    draw.text((size[0]//2, size[1]//2), text, font=font,
              fill=(255, 255, 255), anchor="mm",
              stroke_width=4, stroke_fill=(0, 0, 0))
    return img
```

## Educational content requires distinct visual hierarchy

For language-learning content with mixed languages, implement **visual differentiation** through color coding: primary language in white (#F2F2F2), target/foreign words in accent color (yellow, light blue). Language detection can use character n-gram models or simple dictionary lookup for known language pairs.

**Dual subtitle layout** for translations:
```
[Target language - 46px, bottom center]
[Translation - 32-38px (70-80% size), directly above]
```

Both languages must have **identical timing**—use the earlier start and later end time when merging. Maintain 10-20px vertical gap between lines.

**Safe area positioning** varies by platform: TikTok requires keeping text in the **middle 70%** to avoid UI element overlap (like/comment buttons on right edge), while YouTube allows 90% usage. Always test on actual devices, as phones aren't 16:9.

## Complete implementation pipeline

The optimal Python stack for production TikTok-style captions:

1. **Transcription**: WhisperX for word timestamps (or stable-ts for simpler setup)
2. **Animation logic**: Custom easing functions (ease-out-back for pop effects)
3. **Text rendering**: PIL/Pillow with Montserrat Bold, 2-4px black stroke
4. **Compositing**: FFmpeg overlay filter for final video
5. **Alternative**: pycaps for all-in-one with CSS styling

```python
# Complete pipeline example
import whisperx
from PIL import Image, ImageDraw, ImageFont
import subprocess
import os

def generate_caption_video(input_video, output_video):
    # 1. Get word timestamps
    model = whisperx.load_model("large-v2", "cuda")
    audio = whisperx.load_audio(input_video)
    result = model.transcribe(audio)
    model_a, meta = whisperx.load_align_model("en", "cuda")
    aligned = whisperx.align(result["segments"], model_a, meta, audio, "cuda")
    
    # 2. Render text frames with pop animation
    os.makedirs("frames", exist_ok=True)
    fps, frame_num = 30, 0
    
    for seg in aligned["segments"]:
        for word in seg["words"]:
            start_frame = int(word["start"] * fps)
            end_frame = int(word["end"] * fps)
            anim_frames = 6  # 200ms pop at 30fps
            
            for f in range(start_frame, end_frame):
                progress = min((f - start_frame) / anim_frames, 1.0)
                img = render_word_frame(word["word"], progress)
                img.save(f"frames/{frame_num:06d}.png")
                frame_num += 1
    
    # 3. Composite with FFmpeg
    subprocess.run([
        'ffmpeg', '-i', input_video,
        '-framerate', '30', '-i', 'frames/%06d.png',
        '-filter_complex', '[0][1]overlay=shortest=1',
        '-c:v', 'libx264', '-crf', '18', output_video
    ])
```

## Conclusion

The gap between amateur and professional animated captions comes down to **three technical details**: sub-50ms word timing (use WhisperX), spring-physics easing (implement ease-out-back with 10-20% overshoot), and efficient rendering (PIL frames + FFmpeg, or pycaps). Commercial tools like CapCut aren't doing anything magical—they've simply optimized these same fundamentals. The "Hormozi style" that dominates viral content follows a reproducible formula: Montserrat Black, ALL CAPS, single-word display, aggressive pop animations, and strategic color highlighting. For Python developers, pycaps now offers the fastest path to production-quality results, while the PIL + FFmpeg + WhisperX combination provides maximum control for custom implementations.
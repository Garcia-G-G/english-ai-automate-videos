# FIX: Educational Videos Not Generating (Critical Bug)

## Prompt for Claude Code

```
CRITICAL BUG: Educational videos are not being generated. The dashboard shows "completed" status but no .mp4 file is created. The root cause is that ElevenLabs TTS generates audio but does NOT produce word-level timestamps. The educational video renderer requires word timestamps for its karaoke-style word-by-word animation, so when words=[] and segments=[], the renderer returns None and no video file is created.

AFFECTED: Only educational videos. Quiz, true_false, fill_blank, and pronunciation all work fine.

ROOT CAUSE ANALYSIS:
1. In src/tts_elevenlabs.py, line 1281: For educational/pronunciation types, the code does a single TTS call and hardcodes `'words': [], 'segments': []`
2. In src/video/__init__.py, lines 121-134: For educational type, if words is empty AND segments is empty, the function returns None (no video created)
3. In src/admin.py, lines 318-319: The pipeline checks video_result.returncode but the video module's __main__ doesn't set a proper exit code when generate_video returns None

THREE FIXES NEEDED:

FIX 1 — Generate word timestamps from ElevenLabs (PRIMARY FIX)
File: src/tts_elevenlabs.py

The ElevenLabs SDK v2.35+ supports the `with_timestamps` parameter in `text_to_speech.convert_with_timestamps()` method which returns character-level or word-level alignment data along with the audio.

However, if `convert_with_timestamps` is not available in this SDK version, implement a FALLBACK approach: estimate word timestamps from the audio duration and the script text.

In the CLI section (around line 1270-1291), for educational and pronunciation types:

Option A (preferred): Use ElevenLabs `convert_with_timestamps` API if available:
```python
try:
    response = client.text_to_speech.convert_with_timestamps(
        voice_id=voice_id,
        text=text,
        model_id=MODEL_ID,
        voice_settings=VoiceSettings(...),
        output_format="mp3_44100_128",
    )
    # Extract audio and alignment
    audio_bytes = b''.join(response.audio_base64)  # or however the response provides audio
    alignment = response.alignment  # word-level timestamps
    words = parse_alignment_to_words(alignment, text)
except Exception:
    # Fall through to Option B
```

Option B (reliable fallback): Estimate word timestamps from duration and text. Add this function:

```python
def estimate_word_timestamps(text: str, duration: float, english_phrases: list = None) -> list:
    """
    Estimate word-level timestamps by distributing words evenly across duration.

    This is a fallback when the TTS API doesn't provide alignment data.
    Words are distributed proportionally by character length.
    """
    import re
    # Split text into words, preserving punctuation
    raw_words = text.split()
    if not raw_words:
        return []

    # Build english set for is_english detection
    english_set = set()
    if english_phrases:
        for phrase in english_phrases:
            for w in phrase.lower().split():
                english_set.add(w.strip("'\".,!?¿¡"))

    # Calculate proportional timing based on character count
    # Longer words take more time to speak
    char_counts = [len(w) + 1 for w in raw_words]  # +1 for space
    total_chars = sum(char_counts)

    # Leave small buffer at start and end
    buffer = 0.1
    usable_duration = duration - 2 * buffer

    words = []
    current_time = buffer

    for i, raw_word in enumerate(raw_words):
        word_duration = (char_counts[i] / total_chars) * usable_duration
        word_clean = re.sub(r'[^\w\s]', '', raw_word).lower()

        words.append({
            'word': raw_word,
            'start': round(current_time, 3),
            'end': round(current_time + word_duration, 3),
            'is_english': word_clean in english_set,
        })
        current_time += word_duration

    return words
```

Then in the CLI section (line ~1270-1291), replace:
```python
result = {'duration': duration, 'words': [], 'segments': []}
```
with:
```python
english_phrases = script_data.get('english_phrases', [])
estimated_words = estimate_word_timestamps(text, duration, english_phrases)

# Create segments from sentences (split on periods)
import re as _re
sentences = [s.strip() for s in _re.split(r'[.!?]+', text) if s.strip()]
segments = []
if estimated_words:
    words_per_sentence = max(1, len(estimated_words) // max(1, len(sentences)))
    for i, sentence in enumerate(sentences):
        start_idx = i * words_per_sentence
        end_idx = min((i + 1) * words_per_sentence, len(estimated_words))
        if start_idx < len(estimated_words):
            segments.append({
                'start': estimated_words[start_idx]['start'],
                'end': estimated_words[min(end_idx, len(estimated_words)) - 1]['end'],
                'text': sentence,
            })

result = {
    'duration': duration,
    'words': estimated_words,
    'segments': segments,
}
```

FIX 2 — Better error handling in video __main__
File: src/video/__init__.py

At the end of generate_video(), after the renderer returns, add validation:
```python
# After line 283: return output_path
# Add at the very end of generate_video, before the final return:
if output_path and os.path.exists(output_path):
    file_size = os.path.getsize(output_path)
    if file_size < 1000:
        logger.error(f"Generated video is suspiciously small ({file_size} bytes)")
        return None
    logger.info(f"Video created: {output_path} ({file_size:,} bytes)")
    return output_path
else:
    logger.error(f"Video file was not created: {output_path}")
    return None
```

Also in the main() function, add proper exit code when generate_video returns None:
After the call to generate_video() in main(), add:
```python
result = generate_video(...)
if result is None:
    print("Error: Video generation failed - no output produced", file=sys.stderr)
    sys.exit(1)
```

FIX 3 — Pipeline validation in admin.py
File: src/admin.py

After the video subprocess completes (around line 318-319), add explicit file existence check:
```python
if video_result.returncode != 0:
    raise Exception(f"Video generation failed: {video_result.stderr[-500:]}")

# ADD THIS: Verify the video file was actually created
if not video_path.exists():
    stderr_tail = video_result.stderr[-500:] if video_result.stderr else "no stderr"
    stdout_tail = video_result.stdout[-500:] if video_result.stdout else "no stdout"
    raise Exception(
        f"Video render completed but file not found: {video_path}\n"
        f"stdout: {stdout_tail}\n"
        f"stderr: {stderr_tail}"
    )

video_size = video_path.stat().st_size
if video_size < 1000:
    raise Exception(f"Video file too small ({video_size} bytes), likely corrupted: {video_path}")
```

PRIORITY: Fix 1 is the most important — it makes educational videos work. Fix 2 and 3 prevent false "completed" status.

IMPORTANT:
- Do NOT change any quiz, true_false, fill_blank, or pronunciation logic — those work correctly
- The estimate_word_timestamps function should be added near the top of tts_elevenlabs.py with the other helper functions
- Test by generating an educational video from the dashboard after applying the fix
- The word timestamp estimation doesn't need to be perfect — the SubtitleProcessor in the video renderer will clean up grouping and timing
```

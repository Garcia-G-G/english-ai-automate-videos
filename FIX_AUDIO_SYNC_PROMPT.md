# FIX: Educational Video Text-Audio Sync (Text Goes Faster Than Voice)

## Prompt for Claude Code

```
CRITICAL BUG: In educational videos, the text appears FASTER than the voice speaks. Words on screen advance ahead of the audio because timestamps are estimated by character count instead of actual speech timing.

THE SOLUTION ALREADY EXISTS IN THE PROJECT:
The file src/tts_openai.py has a function extract_timestamps_whisper() that uses OpenAI's Whisper API to extract REAL word-level timestamps from any audio file. We need to call this function AFTER generating audio with ElevenLabs to get accurate timestamps.

The OPENAI_API_KEY is already set in .env and Whisper API is already a dependency in requirements.txt.

FILE TO MODIFY: src/tts_elevenlabs.py

CHANGE: In the CLI section (around line 1367-1391), after generating audio with ElevenLabs, use Whisper to extract real word timestamps instead of estimating them.

Replace the current code block (lines ~1367-1391):

```python
        else:
            # educational, pronunciation — single TTS call
            text = script_data.get('full_script', '')
            if not text:
                print(f"Script missing 'full_script' for type '{video_type}'")
                import sys; sys.exit(1)
            tts_text = clean_for_tts(text)  # cleaned for TTS only
            english_words = extract_english_words_from_script(script_data)
            duration = generate_segment_audio(
                tts_text, args.output, voice_id=args.voice,
                segment_type='explanation', english_words=english_words,
            )
            english_phrases = script_data.get('english_phrases', [])
            # Use ORIGINAL text for word estimation (not tts_text)
            est_words, est_segments = estimate_word_timestamps(text, duration, english_phrases)
            result = {'duration': duration, 'words': est_words, 'segments': est_segments}
            for key in ('type', 'question', 'options', 'correct', 'explanation',
                        'full_script', 'translations', 'hashtags', 'word', 'phonetic',
                        'english_phrases', 'tip', 'sentence'):
                if key in script_data:
                    result[key] = script_data[key]
            # Save companion JSON
            json_out = args.output.replace('.mp3', '.json')
            with open(json_out, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
```

WITH THIS NEW VERSION:

```python
        else:
            # educational, pronunciation — single TTS call
            text = script_data.get('full_script', '')
            if not text:
                print(f"Script missing 'full_script' for type '{video_type}'")
                import sys; sys.exit(1)
            tts_text = clean_for_tts(text)
            english_words_set = extract_english_words_from_script(script_data)
            duration = generate_segment_audio(
                tts_text, args.output, voice_id=args.voice,
                segment_type='explanation', english_words=english_words_set,
            )
            english_phrases = script_data.get('english_phrases', [])

            # --- Get REAL word timestamps from Whisper ---
            whisper_words = []
            try:
                from tts_openai import extract_timestamps_whisper
                logger.info("Extracting real word timestamps with Whisper...")
                whisper_result = extract_timestamps_whisper(
                    args.output,
                    original_text=text,
                    explicit_english=english_phrases,
                )
                whisper_words = whisper_result.get('words', [])
                whisper_duration = whisper_result.get('duration', duration)
                if whisper_words:
                    duration = whisper_duration
                    logger.info("Whisper: got %d real word timestamps", len(whisper_words))
                else:
                    logger.warning("Whisper returned no words, falling back to estimation")
            except Exception as e:
                logger.warning("Whisper failed (%s), falling back to character estimation", e)

            if whisper_words:
                # Use real Whisper timestamps — but they lack segment_id
                # Add segment boundaries using the original script
                from video.educational import add_sentence_boundaries
                words_with_segments = add_sentence_boundaries(whisper_words, text)

                # Build segments from sentence boundaries
                segments = []
                current_seg_id = None
                seg_words = []
                for w in words_with_segments:
                    sid = w.get('segment_id', 0)
                    if sid != current_seg_id:
                        if seg_words:
                            segments.append({
                                'start': seg_words[0]['start'],
                                'end': seg_words[-1]['end'],
                                'text': ' '.join(sw['word'] for sw in seg_words),
                            })
                        seg_words = [w]
                        current_seg_id = sid
                    else:
                        seg_words.append(w)
                if seg_words:
                    segments.append({
                        'start': seg_words[0]['start'],
                        'end': seg_words[-1]['end'],
                        'text': ' '.join(sw['word'] for sw in seg_words),
                    })

                result = {
                    'duration': duration,
                    'words': words_with_segments,
                    'segments': segments,
                }
            else:
                # Fallback: estimate timestamps from character count
                est_words, est_segments = estimate_word_timestamps(text, duration, english_phrases)
                result = {'duration': duration, 'words': est_words, 'segments': est_segments}

            for key in ('type', 'question', 'options', 'correct', 'explanation',
                        'full_script', 'translations', 'hashtags', 'word', 'phonetic',
                        'english_phrases', 'tip', 'sentence'):
                if key in script_data:
                    result[key] = script_data[key]

            # Save companion JSON
            json_out = args.output.replace('.mp3', '.json')
            with open(json_out, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
```

KEY POINTS:
1. After ElevenLabs generates the audio, we call extract_timestamps_whisper() from tts_openai.py
2. This sends the audio to OpenAI's Whisper API which returns REAL word-level timestamps
3. We then run add_sentence_boundaries() to tag sentence breaks (segment_id, segment_end)
4. If Whisper fails (network error, API issue), we gracefully fall back to the character estimation
5. The import of extract_timestamps_whisper is inside the try block so it won't crash if openai isn't installed

ALSO: Make sure to add this import at the top of tts_elevenlabs.py (around line 30, with the other imports):
```python
# Note: tts_openai is imported dynamically inside the try block to avoid
# hard dependency — fallback to estimation if unavailable
```

No new import is needed at the top level since we import dynamically inside the try block.

IMPORTANT:
- Do NOT modify extract_timestamps_whisper() in tts_openai.py — it works correctly
- Do NOT modify add_sentence_boundaries() in educational.py — it works correctly
- Do NOT change quiz, true_false, fill_blank, pronunciation — they use segment_times not word timestamps
- The Whisper API call adds ~2-5 seconds to generation time but gives perfect sync
- Keep estimate_word_timestamps() as the fallback — don't remove it
- The OPENAI_API_KEY is already in .env and loaded by tts_openai.py
```

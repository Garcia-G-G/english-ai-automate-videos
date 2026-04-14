# ElevenLabs TTS Optimization — Analysis & Claude Code Prompts

## Current State Analysis

### What's Already Implemented
The project already has the ElevenLabs integration modified with these changes:

1. **Voice Settings (HUMANIZED)** in `src/tts_elevenlabs.py`:
   - Stability: 0.40 (was 0.50) — more expressive
   - Similarity: 0.80 (was 0.75) — more faithful to voice
   - Style: 0.15 (was 0.0) — subtle warmth
   - Speaker Boost: True (unchanged)

2. **Speed Control** — per-segment speeds via REST API (SDK v2.35 doesn't expose `speed`):
   - question: 0.90, options: 0.85, english_word: 0.80, answer: 0.88, explanation: 0.87, global: 0.88

3. **SSML Break Tags** — `add_natural_pauses()` function inserts `<break time="X.Xs" />` tags:
   - After "Correcto" (0.5s), before "La respuesta es" (0.4s)
   - Between sentences in explanations (0.3s)
   - Between options A/B/C/D (0.4s)
   - Around quoted English words (0.2s)
   - After commas (0.15s)

4. **Bilingual Enhancement** — `enhance_bilingual_text()` adds micro-pauses around English words

5. **Provider activated** — `.env` set to `TTS_PROVIDER=elevenlabs`

### Known Issues / Risks
- The `speed` parameter uses direct REST API instead of SDK (works, but bypasses SDK error handling)
- Comma micro-pauses (0.15s) on EVERY comma might over-fragment short segments
- Too many `<break>` tags in one call can cause ElevenLabs instability (per their docs)
- No pronunciation dictionary support yet (for tricky words)
- `output_format` is `mp3_44100_128` — could use `mp3_44100_192` for higher quality
- The `requests` library is imported inside the retry function — potential proxy issues on some systems


---

## PROMPT 1 — First Test & Baseline

```
Generate a test quiz video to establish a baseline with the current ElevenLabs configuration. Run:

python main.py --random --type quiz

Listen to the output audio carefully and note:
1. Does the speed feel right? (currently set to 0.88 global)
2. Are English words pronounced correctly in English context?
3. Are Spanish words pronounced correctly?
4. Do the SSML break pauses sound natural or choppy?
5. Is there any audio instability (artifacts, speed changes, weird noises)?

After generating, show me the segment timestamps from the JSON output and the total duration. Also show me the exact text that was sent to the API for each segment (with SSML tags visible) so I can evaluate the pauses.
```

---

## PROMPT 2 — Fix Speed via SDK Upgrade

```
The current implementation uses direct REST API calls (requests library) to send the `speed` parameter because the elevenlabs Python SDK v2.35 doesn't expose it. This is fragile.

Check if there's a newer version of the elevenlabs SDK that supports the speed parameter:

pip install --upgrade elevenlabs

Then inspect the convert method signature:
python3 -c "import inspect; from elevenlabs.text_to_speech.client import TextToSpeechClient; print(inspect.signature(TextToSpeechClient.convert))"

If the new SDK supports `speed`, refactor `_elevenlabs_with_retry()` in `src/tts_elevenlabs.py` to use the SDK directly instead of the REST API fallback. Remove the `requests` import and the direct API code path. The function should only use `client.text_to_speech.convert()` with the speed parameter.

If the SDK still doesn't support speed, keep the current approach but add proper error handling: if the REST call fails with a 422 (invalid parameter), fall back to SDK without speed.
```

---

## PROMPT 3 — Reduce SSML Over-Engineering

```
The `add_natural_pauses()` function in `src/tts_elevenlabs.py` currently adds break tags on EVERY comma (step 7, line 165-170). This is too aggressive — ElevenLabs docs warn that too many break tags cause instability (speed changes, artifacts, weird noises).

Make these changes to `add_natural_pauses()`:

1. REMOVE step 7 entirely (comma-based micro-pauses). ElevenLabs already handles commas naturally — adding explicit breaks on every comma over-fragments the speech.

2. REDUCE step 6 (quoted English word pauses) from 0.2s to 0.1s — the bilingual model already handles code-switching, we just need a hint.

3. In step 3 (explanation sentence pauses), only add breaks if the explanation has 3+ sentences. For 1-2 sentences, the natural flow is fine.

4. Add a safety check: count total breaks in final text. If more than 6 breaks in a single API call, remove the smallest ones (0.1s, 0.15s) until we're at 6 or fewer. This prevents ElevenLabs instability.

5. Keep steps 1, 2, 4, 5 unchanged — those are the important structural pauses.

Test with: python src/tts_elevenlabs.py --test --text "¿Qué significa 'embarrassed' en español? Muchos lo confunden con embarazada, pero en realidad significa avergonzado. Es un falso amigo muy común entre estudiantes de inglés."
```

---

## PROMPT 4 — Improve Bilingual Pronunciation

```
The `enhance_bilingual_text()` function in `src/tts_elevenlabs.py` only adds micro-pauses around English words. But ElevenLabs eleven_multilingual_v2 supports a better approach: pronunciation dictionaries.

Do these improvements:

1. In `enhance_bilingual_text()`, for common English words that the Spanish model mispronounces, add phonetic spelling hints. Create a dictionary in the function:

PRONUNCIATION_HINTS = {
    'comfortable': 'cómfortable',     # Spanish speakers stress wrong syllable
    'vegetable': 'végetable',
    'wednesday': 'wénzday',
    'february': 'fébruary',
    'library': 'láibrary',            # Not "librería"
    'recipe': 'résipee',
    'schedule': 'skéjool',
    'breakfast': 'brékfast',
    'through': 'thruu',
    'tough': 'tuff',
    'enough': 'enúff',
    'thought': 'thot',
    'although': 'olthóu',
}

Only apply these hints if the word is detected as an English teaching word. Don't change words that are part of Spanish sentences.

2. For the `language_code` parameter: ElevenLabs API supports a `language_code` parameter. Since our content is primarily Spanish with English words embedded, pass `language_code="es"` in the API call. This tells the model the base language is Spanish, which improves how it handles the Spanish portions. Add this to both the SDK call and the REST API call in `_elevenlabs_with_retry()`.

3. Test with a word that's commonly mispronounced:
python src/tts_elevenlabs.py --test --text "¿Sabes cómo se pronuncia 'comfortable' en inglés? No es como suena, se dice 'cómftable', casi sin la segunda O."
```

---

## PROMPT 5 — Fine-Tune Voice Settings Based on Feedback

```
I need you to create a voice settings test script that generates the SAME text with different voice configurations so I can A/B compare them. Create a new file `src/test_voice_settings.py` that:

1. Uses this test text (covers all segment types):
   - Question: "¿Qué significa 'awkward' en español?"
   - Answer: "Correcto. La respuesta es A, incómodo."
   - Explanation: "Awkward significa incómodo o torpe. No confundas con 'weird' que significa raro. Son palabras diferentes con significados distintos."

2. Generates 4 variations with different settings, saving each as a separate file:

   a) `test_current.mp3` — Current settings (stability=0.40, similarity=0.80, style=0.15, speed=0.88)
   b) `test_warmer.mp3` — Warmer/more human (stability=0.35, similarity=0.85, style=0.20, speed=0.85)
   c) `test_teacher.mp3` — Teacher mode (stability=0.45, similarity=0.80, style=0.10, speed=0.83)
   d) `test_natural.mp3` — Most natural (stability=0.30, similarity=0.75, style=0.25, speed=0.87)

3. For each variation, generate all 3 segments (question, answer, explanation) and concatenate them with proper pauses.

4. Print a summary table showing: variant name, total duration, settings used.

5. Save all files to `output/voice_tests/` directory.

This lets me listen to each variant and tell you which one sounds best so we can update the defaults.
```

---

## PROMPT 6 — Upgrade Output Quality

```
Make these quality improvements to the ElevenLabs TTS pipeline in `src/tts_elevenlabs.py`:

1. Change `output_format` from `"mp3_44100_128"` to `"mp3_44100_192"` everywhere — higher bitrate = better audio quality, especially for the subtle SSML pauses and bilingual transitions. Update both in `generate_segment_audio()` and in `_elevenlabs_with_retry()`.

2. In `_elevenlabs_with_retry()`, the REST API path should also pass `"previous_text"` and `"next_text"` context when available. This helps ElevenLabs generate more natural transitions. Modify `generate_segment_audio()` to accept optional `previous_text` and `next_text` parameters, and pass them through. Then in `generate_quiz_audio_segmented()`, when generating the answer segment, pass the question as `previous_text`; when generating the explanation, pass the answer as `previous_text`.

3. Add a `seed` parameter to `generate_segment_audio()` with default `None`. When not None, pass it to the API for reproducible output (useful for regenerating specific segments without changing the voice). Document that this is optional.
```

---

## PROMPT 7 — Iterate Based on Audio Feedback

```
[USE THIS AFTER LISTENING TO TEST AUDIO]

I listened to the generated audio and here is my feedback:
[PASTE YOUR FEEDBACK HERE — e.g. "the speed is good but the pauses after Correcto are too long", "the English word embarrassed is being pronounced with Spanish accent", "the explanation sounds choppy", etc.]

Based on this feedback, make the necessary adjustments to `src/tts_elevenlabs.py`. Specifically update:
- Voice settings constants (DEFAULT_STABILITY, DEFAULT_SIMILARITY, DEFAULT_STYLE) if tone needs changing
- SEGMENT_SPEEDS dictionary if any segment is too fast or slow
- Break tag durations in `add_natural_pauses()` if pauses need adjustment
- Any pronunciation hints in `enhance_bilingual_text()` if words are mispronounced

After making changes, generate a new test audio:
python src/tts_elevenlabs.py --test --text "[SAME TEXT YOU TESTED WITH]"

Show me the before/after durations and the exact SSML-enhanced text being sent to the API.
```

---

## Quick Reference: ElevenLabs Settings Cheat Sheet

| Setting | Range | Lower = | Higher = | Current |
|---------|-------|---------|----------|---------|
| stability | 0.0-1.0 | More emotional/variable | More monotone/consistent | 0.40 |
| similarity_boost | 0.0-1.0 | Less like original voice | More like original voice | 0.80 |
| style | 0.0-1.0 | Neutral delivery | Exaggerated style | 0.15 |
| speed | 0.7-1.2 | Slower speech | Faster speech | 0.88 |
| speaker_boost | bool | Less clear | Enhanced clarity | true |

### SSML Break Tags (eleven_multilingual_v2)
- Supported: `<break time="1.5s" />` (self-closing ONLY, up to 3s)
- NOT supported: `<phoneme>` tags (use pronunciation dictionaries instead)
- WARNING: >6 break tags per call can cause instability

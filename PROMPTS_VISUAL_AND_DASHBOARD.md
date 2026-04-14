# Prompts for Claude Code — Visual Bugs + Dashboard TTS Fix

---

## PROMPT 1 — Fix Pronunciation Video Text Overlap (CRITICAL)

```
There's a critical text overlap bug in the pronunciation video type. Look at the current code in `src/video/pronunciation.py` and the layout constants in `src/config/layout.py`.

THE PROBLEM:
The pronunciation video has multiple text elements stacking on top of each other, creating an unreadable mess. Here's what's happening:

1. The big word title (e.g., "Disagreement") at PRON_TITLE_Y=300 with font size FONT_SIZE_BIG_WORD is too large — when the word is long (like "Disagreement"), it's so big it bleeds into the translation area below it.

2. The translation at PRON_TRANSLATION_Y=470 overlaps with the question "Como se pronuncia?" at PRON_QUESTION_Y=570 — only 100px gap which is not enough for large text.

3. The "Incorrecto:" label at PRON_INCORRECT_LABEL_Y=670 and text at PRON_INCORRECT_TEXT_Y=740 overlap because the incorrect text (e.g., "Pronunciar 'disagreement' como 'disagree-ment'") wraps to multiple lines and extends down into the correct section area.

4. WORST: During the phase where BOTH incorrect and correct are visible (between word_phase and phonetic_phase), the incorrect section (670-740+) overlaps with the correct section (1050-1130) — actually these don't overlap numerically, BUT the real problem is that the incorrect text has NO max_width constraint on line 61, so long common_mistake text renders as one wide line that goes off-screen.

5. The "Correcto:" section transitions from PRON_CORRECT_LABEL_Y=1050 to PRON_CORRECT_FINAL_LABEL_Y=670 when t > phonetic_phase — this puts it EXACTLY where "Incorrecto:" was, but "Incorrecto:" doesn't fade out until phonetic_phase, causing overlap during the transition.

THE FIXES NEEDED:

1. **Dynamic font size for the big word:** In pronunciation.py line 42-44, the word uses FONT_SIZE_BIG_WORD which is likely too large for long words. Add dynamic font sizing:
   - If the word has <= 8 characters: use FONT_SIZE_BIG_WORD (current)
   - If 9-12 characters: use FONT_SIZE_BIG_WORD * 0.75
   - If 13+ characters: use FONT_SIZE_BIG_WORD * 0.55
   - Always use `max_width=TEXT_AREA_WIDTH - 40` to prevent horizontal overflow

2. **Add max_width to ALL draw_text_centered calls:** Lines 44, 49, 54, 60, 61, 75, 76 — every single text draw call should include `max_width=TEXT_AREA_WIDTH - 80` to prevent text going off-screen. Currently only the tip (line 82) has max_width.

3. **Spread out Y positions to prevent overlap:** Update `src/config/layout.py` pronunciation section:
   ```
   PRON_TITLE_Y = 250          # was 300 — move up to give more room
   PRON_TRANSLATION_Y = 430    # was 470 — slightly higher
   PRON_QUESTION_Y = 530       # was 570 — gap between elements
   PRON_INCORRECT_LABEL_Y = 650  # was 670
   PRON_INCORRECT_TEXT_Y = 720   # was 740
   PRON_CORRECT_LABEL_Y = 1000  # was 1050 — move up
   PRON_CORRECT_TEXT_Y = 1080   # was 1130
   PRON_CORRECT_FINAL_LABEL_Y = 650  # was 670
   PRON_CORRECT_FINAL_TEXT_Y = 750   # was 770
   PRON_TIP_Y = 900            # was 950 — move up
   ```

4. **Fix the phase transition:** In pronunciation.py, the incorrect section should FULLY fade out before the correct section transitions to its final position. Change line 57 from:
   ```python
   if word_phase < t < phonetic_phase:
   ```
   to calculate a fade-out alpha that reaches 0 before phonetic_phase:
   ```python
   if word_phase < t < phonetic_phase:
       m_alpha = get_alpha(t, word_phase, 0.3)
       # Fade out as we approach phonetic_phase
       fade_out = max(0, 1.0 - ((t - mistake_phase) / (phonetic_phase - mistake_phase)))
       m_alpha = int(m_alpha * fade_out)
   ```

5. **Reduce font sizes for secondary text:** The incorrect and correct phonetic text use font(64) and font(72) which is too large for long pronunciation strings. Reduce:
   - Incorrect text: font(64) → font(52)
   - Correct phonetic: font(72) → font(60)
   - These still look big and readable on a phone screen but won't overflow

After making changes, generate a test pronunciation video with a long word like "disagreement" or "uncomfortable" to verify no overlap:
```bash
python main.py --type pronunciation --topic "disagreement"
```
```

---

## PROMPT 2 — Fix Admin Dashboard to Use ElevenLabs TTS

```
CRITICAL BUG: The admin dashboard (`src/admin.py`) is hardcoded to use OpenAI TTS and completely ignores the TTS_PROVIDER setting in .env.

THE PROBLEM:
In admin.py around line 227-231, the TTS command is hardcoded:
```python
tts_cmd = [
    "python3", str(ROOT / "src" / "tts_openai.py"),  # HARDCODED to OpenAI!
    "--script", str(tts_script_path.resolve()),
    "-o", str(audio_path.resolve())
]
```

This means every video generated through the Streamlit dashboard uses OpenAI TTS regardless of what's set in .env (which is TTS_PROVIDER=elevenlabs). All the ElevenLabs improvements we made (voice settings, natural pauses, bilingual pronunciation) are being bypassed.

THE FIX:
Replace the hardcoded OpenAI TTS command with logic that reads TTS_PROVIDER from .env and uses the correct module. Change lines 227-231 to:

```python
# Read TTS provider from environment
from dotenv import load_dotenv
load_dotenv()
tts_provider = os.getenv("TTS_PROVIDER", "elevenlabs").lower()

# Map provider to module
tts_modules = {
    "elevenlabs": "tts_elevenlabs",
    "openai": "tts_openai",
    "google": "tts_google",
    "edge": "tts",
}
tts_module = tts_modules.get(tts_provider, "tts_elevenlabs")

tts_cmd = [
    "python3", str(ROOT / "src" / f"{tts_module}.py"),
    "--script", str(tts_script_path.resolve()),
    "-o", str(audio_path.resolve())
]
```

Also update the progress message on line 208 from:
```python
current_step="Step 3/4: Generating audio with OpenAI TTS...",
```
to:
```python
current_step=f"Step 3/4: Generating audio with {tts_provider.upper()} TTS...",
```

Make sure the dotenv import is at the top of admin.py (it might already be imported). Verify that `tts_elevenlabs.py` supports the same --script and -o CLI arguments that tts_openai.py uses — check the `if __name__ == "__main__"` block at the bottom of both files to confirm they accept the same interface.

After making this change, every video generated from the dashboard will use ElevenLabs with all our voice improvements.
```

---

## PROMPT 3 — Fix Mini-Words / Audio Artifacts from ElevenLabs

```
The ElevenLabs eleven_v3 model sometimes adds random meaningless mini-words or sounds that weren't in the original text. Read `src/tts_elevenlabs.py` and fix these issues:

1. STABILITY TOO LOW: Current DEFAULT_STABILITY = 0.50. For eleven_v3, raise it to 0.55. The v3 model is already more expressive than v2 by default, so it needs slightly more stability to avoid hallucinated words. The sweet spot for v3 educational content is 0.55-0.60.

2. EXCESSIVE ELLIPSIS PAUSES: The `add_natural_pauses()` function adds "..." markers which v3 interprets as hesitation — but too many of them cause the model to generate filler sounds (ums, ahs, random syllables). Make these changes:
   - Reduce MAX_PAUSE_MARKERS from 5 to 3
   - In the 'explanation' segment type (step 2), ONLY add "..." between sentences if there are 3 or more sentences. For 1-2 sentences, the natural flow is better.
   - In the 'options' segment type (step 4), don't add "..." between options — v3 already pauses naturally between "Opción A... Opción B". Remove step 4 entirely.

3. PRONUNCIATION HINTS CAUSING ARTIFACTS: The `enhance_bilingual_text()` function replaces English words with phonetic hints like 'comfortable' → 'cómfortable'. This can confuse eleven_v3 because v3 handles English pronunciation much better than v2. For v3, DISABLE the pronunciation hints — remove or comment out the PRONUNCIATION_HINTS replacement logic. Only keep the function structure so it can be re-enabled later if needed. v3's multilingual model already knows how to pronounce these words correctly.

4. ADD apply_text_normalization PARAMETER: In `_elevenlabs_with_retry()`, when calling `client.text_to_speech.convert()`, add the parameter `apply_text_normalization="on"`. This tells ElevenLabs to normalize the text before synthesis, which reduces artifacts from unusual characters, quotes, or formatting.

After changes, test with:
```bash
python src/tts_elevenlabs.py --test --text "¿Qué significa 'comfortable' en español? Comfortable significa cómodo. No confundas con 'comfortar' que no existe en inglés."
```
```

---

## PROMPT 4 — Improve All Video Type Animations (General Overlap Prevention)

```
Review ALL video type renderers in `src/video/` and add overflow protection to prevent text overlap. Read each file and apply these fixes:

FILES TO CHECK:
- src/video/quiz.py
- src/video/true_false.py
- src/video/fill_blank.py
- src/video/pronunciation.py (should already be fixed from previous prompt)
- src/video/educational.py

FOR EACH FILE, apply these rules:

1. EVERY `draw_text_centered()` call MUST have `max_width=TEXT_AREA_WIDTH - 80` (or similar appropriate value). Search for any calls missing this parameter and add it.

2. DYNAMIC FONT SIZING: For any text that could be long (questions, explanations, sentences), implement adaptive font sizing. The pattern should be:
   ```python
   def fit_text_font(text, max_font, min_font, max_width, max_height=None):
       """Find the largest font size that fits the text within bounds."""
       for size in range(max_font, min_font - 1, -2):
           f = font(size)
           lines = line_break(text, f, max_width)
           line_h = int(size * 1.35)
           total_h = len(lines) * line_h
           if max_height is None or total_h <= max_height:
               return f, size
       return font(min_font), min_font
   ```
   Add this utility function to `src/video/utils.py` and use it wherever text length is variable.

3. ZONE BOUNDARY ENFORCEMENT: Text should NEVER render below its designated zone. For quiz.py, the question text must stay within QUIZ_QUESTION_ZONE_TOP to QUIZ_QUESTION_ZONE_BOTTOM. For true_false.py, statements must stay within TF_QUESTION_ZONE_TOP to TF_QUESTION_ZONE_BOTTOM. Check that each renderer respects its zone boundaries.

4. CLAMP FONT SIZES: No text should ever use a font larger than 80px except for the pronunciation big word title. Cap font sizes:
   - Questions/statements: max 56px, min 36px
   - Options: max 48px, min 32px
   - Explanations: max 44px, min 30px
   - Labels ("Incorrecto:", "Correcto:"): fixed 40px
   - Tip text: max 40px, min 28px

After making changes, generate one video of each type to verify:
```bash
python main.py --type quiz --random
python main.py --type true_false --random
python main.py --type fill_blank --random
python main.py --type pronunciation --random
```
```

---

## Summary — Execution Order

1. **PROMPT 2 first** — Fix dashboard to use ElevenLabs (fastest, biggest impact)
2. **PROMPT 3 second** — Fix mini-word artifacts (improves audio quality)
3. **PROMPT 1 third** — Fix pronunciation video overlap (visual fix)
4. **PROMPT 4 last** — General overflow prevention for all video types (polish)

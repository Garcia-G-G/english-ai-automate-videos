# AUDIT — english-ai-videos

**Date:** 2026-07-28
**Scope:** read-only audit of `~/Downloads/english-ai-videos/`, 62 Python files, 27,104 lines.
**Method:** full read of the source (not grep-sampling), plus 11 real script JSONs from `output/scripts/` and the 37 job records in `output/generation_jobs.json`. Every claim carries a `file:line`. Claims I could not verify are marked explicitly.
**No file inside the project was modified.**

---

## 0. Executive summary

The project is not 60% done — it is four separate projects stacked on top of each other, none of which was ever decommissioned, and the one you drive every day (the Streamlit dashboard) runs the second-oldest of the four. `main.py` and `src/admin.py` are two independent pipelines that produce **different audio from identical input**; the dashboard bypasses the provider abstraction, the bilingual accent engine, the profile system and cost tracking entirely, by shelling out to a module `__main__` block. That single fact invalidates most of the debugging you have done, because a fix landed on one path is invisible on the other.

Your hypothesis about the quiz options is wrong, and the truth is worse. The countdown was never "fixed with the segmenter" — it was **deleted**: the countdown is now 7 seconds of `anullsrc` silence with the numbers drawn on screen (`src/tts_elevenlabs.py:618-633`). Quiz options are generated ~40 lines above it, in the same function, as **one TTS call** with the letter and the word welded together by a comma (`src/tts_elevenlabs.py:562`, `combined_text = " ".join(...)` at `:565`). There is no parallel code path and no bypassed segmenter. "afabric" is not a regression — it is the designed behaviour, and no code anywhere in the repo is capable of putting silence between an option letter and its word.

Everything downstream inherits an invented timeline. Option reveal times are computed as `transition_duration = 1.5` (a hardcoded guess for how long "Escucha las opciones." takes) and `per_option = options_duration / 4` (`src/tts_elevenlabs.py:589-591`) — then written into `segment_times` and consumed by the renderer as exact. Separately, the educational path builds word timings from the sum of *pre-concatenation* file durations and never reconciles them against the *post-concatenation* file it actually plays (`src/tts_bilingual.py:281` vs `:306`). That is a monotonic, accumulating error in one direction, and it is the mechanism behind "animations faster than the voice."

The reviewer you built to catch this never had a chance. There are in fact **two** of them — `quality_reviewer.py` (840 lines) and `video_analyzer.py` (1,838 lines) — with zero shared symbols, both **orphaned**: a repo-wide grep finds no caller in `main.py`, `admin.py`, or any script. Even if you ran them, every word-level check reads a `words[]` array that the TTS hardcodes as `[]` for quiz, fill_blank, true_false and vocabulary (9 sites, e.g. `src/tts_elevenlabs.py:722`). The analyzer therefore returns FAIL on 100% of those videos with two content-free reasons, while the reviewer returns a false *positive* — `add_positive("Word language marking looks correct")` — on exactly the language dimension you report as broken (`src/quality_reviewer.py:504-505`).

There is no layout engine and not one bounding-box overlap check in the tree. `fit_text_font`, the auto-shrink helper, **never shrinks** when called without `max_height` — the loop returns on its first iteration (`src/video/utils.py:139-141`), and four of its nine call sites omit that argument. Two call sites then discard the wrapped lines and draw the raw string anyway. That is your overlapping-text bug, and it is deterministic, not intermittent.

Your recent failures are not quality failures at all: the three most recent jobs (2026-04-16, back to back) each burned the full **600-second render timeout** at `src/admin.py:250-251`, with `capture_output=True` discarding the renderer's stderr, then threw away paid audio with no resume path. That is what "failing every job with no useful error" actually is.

The good news is real and worth protecting: `src/video/compositor.py`, `src/video/v2/timing_engine.py` and `src/tts_segmenter.py` are precisely specified, correctly reasoned code with documented failure modes and the only tests in the repo. The newest code is the best code. It is also almost entirely unreachable from the UI you use.

**Last recorded pipeline run: 2026-04-16 — three and a half months ago.** In that window `docs/` grew a v2 clip-library plan and a character release calendar. That is the pattern you asked me to flag.

---

## 1. What you are wrong about

Stated plainly, as requested. Each of these is verified.

| Your description | Reality |
|---|---|
| "`src/video.py` reportedly ~3,300 lines" | **`src/video.py` does not exist.** It is a package: `src/video/` — 15 modules (~5,300 lines) plus a `v2/` subpackage (7 modules, ~1,800 lines). The largest single file is `src/admin.py` at 1,877. |
| "MoviePy was removed for performance" | Still pinned in `requirements.txt:13`, still imported at `src/video/__init__.py:79-80`, and there is a **bare `except Exception` around the entire ffmpeg render that silently falls back to MoviePy** (`src/video/__init__.py:333-336`). Any data bug in any renderer is caught there, mislabelled "FFmpeg renderer failed", and re-run under MoviePy where it fails again. |
| "Segment-based audio generation … is what fixed the countdown" | The countdown was fixed by **removing its audio**. It is `add_silence(1.5)` ×3 plus a hardcoded `add_silence(1.0)` (`src/tts_elevenlabs.py:622-633`). The actual segment-based countdown fix — per-number TTS spliced with silence — exists at `src/tts_openai.py:408-573` (`fix_countdown_timing`, 166 lines) and is **orphaned, zero callers.** |
| "quiz options run through a parallel code path that never got it" | **Refuted.** Same function, ~40 lines above the countdown. `src/tts_elevenlabs.py:554-579`. The design is deliberate and commented as such at `src/tts_openai.py:748-751`: *"TTS is inconsistent with short isolated words. Generating ALL options together in ONE call works reliably."* |
| "ElevenLabs replaced OpenAI TTS" | Added, not replaced. `src/tts_openai.py` (1,668 lines) is live, reachable from both entry points, and load-bearing: `extract_timestamps_whisper` is imported *by* `tts_elevenlabs.py:1428`. Four TTS generations coexist. |
| "Whisper for transcription/alignment" | It is the **paid `whisper-1` API** (`src/tts_openai.py:355-361`), billed at `cost_tracker.py:45`. `import whisper` / `whisperx` appears **nowhere** in the codebase — `openai-whisper>=20231117` in `requirements.txt:10` is a multi-hundred-MB torch install for code that never runs. The bilingual path doesn't use Whisper at all; it gets alignment free from ElevenLabs `convert_with_timestamps`. |
| "A reviewer/analyzer … that never caught a single one" | There are **two**, 2,678 lines combined, with zero shared symbols — two independent implementations of the same idea. Both fully orphaned. See §6. |
| "ffmpeg, Whisper/WhisperX, PIL, Python — everything else runs locally and free" | Whisper is the paid API (above). `requirements.txt` is also **missing the entire default TTS stack**: `elevenlabs`, `google-cloud-texttospeech`, `pydub`, `httpx` are all imported and none is listed. A clean install cannot run the default provider. |
| `.context/*.md` as a record of what happened | Both files describe an architecture that was **reverted**. `2026-01-16_segment_architecture.md` claims `parse_quiz_timestamps()` was deleted — it is at `src/video/quiz.py:65-221` and still reachable. `2026-01-16_dashboard_fixes.md` claims `retry_failed_job()`, `clear_job_history()` and per-item queue error display exist — none is in `admin.py`. Onboarding from these docs actively misleads. |
| `README.md` | Describes a 4-step pipeline where steps 2, 3 and 4 are marked *"(próximo paso)"*. All three exist and total ~15,000 lines. It predates ~90% of the codebase. |

---

## 2. Top 10 problems, ranked

Marked **ROOT CAUSE** (fixing it removes a class of bugs) or **SYMPTOM** (fixing it removes one bug).

---

### #1 — Two production pipelines that produce different audio from identical input · **ROOT CAUSE**

`main.py:119-143` uses the `tts_providers/` factory in-process. `src/admin.py:174-208` ignores it and shells out:

```python
tts_cmd = ["python3", str(ROOT / "src" / f"{tts_module}.py"), "--script", ..., "-o", ...]
```

That lands in `src/tts_elevenlabs.py:1370-1501`, which **re-implements the type dispatch** at `:1392-1410`. For educational/pronunciation, `main.py` routes to `tts_bilingual.generate_bilingual_narration` (per-segment `language_code`, the code that exists specifically to give Spanish a native accent and English terms an anglo accent — `src/tts_providers/elevenlabs_provider.py:52-70`). The dashboard routes to the legacy single-call path with **no `language_code` at all** (`src/tts_elevenlabs.py:1411-1493`).

**This is the most likely direct cause of the persistent "wrong accents" complaint: the fix exists and your primary UI does not use it.** It also costs 2× (§9).

Compounding, all verified:
- `admin.py` never imports `profiles` — the `kids` profile in `config.yaml:104-116` is **completely inert from the dashboard** (and its `voice_id` is the literal string `"KIDS_VOICE_ID_PENDIENTE"`, `config.yaml:106`, which `profiles.py:83-86` would export to the API verbatim).
- `admin.py` never passes `--v2` (verified: grep for `v2` in `admin.py` returns only a sidebar caption and a model dropdown). **v2 never runs in your normal workflow.**
- `admin.py` never imports `cost_tracker`. TTS runs as a subprocess, so its in-process tracker dies unsaved. **Every video generated through the dashboard is invisible to cost accounting.**
- `admin.py:446-499` re-implements `mask_key` / `get_api_status` / `save_env_key` inline, without the format validation and key allowlist in the orphaned `src/config/secrets.py:126-154`.

---

### #2 — Quiz option timestamps are fabricated arithmetic presented as ground truth · **ROOT CAUSE**

`src/tts_elevenlabs.py:588-601` (identical at `tts_openai.py:782-800`, `tts_google.py:294-307`):

```python
transition_duration = 1.5
options_duration = combined_duration - transition_duration
per_option = options_duration / 4
for i, letter in enumerate(['A','B','C','D']):
    opt_start = combined_start + transition_duration + (i * per_option)
```

`1.5` is a guess at how long *"Escucha las opciones."* takes. The four options are assumed equal length. These invented values are written into `segment_times` (`:704-713`) and the renderer treats them as exact — `src/video/quiz.py:519-538` literally logs `"Quiz timestamps: using segment_times (exact)"` and returns immediately; `create_frame_quiz` drives option reveal from them at `:598-601, 653-671`.

`'fábrica'` and `'This shirt is made of cotton fabric'` do not take the same time to say. The reveal cannot match the audio, and the error compounds A→D.

`.context/2026-01-16_segment_architecture.md` claims *"ONE source of truth — segment_times from TTS generation. No fallbacks, no estimation."* For quiz options that source of truth **is** an estimation.

---

### #3 — Word timelines are built pre-concat and played post-concat, never reconciled · **ROOT CAUSE**

This is your "animations faster than the voice" bug.

`src/tts_bilingual.py:266-288`: per segment, ElevenLabs returns real character timings → `_chars_to_words` (`:195-214`); words are offset by `running`, which accumulates each segment file's own ffprobe duration (`:281`) plus hardcoded pauses (`:283-288`).

Then at `:298-300` the segments are concatenated **through a LAME re-encode**, and at `:306` the finished file is measured: `duration = get_audio_duration(output_path)`.

`_build_result` (`:321-356`) attaches the words **unchanged**. Every segment boundary contributes encoder delay and frame-granularity padding, so `Σ(per-segment ffprobe) + Σ(silences) ≠ ffprobe(concatenated)`. The visuals are keyed to the pre-concat timeline; the audio plays the post-concat file. The error is monotonic, always the same sign, and grows linearly with segment count — educational scripts produce dozens.

Three amplifiers, all verified:
- `src/animations/subtitle_processor.py:276-279` splits a segment's duration by **character count**, then clamps `min(word_duration, 1.5)` and never redistributes the remainder — `current_time = word_end` at `:299` carries the deficit forward, so every word after a clamped one fires early.
- `src/animations/subtitle_processor.py:462-480` `group_words` *rewrites* group ends to `next_start - 0.033`, pulling text off screen before its last word finishes. The v2 `timing_engine.py` docstring names this as the bug it exists to fix — **but the mutation still happens upstream in `group_words`, and v1 still ships it.**
- The four `*_segmented` generators publish `duration = running_time` (the pre-concat sum, `src/tts_elevenlabs.py:674`) while the renderer takes the real file's duration (`src/video/__init__.py:76-77`).

---

### #4 — No layout engine, no collision detection, and the auto-fit helper is a no-op · **ROOT CAUSE**

This is your overlapping-text bug, and it is deterministic.

`src/video/utils.py:133-146`:

```python
for size in range(max_font, min_font - 1, -2):
    ...
    if max_height is None or total_h <= max_height:
        return f, size, lines, total_h
```

**With `max_height=None` the first iteration always returns `max_font`. It never shrinks.** Four call sites omit `max_height`: `fill_blank.py:125` (the sentence card), `fill_blank.py:288` (option text), `vocabulary.py:99` (title), `vocabulary.py:332` and `:343` (row text).

Two of those then **throw the wrapped lines away and draw the raw string**:
```python
lf, _, _, _ = fit_text_font(es_text, _ROW_FONT, 28, left_col_w)   # vocabulary.py:332
draw_text_solid(draw, es_text, max(left_min_x, lx), ly, lf, ...)  # :338 — raw es_text
```
Same shape at `fill_blank.py:288-293`. The measurement is performed and discarded.

Third defect: `fit_text_font` computes line height as `int(size * 1.35)` (`utils.py:139`) while every caller redraws at `int(size * 1.4)` (`quiz.py:290`, `quiz.py:793`, `true_false.py:323`). Every box that "just fits" overflows by ~4%.

**There is not one bounding-box overlap check anywhere in the tree.** No renderer tracks occupied rectangles; nothing compares two elements' extents. Safe-area is enforced in exactly two places (`educational.py:269-273`, and as an input to the broken `fit_text_font` at `quiz.py:787`), and the two definitions disagree: v1 `SAFE_AREA_TOP/BOTTOM = 288/1632` (`config/layout.py:15-16`) vs v2 `SAFE_TOP/CONTENT_BOTTOM = 200/1600` (`v2/design.py:32-36`).

Concrete verified collisions:
- **Quiz explanation card overflows the bottom safe area during its own entrance.** `exp_y = COUNTDOWN_ZONE_TOP + 10 + slide_offset` (`quiz.py:783-784`). With the real `cool_20260416_084217.json` explanation, at `slide_offset=60` the card bottom is 1683 > 1632.
- **The same card reflows mid-animation.** `max_exp_h = SAFE_AREA_BOTTOM - exp_y - 56` (`quiz.py:787`) depends on the *animated* `exp_y`, so `fit_text_font` picks 28 px at the start of the slide and 30 px at the end — the font size changes during the 0.4 s entrance. Visible jitter.
- **fill_blank sentence card overlaps the first option card**: `_CARD_Y=250`, `card_h = max(140, total_h + 92)` with no height constraint → a 3-line sentence at the never-shrinking 48 px gives bottom 534 > `_OPTIONS_Y=520` (`fill_blank.py:39, 126`).
- **Vocabulary Spanish text crosses the divider into the English column**: `"la responsabilidad del gerente"` at 42 px measures 724 px into a 400 px column; `lx` clamps to 110 and the text spans x 110–834 through the divider at 500.
- `TIMER_BAR_Y = 1750` and `BAR_Y = 1850` (`config/layout.py:27, 86`) are both **below the 1632 safe line** — inside the platform's caption/action rail.

The one near-miss at collision awareness, `draw_two_column_row` (`utils.py:771-829`, with a `gap` and a clamp), is **dead code** — `vocabulary.py` reimplements it inline with a different gap.

---

### #5 — The QA layer is orphaned, and its core input is hardcoded empty · **ROOT CAUSE**

Full diagnosis in §6. The two headline facts:

1. **Neither analyzer is called by anything.** Repo-wide grep for `video_analyzer`, `quality_reviewer`, `QualityReviewer`, `analyze_video`, `passes_quality` returns zero hits outside the two files. `main.py:319-382` has no QC step; `admin.py:134-286` has no QC step; the Review page (`admin.py:1046-1121`) is a video player with Approve/Reject buttons and an **"Approve All"**.
2. **Every word-level check reads a `words[]` array the TTS writes as literally `[]`** — 9 sites, including `src/tts_elevenlabs.py:722, 933, 1152, 1316` and `src/tts_openai.py:920, 1119, 1320, 1467`. So `video_analyzer.py:713-718` short-circuits with `'No words found'`, which forces `timing_score = 0` (`:1510-1511`) and unconditionally appends `"Timing issues"` and `"Pacing issues"` to `critical_failures` (`:1594-1596`). **The analyzer returns FAIL for 100% of quiz/TF/fill_blank/vocabulary videos regardless of quality.** A detector that fires on every input carries zero information — which is the mechanical reason nobody kept it wired in.

The only quality gates that actually execute in production are three file-size assertions: `admin.py:214` (audio > 1000 bytes), `admin.py:257` (video > 1000 bytes), `src/video/__init__.py:395`.

---

### #6 — No data contract, and every default is a plausible wrong answer · **ROOT CAUSE**

There is no schema. No `jsonschema`, no `pydantic`, no `dataclass`, no `TypedDict` anywhere. The contract exists in three unsynchronized places: the GPT prompt f-strings (`script_generator.py:255-581`), a manual required-key dict (`:620-627`), and `dict.get(key, default)` at every read site.

Validation does not stop anything. Missing keys go into `script["_validation_errors"]` and the function **returns early** (`:634-636`); `generate_script` only *logs* them (`:833-834`) and returns the script anyway; `main.py:340-343` checks only `full_script`.

The renderers then fail **open**, never loud:

```python
correct = data.get('correct', 'A')     # src/video/quiz.py:582
```

A script that loses its `correct` key renders **option A with a green card, a glow, sparkles and "Respuesta: A"**. `fill_blank.py:313-315` renders the literal placeholder `"I ___ to school"` with options `['go','went','gone','going']`. `pronunciation.py:42` renders the word `"word"`.

**There is no "unknown" state anywhere in the render path. Every data failure ships as a polished, confidently incorrect lesson.** This is the single most dangerous property in the codebase for a system meant to run unattended at 2 videos/day.

Contract drift is real, not hypothetical: `options` is a **dict** for quiz (`quiz.py:581`) and a **list** for fill_blank (`fill_blank.py:314`); `correct` is a letter / a bool / a word depending on type; `translation` (str) vs `translations` (dict); `video_title`/`video_description` appear only in files dated 2026-04-14 and later.

---

### #7 — 66% of every generated quiz/TF/fill_blank script is dead payload · **ROOT CAUSE (cost + confusion)**

`script_generator.py:276-305, 355-373, 427-452` instructs GPT to produce **3 questions** and a `full_script` narrating all three. `output/scripts/quiz/cool_20260416_084217.json` carries `questions[3]`.

`generate_quiz_audio_segmented` reads only the **root-level** `question`/`options`/`correct`/`explanation` (`src/tts_elevenlabs.py:474-480`). `src/video/quiz.py:580-583` draws only the root-level question. **Nothing in `src/video/` or the TTS layer reads `questions`, `statements` or `sentences`** — verified by exhaustive grep; the only consumer is the duplicate-option check at `script_generator.py:794`.

Separately, **`full_script` is discarded entirely** for quiz/TF/fill_blank/vocabulary. The GPT-authored narration with its deliberate `...` pacing is generated, paid for, saved to disk, copied into the result JSON (`tts_elevenlabs.py:719`) — and never synthesized. The audio is reassembled from the structured fields instead. Two systems solving the same problem, neither aware of the other.

---

### #8 — "afabric" · **SYMPTOM** — but with a root cause worth naming precisely

The literal text sent to the API is `f"Opción {letter}, {word}."` → `"Opción A, fabric."` (`src/tts_elevenlabs.py:562`), joined with `" "` into one utterance (`:565`) and sent in a single call (`:570-579`). Letter and word are separated by **one comma inside one utterance**. `MODEL_ID` defaults to `eleven_v3`, which per the module's own comment at `:64-65` does **not** support `<break>`. There is no segment boundary, no silence file, no SSML.

Underneath it, a second real bug. `add_natural_pauses` (`:100-158`) has exactly one options rule, at `:139-144`:

```python
text = re.sub(r'(Opción [A-D0-4],\s*[^.]+\.)\s+(Opción)', r'\1 ... \2', text)
```

Because the match consumes the *following* `Opción`, `re.sub` skips it on the next scan. Executed against the real string:

```
in : 'Escucha las opciones. Opción A, fabric. Opción B, tela. Opción C, fabricar. Opción D, textura.'
out: 'Escucha las opciones. Opción A, fabric. ... Opción B, tela. Opción C, fabricar. ... Opción D, textura.'
```

**Pauses land after A and after C only. B→C gets nothing.** Option pacing is audibly uneven, on 1 of 3 boundaries.

Two fossils of the feature you now want, both defined and never used:
- `src/tts_openai.py:649` — `PAUSE_BETWEEN_LETTER_AND_CONTENT = 0.4`
- `src/tts_openai.py:408-573` — `fix_countdown_timing`, the real per-segment splicing implementation, 166 lines, zero callers

---

### #9 — Batch failures are render timeouts with the error discarded · **ROOT CAUSE**

From `output/generation_jobs.json`: 37 history records, 28 completed, **9 failed**. The three most recent (2026-04-16, consecutive, ~10m47s apart — each burned the full timeout):

| Job | Type | Step | Cause |
|---|---|---|---|
| `3e0dd307` cool | quiz | 4 render | `subprocess.TimeoutExpired … after 600 seconds` |
| `3d42776b` scared stiff | quiz | 4 render | same |
| `bbecac57` lay vs lie | quiz | 4 render | same |
| `cc2a36b1` sympathetic | fill_blank | 3 TTS | `httpx.ReadTimeout` from ElevenLabs |
| `67d09343` Making Plans | educational | 3 TTS | `ELEVENLABS_API_KEY not set` |
| ×3 | educational | 2 script | OpenAI `429 insufficient_quota` |
| `eb24255e` | fill_blank | 2 | `FileNotFoundError` — topic `"Meetings: Agreeing/Disagreeing"` → the `/` became a path separator (**since fixed**, `admin.py:158-160`) |

Why you see no useful error:
- The 600 s timeout at `admin.py:250-251` uses `capture_output=True`, so `subprocess.run` **discards `TimeoutExpired.stderr`**. You get a bare traceback and zero renderer log. The TTS branch at `:210-211` at least surfaces `stderr[-500:]`.
- Error chain: `except Exception` (`:278`) → `complete_job(error=error_msg[:2000])` (`:282`) → displayed truncated to 500 chars (`:1860`). A Python traceback puts the **cause at the bottom**, and both truncations cut from the front.
- `admin.py` has **no `logging.basicConfig`** (`main.py:35-42` does), so `logger.error` at `:283` goes nowhere visible.
- The queue itself is `st.session_state.queue_items` — **in-memory only** (`admin.py:751-752`), never persisted, unlike jobs. The whole batch runs synchronously inside one Streamlit script run; worst case per item is 300 s (TTS) + 600 s (render) = 15 minutes, so a 10-item queue blocks for up to 2.5 hours in a single request. Any browser reload destroys the queue and orphans the in-flight job in `jobs["active"]` forever — nothing ever reaps stale actives.

To answer your spec question directly: **one failure does not abort the batch** (`run_pipeline_with_tracking` catches everything at `:278-283`). But per-item errors are never displayed — `status_text` is a single `st.empty()` overwritten each iteration, and the final message is only `"Done! N successful, M failed"`. Also: every queued item is `{"type": t, "category": None, "topic": None}` (`:983`), so 10 items call `get_random_topic()` independently, and two collisions in the same second produce the same `unique_name` (second-resolution timestamp, `:159-162`) and silently overwrite each other.

**Note the cost shape:** a 600 s timeout has already paid for script + full TTS (~$0.085) and there is **no resume-from-audio**. A retry re-buys everything. 100% waste per timeout, and it happened three times in a row.

---

### #10 — Language is decided three to four times, by four different word lists, and the last one wins · **ROOT CAUSE**

Your "Spanish and English mixed into wrong segments" bug.

**Decision 1 — the only real one.** `src/tts_segmenter.py` (educational/pronunciation only) picks per-segment language from explicit script metadata, then quoted spans, then a hand-rolled scorer `looks_english` (`:81-116`). The result becomes `language_code` on the API call (`tts_bilingual.py:143-150`) — the authoritative answer, since it is the accent that was actually synthesized. This module is genuinely good work and is the only part of the language stack with real tests.

**Decision 2 — the renderer throws that away.** `src/video/__init__.py:208-228` rebuilds `is_english` from scratch against a *different* stoplist and assigns unconditionally at `:228`. **A word the model pronounced in English gets rendered in Spanish styling, and vice versa.**

**Decision 3 — quiz/TF/fill_blank/vocabulary have no language selection at all.** They pass `english_words` to `enhance_bilingual_text` (`tts_elevenlabs.py:161-209`), whose *only* action is substituting from a 13-entry phonetic table (`:182-196`, e.g. `'schedule' → 'skéjool'`). For any word outside that table it is a **complete no-op**. ES/EN is entirely at the model's discretion.

**Four copies of the Spanish stoplist, all differing:** `tts_common.py:60-83`, `tts_segmenter.py:40-56`, `tts_elevenlabs.py:248-262`, `video/__init__.py:177-207`, plus a fifth in `subtitle_processor.py:201-247`.

**And the input is poisoned upstream.** `script_generator.py:668-680` scrapes every `'…'` span from `full_script` into `english_phrases`, guarded only by `if any(len(w) > 1 for w in phrase_words)`. Since your scripts quote Spanish translations too, real files carry Spanish in `english_phrases` — `social_media_language_20260317_171457.json` lists `"me gusta tu outfit"` and `"qué increíble"`; `to_be_swamped_20260414_142502.json` lists `"i can"` and `"m swamped with deadlines"` (the apostrophe in *I can't* split the phrase).

**Root of the root:** the smart-quote normalizer that was supposed to prevent this is two no-ops and one accidental mangler. `script_generator.py:642-643`, confirmed by dumping the AST:

```
642  full_script = full_script.replace("'", "'").replace("'", "'")   # ASCII → ASCII, ×2 no-op
643  full_script = full_script.replace(', \'"\').replace(', '"')     # ← what Python actually parses
```

Line 643 contains `"""`, which Python reads as a triple-quoted string opener — so instead of normalizing typographic quotes it replaces the literal substring `, '").replace(` with `"`. The typographic quotes were flattened to ASCII at some point (editor or paste), turning the whole normalization step into dead code plus one nonsense substitution. Everything downstream — the balance count at `:646-665`, the `english_phrases` extraction at `:669` — runs on un-normalized text. This is the origin of the `"Unbalanced single quotes (51)"` warning shipped inside `output/scripts/quiz/cool_20260416_084217.json:68`, and of the quote-boundary repair at `:646-665` that *moves* quote boundaries and therefore moves language boundaries.

---

## 3. Structure

### 3.1 File tree with line counts

Files over 500 lines are marked ⚠. Total: 62 files, 27,104 lines.

```
english-ai-videos/
├── main.py                                709  ⚠
├── config.yaml                            (3.7 KB)
├── requirements.txt                       (missing elevenlabs, google-cloud-texttospeech, pydub, httpx)
├── config/                                EMPTY DIRECTORY
├── src/
│   ├── __init__.py                         70   ← byte-identical clone of tts_providers/__init__.py
│   ├── admin.py                          1877  ⚠  Streamlit dashboard (9 pages)
│   ├── backgrounds.py                    1839  ⚠  BackgroundGenerator, 13 render modes
│   ├── video_analyzer.py                 1838  ⚠  ORPHANED
│   ├── tts_openai.py                     1668  ⚠
│   ├── tts_elevenlabs.py                 1501  ⚠
│   ├── script_generator.py                975  ⚠
│   ├── uploader.py                        917  ⚠
│   ├── quality_reviewer.py                840  ⚠  ORPHANED
│   ├── tts.py                             817  ⚠  Edge TTS, legacy
│   ├── tts_google.py                      514  ⚠  quiz only; else prints "Unsupported"
│   ├── generate_backgrounds.py            480      ORPHANED (DALL·E asset script)
│   ├── tts_bilingual.py                   420
│   ├── tts_common.py                      405
│   ├── tts_segmenter.py                   405
│   ├── generate_character.py              397      ORPHANED (DALL·E asset script)
│   ├── cost_tracker.py                    283
│   ├── metadata_generator.py              272
│   ├── test_voice_settings.py             178      MISFILED — pytest would collect it and spend money
│   ├── profiles.py                        103
│   ├── tts_base.py                         75
│   ├── generate_app_icon.py                56      ORPHANED
│   ├── animations/
│   │   ├── easing.py                      621  ⚠  53% dead (329 lines unreachable)
│   │   ├── subtitle_processor.py          482
│   │   └── __init__.py                     30      ORPHANED
│   ├── config/                                     (Python constants, NOT user config)
│   │   ├── colors.py    106   layout.py    91   secrets.py 181 ORPHANED
│   │   ├── timing.py     51   typography.py 33   __init__.py 13 ORPHANED
│   ├── tts_providers/
│   │   ├── __init__.py 70  elevenlabs_provider.py 162
│   │   ├── openai_provider.py 73  edge_provider.py 58  google_provider.py 50
│   └── video/                                      ← this is what you call "src/video.py"
│       ├── utils.py                       862  ⚠  27 drawing primitives, 2 dead
│       ├── quiz.py                        847  ⚠  create_frame_quiz = 276 lines
│       ├── character.py                   773  ⚠  sprite compositor (disabled in config)
│       ├── educational.py                 734  ⚠  v1 renderer
│       ├── true_false.py                  625  ⚠  create_frame_true_false = 342 lines (55%)
│       ├── __init__.py                    470      generate_video = 360 lines
│       ├── fill_blank.py 385   vocabulary.py 371   karaoke.py 355 (DEAD)
│       ├── backgrounds.py 297   compositor.py 194   clip_background.py 162
│       ├── pronunciation.py 100   constants.py 80   __main__.py 3
│       └── v2/                                     ← newest generation, educational only
│           ├── educational.py             624  ⚠  best-organized large file in the repo
│           ├── character_director.py      336
│           ├── timing_engine.py           241      best-specified module in the repo
│           ├── design.py 212   background.py 169   motion.py 121   __init__.py 9
└── tests/
    ├── test_tts_segmenter.py              234      the one genuinely good test file
    ├── test_tts.py                        138      Edge TTS only; makes live network calls
    └── test_timing_engine.py              102      crashes on default invocation
```

**18 files over 500 lines = 16,824 lines = 62% of the codebase.** Of those, 5 earn their size through genuine cohesion (`backgrounds.py`, `uploader.py`, `v2/educational.py`, and arguably `script_generator.py`, `video/utils.py`). The other 13 are god-modules, god-functions, orphaned tooling, or copy-paste forks.

### 3.2 Entry points

| # | Invocation | Path |
|---|---|---|
| 1 | `python main.py [--random\|--script\|--topic\|--batch…]` | `main.py:447-591` → profile → `generate_script()` in-process → `run_tts()` via `tts_providers` factory → `run_video()` **subprocess** `python3 -m video` (cwd=`src/`) → optional upload |
| 2 | `python main.py clean […]` | `main.py:612-698` — a second, unrelated argparse program in the same file |
| 3 | `python main.py costs [DAYS]` | `main.py:704-707` — **note: `from src.cost_tracker import …`**, a different module object from the pipeline's `from cost_tracker import …` (see §3.4) |
| 4 | `./run_admin.sh` → `streamlit run src/admin.py` | `admin.py:689-760` page dispatch → `run_pipeline_with_tracking()` (`:134-286`) → **two subprocesses**, bypassing `main.py` and `tts_providers` entirely |
| 5 | `python3 -m video -a … -d … -o … [-t] [--v2] [--karaoke] [--renderer]` | `src/video/__main__.py` → `video.main()` (`__init__.py:403-466`) → `generate_video()` (`:41-400`) |

Plus 13 modules with their own `if __name__ == "__main__"` script mode, four of which `admin.py` invokes directly.

### 3.3 Symbol map — the six heaviest render/orchestration files

Line ranges are exact (extracted via `ast`).

**`src/video/__init__.py` (470)**

| Symbol | Lines | Purpose |
|---|---|---|
| `get_recommended_preset` | 35-36 | `None`-returning stub in the `except ImportError` branch |
| `generate_video` | 41-400 | **360 lines, ~10 responsibilities**: load audio duration + data JSON, resolve v1/v2 engine, resolve and pre-render background, re-derive `is_english` flags (177-232), build the per-type frame generator, encode via ffmpeg with MoviePy fallback |
| `main` | 403-466 | argparse for `python -m video` |

**`src/video/quiz.py` (847)**

| Symbol | Lines | Purpose |
|---|---|---|
| `find_word_time` | 44-51 | Linear scan for a word's timestamp |
| `find_phrase_time` | 54-62 | **DEAD** — zero callers |
| `parse_quiz_timestamps` | 65-221 | 157-line keyword heuristic reconstructing quiz beats from raw Whisper words. `.context/` claims this was deleted; it was not |
| `draw_quiz_timeline` | 224-265 | Top-of-frame segment bar |
| `draw_quiz_question_box` | 271-334 | White question card |
| `draw_quiz_option_card` | 337-451 | One option card with reveal/correct/incorrect states |
| `draw_countdown_number` | 454-516 | Pop-in + glow digit |
| `resolve_quiz_timestamps` | 519-569 | Prefer `segment_times`, else fall back to the parser |
| `create_frame_quiz` | 572-847 | **276-line god-function** — entire quiz frame |

**`src/video/true_false.py` (625)**

| Symbol | Lines | Purpose |
|---|---|---|
| `parse_true_false_timestamps` | 59-109 | Keyword heuristic |
| `resolve_true_false_timestamps` | 112-145 | `segment_times` with parser fallback |
| `_draw_button` | 150-216 | Gradient ✓/✗ button |
| `_draw_countdown_number` | 221-279 | Near-duplicate of `quiz.draw_countdown_number` |
| `create_frame_true_false` | 284-625 | **342 lines = 55% of the file.** Largest single function in the render layer |

**`src/video/educational.py` (734)**

| Symbol | Lines | Purpose |
|---|---|---|
| `add_sentence_boundaries` | 39-92 | **The most reused symbol in the repo** — imported by `video/__init__.py`, `tts_bilingual.py`, `tts_elevenlabs.py`, `elevenlabs_provider.py`, `tests/test_timing_engine.py`. This is why v1 educational can never simply be deleted |
| `create_frame_educational` | 95-127 | Frame entry point |
| `_lookup_translation` | 130-161 | Exact-then-60%-overlap lookup |
| `_render_group_tiktok` | 164-319 | 156-line layout + render of one group |
| `_english_hero_size` | 322-329 | Cap hero font by word count |
| `_render_english_card` | 332-431 | Dark glass card: English word + translation |
| `_render_spanish_karaoke` | 434-550 | Word-by-word karaoke. **Contains the `offset_x` shadowing bug (§4)** |
| `_render_english_hero` | 553-688 | Large English hero word |
| `_render_text_simple` | 691-734 | No-timing fallback |

Note the shape: five `_render_*` functions of 44-136 lines each sharing a 14-parameter calling convention. The parameter list is the tell — the shared state wants to be an object, which is exactly what v2 did.

**`src/video/utils.py` (862)** — 27 primitives. Notable: `fit_text_font` 133-146 (**broken**, §4), `draw_glass_button` 404-492 (**dead**, 89 lines), `draw_two_column_row` 771-829 (**dead**, 59 lines), `create_base_frame` 535-544, `finalize_frame` 547-562, `resolve_countdown_number` 585-611, `draw_rounded_card` 617-652.

**`src/video/v2/timing_engine.py` (241)** — `_last_word_end` 47-51, `_min_duration` 54-55, `_merge_short_groups` 64-109, `compute_display_windows` 112-180, `validate_windows` 183-206 (asserts, called from `:179`), `group_alpha` 209-226, `debug_table` 229-241. The 31-line module docstring names the exact v1 bugs it replaces. **Best-specified module in the codebase.**

**`src/video/compositor.py` (194)** — `render_video_ffmpeg` 22-92, `_encode` 95-194. Single responsibility, documented failure modes (including the stderr-pipe deadlock comment at `:111-113`), correct resource cleanup. **Cleanest module in the repo.**

### 3.4 Dead code and duplication

**Orphaned modules — 13, ~4,500 lines:** `video_analyzer.py` (1838), `quality_reviewer.py` (840), `generate_backgrounds.py` (480), `generate_character.py` (397), `config/secrets.py` (181), `test_voice_settings.py` (178), `generate_app_icon.py` (56), `src/__init__.py` (70), `animations/__init__.py` (30), `config/__init__.py` (13), and the 3 test files.

**Dead-by-flag:** `video/karaoke.py` (355) — reachable only via `--karaoke`, which neither entry point passes. `video/v2/*` (1,802) — reachable only via `--v2`, which `admin.py` never passes.

**Unreachable functions (zero references), largest first:**

| Location | Symbol | Lines |
|---|---|---|
| `src/tts_openai.py:408-573` | `fix_countdown_timing` — *the real segment-based countdown fix* | 166 |
| `src/video/utils.py:404-492` | `draw_glass_button` | 89 |
| `src/animations/easing.py:502-577` | `word_emphasis_animation` | 76 |
| `src/video/utils.py:771-829` | `draw_two_column_row` | 59 |
| `src/animations/easing.py:386-441` | `spring_with_anticipation` | 56 |
| `src/animations/easing.py:446-499` | `tiktok_viral_pop` | 54 |
| `src/tts_common.py:333-379` | `validate_script_for_tts` | 47 |
| `src/tts_common.py:126-167` | `concatenate_audio_files` — the shared concat that 4 copies ignore | 42 |
| `src/animations/easing.py:314-381` | `follow_through_offset`, `squash_stretch` | 66 |
| `src/animations/easing.py:273-311` | `anticipation_scale` | 39 |
| `src/tts_openai.py:95-127` | `prepare_bilingual_text` — body is comments + `pass` | 33 |
| `src/tts_openai.py:666-687` | `get_or_generate_word` — **the word cache, defined and never called**; its docstring at `:629-640` still advertises caching as the architecture. `WORDS_DIR` stays empty forever and every run re-pays | 22 |

`src/animations/easing.py` is **53% dead** — 329 of 621 lines across 8 unreferenced functions.

**Dead constants:** `PAUSE_BETWEEN_LETTER_AND_CONTENT = 0.4` (`tts_openai.py:649`), `PAUSE_AFTER_TRANSITION`, `PAUSE_AFTER_ANSWER_PHRASE` (same block), `STAGGER = 0.12` (`quiz.py:659`), the entire `VOICES` dict (`tts_elevenlabs.py:45-56`, 10 voice IDs, never read), `config/timing.py:36-42` `PAUSE_AFTER_*` labelled "single source of truth" with **0 consumers** (the real ones are in `tts_common.py:31-37`).

**`src/__init__.py` is a byte-identical copy of `src/tts_providers/__init__.py`** — md5 `ebd37ef2f22d0acfe14edeb420d6d1b7`, both 1,952 bytes. Verified.

**TTS duplication, measured (SequenceMatcher on full function text):**

| Function | ElevenLabs | OpenAI | Similarity |
|---|---|---|---|
| `generate_fill_blank_audio_segmented` | 736-950 | 930-1126 | **0.74** |
| `generate_true_false_audio_segmented` | 953-1169 | 1129-1327 | **0.73** |
| `generate_vocabulary_audio_segmented` | 1172-1333 | 1330-1475 | **0.72** |
| `generate_quiz_audio_segmented` (EL vs **Google**) | 452-733 | `tts_google.py` | **0.84** |

And internally: within `tts_openai.py`, fill_blank vs true_false = **0.81**; same pair within `tts_elevenlabs.py` = **0.81**.

**≈1,700 lines that are variations on one ~200-line function.** `tts_common.py` exists as the shared-helper module and is imported by all of them — but only for leaf utilities. The segment-assembly logic was never hoisted.

**`main.py` imports `cost_tracker` two different ways** — `from cost_tracker import reset_tracker` (`:327`) and `from src.cost_tracker import print_report` (`:705`). Python treats these as **two distinct module objects**, each with its own `_current_tracker` global (`cost_tracker.py:196`). The `costs` subcommand and the pipeline never share tracker state; it works only because `costs` reads from disk.

**No TODO/FIXME/HACK markers anywhere** (one false positive: `script_generator.py:360`, Spanish *"todo"* inside a prompt). **No commented-out blocks ≥10 lines.** This is AI-assisted code where problems were rewritten rather than annotated — which is precisely why the archaeology above is necessary.

### 3.5 The four generations

| Gen | What | Where it lives | Who runs it |
|---|---|---|---|
| 1 | Manual prompt → paste into Claude | `README.md`, `script_generator.py` CLI flags | vestigial |
| 2 | Monolithic TTS + v1 renderers + sprite character | `tts_{openai,elevenlabs,google}.py`, `video/*.py`, `character.py` | **`admin.py` — your daily driver** |
| 3 | Abstraction pass (~2026-01) | `tts_base.py` + `tts_providers/`, `tts_segmenter.py` + `tts_bilingual.py`, `config/`, `animations/`, `compositor.py`, segment-based timing | `main.py` only |
| 4 | v2 (newest) | `video/v2/` (1,802 lines), `clip_background.py`, `profiles.py`, kids profile, `docs/` | `--v2` flag only, educational only, **unreachable from the dashboard** |

The direction of travel is unambiguous and the newest code is the best code. **Nothing from generations 1-3 has been retired.** Your primary UI runs the second-oldest architecture.

---

## 4. Data contracts

Covered in §2 #6. Additional specifics:

**Real shape per type**, from actual files:

- **quiz** — `type, question, options{A,B,C,D}, correct, explanation, full_script, translations{}, hashtags[], _meta{}` + (2026-04 onward) `video_title, video_description, questions[3]{}`, sometimes `_validation_warnings[]`
- **educational** — `type, hook, full_script, english_phrases[], translations{}, tip, cta, hashtags[], _meta` + (2026-04) `video_title, video_description`
- **fill_blank** — `type, video_title, video_description, sentence, blank_position, options[] (**list**, unlike quiz's dict), correct, explanation, translation (**singular str**), sentences[3]{}, full_script, hashtags[], _meta`
- **true_false** — `type, statement, correct (**bool**), explanation, statements[3]{}, full_script, translations{}, hashtags[], _meta`. No `video_title` despite the prompt demanding it at `script_generator.py:391-392`
- **pronunciation** — `type, word, phonetic, common_mistake, tip, full_script, translation (str), hashtags, _meta`
- **vocabulary** — `type, title, difficulty, pairs[]{spanish,english}, full_script, translations{}, english_phrases[], hashtags, _meta`

**Segment timings** — four mechanisms coexist:

| Type | Mechanism |
|---|---|
| quiz / TF / fill_blank / vocabulary | Running sum of ffprobe-measured clips + **hardcoded silences** (`tts_common.py:31-37`) + **estimated option boundaries** (§2 #2) |
| educational (bilingual, default via `main.py`) | Real ElevenLabs character timings per segment, offset by pre-concat running sum, **never reconciled to the final file** (§2 #3) |
| educational (Whisper fallback) | `extract_timestamps_whisper` over the finished mp3 — **the only genuinely reconciled path**, and it is the fallback |
| pronunciation | `duration * 0.25 / 0.50 / 0.80` — fixed fractions, **nothing derived from the narration** (`pronunciation.py:50-52`) |

**Type branching is scattered across 16 sites in 11 files:** `script_generator.py:588-601, 690, 785-819, 946-967`; `main.py:422-439`; `video/__init__.py:157, 265, 281, 290, 298, 305, 313` and the v2 gate at `:92-96`; `elevenlabs_provider.py:35-51`; `openai_provider.py:35+`; `tts_elevenlabs.py:1395-1407`; `tts_openai.py:1524-1530`; `tts_google.py:498`; `quality_reviewer.py:409, 597-601`; `video_analyzer.py:723, 1702`; `admin.py:1072`; `config.yaml:86-91`.

There is **no dispatch table, factory or registry.** `VIDEO_TYPES` (`script_generator.py:35`) is a bare list used only for argparse `choices`. Adding a seventh type requires editing at minimum `script_generator.py` (×4), `video/__init__.py` + a new module, two TTS providers (×2 each), `main.py`, and `config.yaml`. **This is directly relevant to roadmap step 3** — see §10.

---

## 5. Audio path

Full trace and the option/countdown verdict are in §2 #2 and #8. Additional facts:

**Concatenation** is always the ffmpeg concat demuxer, never pydub/filter/byte-append — implemented **four times** in `tts_elevenlabs.py` (`:682-699, 896-914, 1110-1129, 1273-1292`, all with re-encode `-q:a 2 -ar 44100 -ac 1`), **four times** in `tts_openai.py` (`:877-899, 1082-1100, 1279-1297, 1425-1443`, all with `-c:a copy`), once in `tts_google.py:381-401`, once in `tts_bilingual.py:290-303`. The shared `tts_common.concatenate_audio_files` (`:126-167`) is called from nowhere.

**`-c:a copy` in the OpenAI paths is a latent format bug.** It mixes TTS MP3s (rate set by the API), silence generated explicitly at 44100 Hz **stereo** (`tts_openai.py:714`), and pre-recorded assets of unknown format — with **no resampling and no channel conversion**. Decoders honour the first frame header, so silence blocks play at the wrong duration while `running_time` bookkeeping assumes the nominal value. ElevenLabs avoids this by re-encoding. *I could not verify magnitude — `assets/` is not present in the copy I staged.*

**Silence** is generated as real MP3 files via `ffmpeg -f lavfi -i anullsrc` (`tts_common.py:106-123`) and inserted into the concat list. **`generate_silence` never checks the return code** (`:123` is a bare `subprocess.run`), so a failed silence write yields a missing/0-byte file that is still appended to `audio_files` and still added to `running_time`.

**Retries:** 3 attempts with `2**attempt` backoff in `tts_elevenlabs.py:345-370` and `tts_openai.py:576-599`. **Cost is logged *before* the loop** (`:349-356`, `:580-587`) — up to 3 billed attempts recorded as 1. `tts_bilingual._synthesize_segment` has **no retry**: `convert_with_timestamps` is called bare at `:167`, and `except Exception` at `:185-187` logs at **INFO** ("with_timestamps unavailable") and silently downgrades to plain convert, losing exact alignments. An expired key, a 429, and a model rejecting `language_code` all present identically, and the run still "succeeds."

**`main.py:148-153` catches any TTS exception and falls back to Edge TTS** — silently changing voice, language handling and output schema (Edge produces no `segment_times`, so the renderer drops to keyword parsing).

**`main.py`'s script/TTS merge guard is broken** (`:163-165`):
```python
if key not in tts_data or key != 'words':
```
This is `True` for every key except `'words'`-already-present. `segments`, `segment_times` and `duration` are **not protected**. `admin.py:225` gets it right; `.context/2026-01-16_segment_architecture.md:99` claims `main.py` protects them. Currently latent, one script-format change away from silently destroying all timing.

---

## 6. Quality control — why it caught nothing

Both analyzers are orphaned (§2 #5). Assuming you ran them, here is the per-bug verdict.

| Your bug | Catchable in principle? | Why it wasn't |
|---|---|---|
| Countdown "3… atención 2… atención" | Partly | `analyze_countdown_timing` only measures **gaps**, never checks for interpolated words. Moot anyway: countdown is silent, `words[]` is `[]`, the check returns `found:False` and — critically — `video_analyzer.py:759-767` **drops unfound checks from the average instead of penalizing them**. The historical fix is a defensive regex at `tts_openai.py:204` stripping `atención\|piensa\|bien` — applied at the *generator*, never verified at the *output* |
| "afabric" | **No** | No pronunciation or word-segmentation check exists. The only option check is inter-option timing. The root cause is that boundaries are *guessed*, never measured — so nothing can compare intent to reality. Catching this needs waveform analysis or forced alignment; neither exists |
| Wrong accents | **No** | Zero accent/language-ID on audio. `analyze_language_correctness` inspects a boolean flag in JSON — metadata about metadata, never the waveform. And with `words[]` empty it reports **100/100** (`:974-978`), while `quality_reviewer.py:504-505` emits `add_positive("Word language marking looks correct")` |
| Words skipped | **No** | Would require transcribe-and-diff of the rendered audio. `analyze_pacing` uses the TTS's own word list — if TTS drops a word the JSON drops it too, so the ratio stays consistent. Structurally undetectable by this design |
| Voice glitching | Weakly | Only ffprobe metadata + whole-file `volumedetect` max/mean. A 200 ms artefact doesn't move a whole-file mean; the only peak rule is `max > -1.0 dB`. **The docstring at `video_analyzer.py:7` advertises "Glitch/break detection (sudden volume changes)" — that check was never implemented** |
| Animations faster than voice | **This is the biggest miss** | `analyze_pacing` compares only *total* audio duration to *total* video duration with 1.0 s tolerance (`:1134-1137`) — and video length is **derived from** audio length (`video/__init__.py:76-80`). **The check is tautological: it can never fail.** Nothing anywhere compares `segment_times` to measured audio |
| ES/EN in wrong segments | Yes, in principle | Validates against a 24-word hardcoded list (`:936-950`) whose overlap with real scripts is near-zero, on an empty `words[]`. `quality_reviewer.py:470-475` builds `expected_english` from `english_phrases`, which quiz scripts don't carry → empty → both loops find nothing → **false positive** |
| Text overlapping | **No — and worse** | `analyze_layout_balance` (`:248-284`) computes one intensity-weighted centroid over the whole frame. **Two overlapping text blocks produce a *more* centred mass than two separated ones**, and `:1383-1384` awards **+15** for `is_centered`. The metric is *anti-correlated* with the bug. No OCR, no bounding boxes, no z-order |

**Six structural reasons, in order of severity:**

1. **Never invoked.** Zero callers.
2. **Core input hardcoded empty.** `words[]` is `[]` for 4 of 6 types → the analyzer fails 100% of them for content-free reasons; a detector that always fires carries zero information.
3. **Written against a deleted architecture.** Both look for spoken `"tres… dos… uno"`. It's silence now. Neither reads `segments` or `segment_times` at all.
4. **Silent self-exclusion.** `video_analyzer.py:759-767` and `quality_reviewer.py:426-432` — a check that can't find its subject is dropped from the average, not penalized. Absence of evidence scores as evidence of absence.
5. **Reference comparison compares the video to itself.** `REFERENCES_DIR` (`:57`) does not exist; with `--compare` off, `main()` calls `generate_improvement_report(video_analysis, video_analysis, {})` (`:1576-1578`). Half of that function is structurally dead.
6. **Exception swallowing.** `quality_reviewer.py:107-108` (`except: return []`), `:317-324` (bare `except: pass` → volume checks silently skipped), `:352-357` (any audio exception downgraded to a warning). `video_analyzer.py:922-928` returns `score: 0` on any exception — indistinguishable from a real quality failure.

**Sampling is also inadequate:** `quality_reviewer.py:518` samples exactly 5 frames at t = 0.5, 2, 5, 10, 15 s and declares "animations might not be working" if the mean diff between frames **five seconds apart** is < 5. `video_analyzer.py:1275` samples every 0.5 s — 1 frame in 15 at 30 fps, blind to anything shorter than 500 ms. Neither looks past 15 s into the second half of a 30 s video.

**Not an LLM reviewer** — neither file calls a model. All findings are canned strings. The failure mode is worse than agreeable-LLM: hardcoded rules against stale data shapes.

**The lesson for step 2, stated as a rule:** every check must run on the *rendered artifact* (waveform, pixels), never on the JSON that the generator itself produced. Six of the twelve checks above fail purely because they audit the generator's own self-report. Your instinct in the roadmap — waveform-based blended-segment detection via `silencedetect`/RMS rather than forced alignment — is correct, and it is correct for a broader reason than the one you gave: **not just because aligners degrade on digits and letters, but because the aligner's input is the same artifact the bug lives in.**

---

## 7. Testing

**3 files, 474 lines, ≈1.7% of 27,104.**

| File | Lines | Verdict |
|---|---|---|
| `tests/test_tts.py` | 138 | 8 unittest cases against **Edge TTS only** — the free fallback nobody uses. Makes **live network calls** (`:76`, `:30`) and writes real MP3s. No mocks. Zero coverage of `tts_elevenlabs.py` (1501), `tts_openai.py` (1668), `tts_bilingual.py` (420) |
| `tests/test_tts_segmenter.py` | 234 | **The one genuinely good test file.** 7 hand-written cases, ~30 assertions, real problem inputs inlined, pure-function, no network. Covers `tts_segmenter.py` only. Uses a custom `check()` collecting into a module global rather than `assert` |
| `tests/test_timing_engine.py` | 102 | Not a unit test — loads one real data file and asserts invariants (golden rule, min hold, no overlap, alpha bounds). **Default path `output/audio/educational/give_up_20260113_185732.json` does not exist**, so with no argv it dies with `FileNotFoundError` at line 37. The only test touching the subsystem responsible for your timing-drift bug class **cannot be run without an undocumented argument** |

**Plus one misfiled file:** `src/test_voice_settings.py` (178) is not a test — it's an A/B utility that makes **12 paid ElevenLabs calls** (`:100-110, :150-157`). It lives in `src/` and **matches pytest's default collection pattern**, so `pytest src/` spends real money.

**Fixtures / golden files / regression corpus / CI:** none. No `tests/fixtures/`, no `golden/`, no `references/`, no `conftest.py`, `pytest.ini`, `pyproject.toml`, `tox.ini`, `Makefile`. **No `.github/` directory — zero CI.** `requirements.txt` doesn't list pytest.

**Zero coverage** on: `admin.py`, `backgrounds.py`, `video_analyzer.py`, `tts_openai.py`, `tts_elevenlabs.py`, `script_generator.py`, `uploader.py`, `quality_reviewer.py`, the entire `src/video/` package (~5,300 lines), `cost_tracker.py`, `profiles.py`, `metadata_generator.py`, `config/secrets.py`.

The 11 real script JSONs in `output/scripts/*/` are the only corpus that exists, and no test uses them.

---

## 8. Config vs hardcoded

**The root `config/` directory is empty.** `src/config/*.py` are **Python constant modules, not user configuration** — editing them is a code change. `src/video/constants.py` exists purely to re-export them for backward compatibility.

**What `config.yaml` actually controls:**

| Section | Effective? |
|---|---|
| `video.background_mode`, `default_background`, `enabled_backgrounds` | **Yes** (`video/backgrounds.py:39-52`) |
| `video.width`, `height`, `fps` | **No — dead knobs.** Written by the Settings UI (`admin.py:1718-1739`), read by nothing. Real source of truth is `config/layout.py:8-10`. Changing FPS in the dashboard does nothing |
| `video.animation_style` | **No** — written, never read |
| `audio.*` (provider, voice_id, model, stability, style, speeds, langs) | **Only on the `main.py` path.** `admin.py` never imports `profiles`, so the dashboard runs on `.env` + module defaults and ignores every `audio:` key |
| `audio.provider` | **No** — provider selection is env-only (`main.py:127`) |
| `audio.speaker_boost`, `audio.humanize` | **No** — written by the UI (`admin.py:1795-1796`), never consumed |
| `output.videos/audio/frames` | **No** — paths come from `main.py:47-64` and `admin.py:42-49` |
| `character.*` | Yes |
| `upload.platforms` | Yes; `upload.hashtags` **never read** |
| `profile`, `profiles.*` | `main.py` path only |

**Config-write data loss:** `admin.py:1731-1752` "Save Video Config" rebuilds `config.yaml` from only `{video, audio, output, content}` and `yaml.dump`s it over the file. **`character:`, `upload:`, `profile:` and `profiles:` are silently deleted.** One click in the Settings UI wipes your kids profile, hashtags and upload platform list.

**Hardcoded values that should be config:**

*Voice IDs & models* — 10 ElevenLabs UUIDs in a **never-read** `VOICES` dict (`tts_elevenlabs.py:45-56`); active default `"ZOgeDYxfyev5qgOXq2lN"` hardcoded at `:63-64`, again at `tts_bilingual.py:76`, again at `.env.example:22`; `DEFAULT_SIMILARITY = 0.80` (`:75`) with **no env or config override at all**; `MODEL_ID` default `eleven_v3` (`:66`); `eleven_turbo_v2_5` (`tts_bilingual.py:79`); `MODEL = "gpt-4o-mini"` (`script_generator.py:31`); `model="tts-1-hd"` at **14 sites** in `tts_openai.py` (bypassing its own `DEFAULT_MODEL = "tts-1"` at `:91`); `model="whisper-1"` (`:356`); `model="dall-e-3"` (`generate_character.py:241`, `generate_backgrounds.py:309`); `"KIDS_VOICE_ID_PENDIENTE"` (`config.yaml:106`) — a placeholder that would be sent to the API verbatim.

*Timings* — `countdown_interval = 1.5` at **5 duplicated sites** (`tts_openai.py:820, 1039, 1236`; `tts_elevenlabs.py:624, 852, 1067`); `transition_duration = 1.5` + `/4` at 2 sites; `add_silence(1.0)` dramatic pause ×2; all 7 TTS pauses (`tts_common.py:31-37`) **and a duplicate unused copy** (`config/timing.py:36-42`); TTS timeout 300 s and render timeout 600 s (`admin.py:208, 251`); ffmpeg concat timeout 120 s; scheduler intervals `[15,30,60,120,240]` (`admin.py:1541`).

*Colors* — 36 constants + 5 dicts in `config/colors.py`; inline RGBA literals bypassing them at `quiz.py:235, 245, 247, 249, 300, 373, 425, 513`, `fill_blank.py:54-55, 274`, `educational.py:627`; a **separate** v2 token set at `v2/design.py:125-165`; ~180 lines of inline dashboard CSS at `admin.py:511-690`.

*Fonts* — 20 sizes in `config/typography.py:7-33`; absolute font paths for three OSes at `video/utils.py:37-53` and a **different** set at `v2/design.py:49-78`.

*Thresholds* — 15 in `quality_reviewer.py:40-65`, 25 in `video_analyzer.py:63-100` (both orphaned); file-size floor `1000` bytes ×3; `MAX_PAUSE_MARKERS = 5`; `max_retries = 3` ×2; history caps 50/10.

*Resolution/FPS* — `1080/1920/30` appears **six times**: `config/layout.py:8-10` (canonical), `v2/design.py:30-31`, `backgrounds.py:31-33`, `backgrounds.py:517`, `compositor.py:27-29`, `quality_reviewer.py:40-41`.

*Paths* — **`run_admin.sh:17-18` hardcodes `/Users/go/Library/Python/3.9/bin/streamlit`**, a specific machine's Python 3.9 path, committed as a fallback branch. Also `REFERENCES_DIR` (never created), `HISTORY_DIR` with an **import-time `mkdir` side effect** (`quality_reviewer.py:34-35`).

*Word lists* — 4 overlapping, unsynchronised Spanish stoplists (§2 #10) plus `ENGLISH_WORDS`/`SPANISH_ENGLISH_OVERLAP` (`tts_openai.py:55-79`) and `EMPHASIS` (`config/timing.py:45-51`).

---

## 9. Cost surface

**Every paid call site:**

| # | API | Location | Model |
|---|---|---|---|
| 1 | OpenAI Chat — script | `script_generator.py:745-753` | `gpt-4o-mini`, `max_tokens=3000`, `temp=0.7` |
| 2 | OpenAI Chat — duplicate-option retry | `script_generator.py:805-809` | same, **no `temperature`** (silently falls back to 1.0) |
| 3 | OpenAI Chat — metadata | `metadata_generator.py:157-166` | `gpt-4o-mini`, `max_tokens=500` |
| 4 | OpenAI TTS | `tts_openai.py:576-598` | `tts-1-hd` (14 sites) |
| 5 | OpenAI Whisper **(paid)** | `tts_openai.py:355-361` | `whisper-1`, `verbose_json`, word granularity |
| 6-8 | OpenAI Images | `generate_backgrounds.py:308`, `generate_character.py:240`, `generate_app_icon.py:33` | `dall-e-3`, `1024x1792`, `quality="hd"` |
| 9 | ElevenLabs TTS | `tts_elevenlabs.py:345-368` | `eleven_v3` |
| 10 | ElevenLabs TTS + alignment | `tts_bilingual.py:167` | `eleven_turbo_v2_5` |

**Per-video cost.** Measured TTS payload for a quiz: question ~40 chars + combined options ~120 + "¡Piensa bien!" 13 + answer ~50 + explanation ~150 ≈ **380 chars** (countdown is silence → free). Script generation ≈ 1,000 input + 600 output tokens = $0.0005.

| Path | Script | TTS | Whisper | **Total** |
|---|---|---|---|---|
| quiz / TF / fill_blank / vocab (ElevenLabs) | $0.0005 | $0.084 | — | **≈ $0.085** |
| educational via `main.py` (turbo bilingual) | $0.0005 | $0.088 | — | **≈ $0.089** |
| **educational via dashboard** (v3 legacy + Whisper) | $0.0005 | $0.176 | $0.006 | **≈ $0.183 — 2×** |
| same with `TTS_PROVIDER=openai` (`tts-1-hd`) | $0.0005 | $0.024 | $0.006 | ≈ $0.031 |

**At 2 videos/day: $0.17–0.37/day ≈ $5–11/month.** Not a budget problem in itself.

**What is a problem:**

- **Timeout-then-throwaway.** Each of the 3 most recent failures paid for script + full TTS, then died at 600 s and **discarded the audio**. No resume-from-audio exists; a retry re-buys everything. ~100% waste per timeout.
- **The dashboard costs 2× for identical educational output** (v3 + Whisper vs turbo-with-alignment) — a direct consequence of problem #1.
- **`admin.py` has zero cost tracking.** TTS runs as a subprocess, so its in-process tracker dies unsaved. **Every video generated through your primary UI is invisible to cost accounting.**
- **Cost is logged before the retry loop** (`tts_elevenlabs.py:349-356`, `tts_openai.py:580-587`) — up to 3 billed attempts recorded as 1. Given the observed `httpx.ReadTimeout` failures, retries are real.
- **Every `get_tracker()` call is inside `try/except Exception: pass`** (7 sites) — an accounting bug is unobservable by design.
- **No budget cap, rate limit, daily ceiling or spend alert anywhere.** `admin.py:981-1001` offers one-click 10/15/up-to-50 items with no confirmation; the Scheduler UI offers up to 20 per batch every 15 minutes = a nominal $6.80/hour. The only thing preventing that today is that no background loop actually exists (`:1569-1578` sets a session flag and nothing consumes it).
- **The word cache was never wired up** — `get_or_generate_word` (`tts_openai.py:666-687`) is defined and never called, while its docstring advertises caching as the architecture. `WORDS_DIR` stays empty forever.
- **`cost_tracker.py:47` under-reports DALL·E by 33%**: `dall-e-3-1024x1792-hd` is listed at `$0.080`, which is the *standard*-quality price; both image scripts pass `quality="hd"` (~$0.120). Whisper is billed with `ceil(sec/60)` (`:92`), **over**-billing a 30 s video ~2×.
- *Unverified:* the `$220/1M chars` ElevenLabs figure (`cost_tracker.py:52`) is a plausible Creator-tier back-calculation, not a confirmed rate. ElevenLabs bills credits with model-dependent multipliers. Worth checking against an actual invoice before any cost-routing decision.

---

## 10. Answers to your four questions

### 10.1 Does `src/video.py` need to be split before anything else is built on it?

**The question is malformed — the file doesn't exist.** `src/video/` is already a 15-module package. Answering what you meant:

**No for the QA gate. Yes before the mascot layer.**

*No for step 2*, and this is important: the QA gate operates on the **rendered artifact** — the mp4, the wav, the pixels. It does not need to import a single line of `src/video/`. It is version-agnostic, v1/v2-agnostic, and can be built as a standalone module tomorrow without touching the renderer. Splitting first would be pure delay, and — per §6 — a QA gate that reads the generator's own JSON is exactly the thing that already failed.

*Yes before step 4.* Your hard rule — *"the mascot never covers text; query the text layout for occupied regions"* — requires an API that does not exist anywhere in the codebase. There is no layout model, no occupancy query, no bounding-box registry. Positions are computed inline in two god-functions (`create_frame_quiz`, 276 lines; `create_frame_true_false`, 342 lines) that measure text and immediately discard the measurement. Building a mascot placer on top of that means either (a) re-measuring everything a second time in the mascot code, which will drift, or (b) extracting a layout pass first. Option (b) is the only one that also fixes the overlap bug you already have.

*A caveat on how to split.* Do not start with the god-functions. Start with `fit_text_font` and a `LayoutBox` return type — that one helper is the shared dependency of every overlap bug in §2 #4, and fixing it correctly forces every call site to start handling a measured rectangle instead of a bare font object. The god-functions then fall out naturally. Also note that `add_sentence_boundaries` (`educational.py:39-92`) is imported by five modules including the TTS layer — v1 educational cannot be deleted until that function is extracted, whatever you do with v2.

### 10.2 Does the audit change the roadmap ordering?

**Yes — one insertion, and one prerequisite you don't have.**

**Insert a step 0 before the QA gate: unify the two pipelines.** This is not optional and it is not large. Right now `main.py` and `admin.py` produce different audio, different cost, different language handling, different renderer version, and only one of them records spend. A QA gate calibrated on one path will mis-measure the other, and you will spend weeks debugging the gate instead of the videos. Concretely: make `admin.py` call `main.py`'s pipeline functions in-process instead of shelling out to module `__main__` blocks, or make `main.py` the only pipeline and reduce `admin.py` to a UI over it. Either way, delete the four `if __name__ == "__main__"` type-dispatch blocks in the TTS modules — they are a third dispatch implementation.

Fold two things into that same step, because they are cheap and they block measurement:
- **Fix the render timeout diagnostics** (`admin.py:250-251`): stream the subprocess output instead of `capture_output=True`, so `TimeoutExpired` doesn't discard it. You currently cannot diagnose your most common failure. Also find out *why* a quiz render takes >600 s — my hypothesis, unverified, is the per-frame allocation cost in §11, plus the ~933 MB background pre-render cache at `video/__init__.py:136-137`.
- **Remove the MoviePy fallback** (`video/__init__.py:333-336`). A bare `except Exception` that re-runs a failed render under a different engine turns every data bug into a misattributed renderer bug. You believed MoviePy was gone; this is why it isn't.

**Then step 2 (QA gate) is correctly placed and its design is sound.** Two amendments:
- Your blended-segment check needs a companion: **assert `len(detected_speech_regions) == len(script_declared_segments)`** — which you already specified — but also **assert that measured segment boundaries match `segment_times` within a tolerance.** That single check catches problem #2 and #3 simultaneously, and it is the one check that would have caught "animations faster than the voice." Without it the QA gate can tell you the audio is fine and the video is still desynced.
- Do not build the QA gate on top of `quality_reviewer.py` or `video_analyzer.py`. Neither is salvageable — 2,678 lines, both auditing the generator's self-report, one with a metric that is anti-correlated with the bug it should detect. Read them for the list of things worth checking, then delete both.

**Step 3's cost-routing premise is partly moot and needs a prerequisite.** You proposed routing "option letters, countdown numbers, transitions" to `gpt-4o-mini-tts`:
- **Countdown numbers cost nothing today** — they are silence. There is no spend to route.
- **Option letters cannot be routed** because they are not separate segments. They are welded into one utterance with their words (`tts_elevenlabs.py:562-565`). Splitting them into per-role segments is a prerequisite for the cost routing *and* is the actual fix for "afabric" — the same refactor buys both. Do it as part of step 3, but know it is a refactor, not a config table.
- The real cost asymmetry is elsewhere and larger: **the dashboard path costs 2× for educational** (§9). Step 0 captures that saving for free.

**Steps 4 and 5 hold as ordered**, with the layout-extraction caveat in §10.1 attached to step 4.

**One thing missing from the roadmap entirely:** the data contract. §2 #6 — every render default is a plausible wrong answer, and `correct` defaulting to `'A'` will happily publish a green checkmark on the wrong option. At 2 videos/day unattended, that is the failure that costs you an audience, and no amount of audio/visual QA catches it because the video is technically perfect. A ~100-line pydantic schema in front of the renderer, failing **loud** instead of open, belongs in step 2 alongside the audio checks. It is the cheapest item on this entire list.

**Can the foundation hold the QA gate?** Yes — because the QA gate doesn't touch the foundation. It reads files. That is precisely why it should be built next, once step 0 makes "the output" a single well-defined thing.

### 10.3 Structural assessment, direct

The architecture is not bad in the sense of being badly designed. It is bad in the specific sense that **four correct designs are running simultaneously and the oldest one is in production.** Generation 3 (`tts_providers`, `tts_segmenter`, `compositor`) and generation 4 (`v2/timing_engine`, `character_director`) are genuinely good — better than most of what I'd expect in a solo project. They are also, respectively, half-adopted and unreachable.

The whack-a-mole pattern you describe has one mechanical explanation and it is not the one you guessed: **you fix things on `main.py` and watch the results from `admin.py`.**

### 10.4 What to hand to Claude Code

Per your division of labor, these are implementation tasks. In order:

1. **Step 0 — pipeline unification.** Make `admin.py` use `main.py`'s in-process pipeline; delete the `__main__` dispatch blocks in `tts_elevenlabs.py:1370-1501`, `tts_openai.py:1517+`, `tts_google.py:490+`; remove the MoviePy fallback at `video/__init__.py:333-336`; stream subprocess output. Ask for a before/after audio diff on the same educational script through both entry points as proof.
2. **Fix `fit_text_font`** (`utils.py:133-146`) and make it return a measured box; update the 9 call sites; make the 4 that omit `max_height` pass one. Ask for a rendered frame diff.
3. **Fix `script_generator.py:642-643`** (the quote mangler) and the `english_phrases` scraper at `:668-680`. Ask for the `_validation_warnings` count across regenerating all 11 sample scripts as proof.
4. **The QA gate itself** — a standalone `src/qa/` package with the checks from your roadmap plus the `segment_times` vs measured-boundary assertion, and a pydantic script schema. Give it `output/scripts/*.json` as its regression corpus and require that it fails on the known-bad `cool_20260416_084217.json`.

---

## 11. Other findings worth knowing

Not in the top 10, but each is real and verified.

**`offset_x` is shadowed inside the karaoke word loop.** `src/video/educational.py:522` rebinds the **function parameter** `offset_x` (declared `:445`, used at `:472` to compute each line's `start_x`) to a ±2 px emphasis jitter. On any group that wraps to 2+ lines during a fade-out, **line 2 does not slide with line 1** — it snaps to the un-offset centre. Two variables, one name, in a 100-line function.

**English classification runs twice with different dictionaries and the second overwrites the first.** `subtitle_processor.py:240-253` sets `is_english`; `video/__init__.py:208-228` rebuilds it from a different stoplist and assigns unconditionally at `:228`. For the bilingual path this destroys ground truth (§2 #10).

**`random.seed(42)` at module import.** `src/video/backgrounds.py:102` seeds the **global** RNG at import time. `get_default_background` (`:62-66`) works around it with `random.SystemRandom()` and a comment explaining why — so the side effect was noticed and patched around rather than removed. Any module imported afterwards inherits a deterministic stream.

**Per-frame `config.yaml` disk read.** `finalize_frame` (`utils.py:553-556`) calls `get_character_renderer()` every frame. With `character.enabled: false`, `_renderer` stays `None` forever, so `character.py:751-759` does `os.path.exists` + `open` + `yaml.safe_load` **30 times per second of output**. The negative result is never memoized. This is a plausible contributor to the 600 s render timeouts.

**Per-frame full-canvas allocations.** `create_base_frame` allocates an 8.3 MB RGBA buffer per frame; `draw_rounded_card` allocates **two more** per call; every glass button, pill badge, glow and accent bar allocates another. A single quiz frame with 4 option cards + question card + explanation card ≈ **15–25 full-canvas allocations and composites**. That, not MoviePy, is the dominant render cost. v2 does this correctly with a layer cache keyed on `(w,h,radius,key)` (`v2/educational.py:195-214`).

**933 MB background cache.** `video/__init__.py:136-137` pre-renders `5 s × 30 fps = 150` frames of 1080×1920×3 uint8 and holds them resident.

**`karaoke.py` caches on `id(words)`** (`:82-86`). CPython recycles ids; a stale layout can be served silently. Currently harmless only because each video renders in its own subprocess — and because karaoke is dead code.

**The v2 hook shows text nobody says.** `HOOK_END = 3.0` (`v2/educational.py:34`) suppresses `_draw_body` for `t < 3.0` (`:375-378`) and shows `data["hook"]` instead. In both educational samples the `hook` field **does not appear in `full_script` at all**. So for the first 3 seconds of every v2 educational video the screen displays text that is not being narrated — by design. Symmetrically `CTA_LEN = 2.5` overwrites the last 2.5 s. The one component built specifically to guarantee text/audio alignment has its first 3 seconds of output discarded by the renderer that consumes it.

**Three parallel secret-management implementations.** `src/config/secrets.py` (181 lines, with per-key format regexes and a name allowlist at `:153-154`) is **never imported**. `admin.py:446-499` re-implements `mask_key`, `get_api_status` and `save_env_key` inline **without validation** — so the dashboard will happily write a malformed key. `validate_all_keys` has no callers anywhere. **The better implementation is the orphaned one.** This is the codebase's recurring pattern in miniature.

---

## 12. Explicit gaps

Things I could not verify, stated so you don't over-trust the rest:

- **`assets/` was not in the copy I staged.** I could not inspect `piensa_bien.mp3`, the countdown assets, or the character sprites/clips. The `-c:a copy` format-mismatch analysis in §5 rests on the code's explicit `channels="stereo"`/44100 silence parameters versus uncontrolled API output, not on measured files. Anything about `CharacterDirector`'s clip behaviour is code-reading only.
- **`content/topics/` was not staged.** `script_generator.load_topics` (`:38-45`) reads `content/topics/<category>.json`; I could not verify topic-loading behaviour.
- **No `output/audio/*.json` exists in the tree**, so I could not compare a real `segment_times` against a real audio duration and **quantify** the drift in §2 #3. The *direction* is fixed by construction; the magnitude is unmeasured.
- **Whether `eleven_v3` actually elides `"A,"` before a word** is a model-behaviour claim inferred from the constructed input text plus your report. I verified the exact string sent to the API; I did not verify the acoustic output.
- **The `$220/1M` ElevenLabs rate** (`cost_tracker.py:52`) is unverified against your actual plan.
- **Whether the 600 s render timeouts are genuinely slow rendering or a hang** — no renderer logs survive, because `capture_output=True` discards them on `TimeoutExpired`. §11 lists three plausible contributors; none is confirmed.
- **File mtimes are unusable** in the staged copy — all 62 files fall within a 55-second window that reflects the copy, not authorship. There is no `.git` in what I read. Every claim about "what changed recently" comes from timestamps embedded in generated output filenames, not from the filesystem.
- **`src/admin.py`'s Upload page (`:1124-1470`) was read only in part.** Whether `metadata_generator.regenerate_for_platform` (a paid GPT call) is reachable from it is unconfirmed.

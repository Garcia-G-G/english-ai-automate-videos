# Harvested from the deleted analyzers

`src/video_analyzer.py` (1838 lines) and `src/quality_reviewer.py` (840 lines)
were deleted on 2026-07-30, after `src/qa_gate.py` replaced the part of them
worth keeping. Both were orphaned — a repo-wide grep found zero callers — and
both audited the generator's own self-report rather than the rendered artifact.

They are recoverable from git history. This file exists so nobody has to.

---

## Why they never worked

Not "they had bugs". Their **evaluation model** was wrong in four ways, and
each one is a trap the QA gate had to avoid by construction.

**1. They audited metadata, not artifacts.** `analyze_language_correctness`
(`video_analyzer.py:960`) inspects a boolean flag in JSON — metadata about
metadata. A generator that miscomputes a value writes that same wrong value
into its own report, so the analyzer agrees with the bug.

**2. They read arrays the TTS writes as empty.** Every word-level check reads
`words[]`, which the TTS hardcodes to `[]` for quiz, fill_blank, true_false and
vocabulary. So `analyze_audio_timing` short-circuits on `'No words found'`,
forcing `timing_score = 0` and unconditionally appending "Timing issues" and
"Pacing issues" to `critical_failures`. **The analyzer returned FAIL for 100% of
those videos regardless of quality.** A detector that fires on every input
carries zero information — which is the mechanical reason nobody kept it wired
in.

**3. Silent self-exclusion.** `video_analyzer.py:759-767` and
`quality_reviewer.py:426-432` drop a check from the average when it cannot find
its subject, rather than penalising it. Absence of evidence scored as evidence
of absence. This is the single most important thing not to repeat, and it is
why `qa_gate` reports `covered_by` and flags `UNCOVERED_no_timing_declaration`
explicitly — so "nothing was looked at" can never render as "passed".

**4. Exception swallowing.** `quality_reviewer.py:107-108` (`except: return []`),
`:317-324` (bare `except: pass`, so volume checks silently skipped),
`video_analyzer.py:922-928` (returns `score: 0` on any exception —
indistinguishable from a real failure).

### The anti-correlated metric

`analyze_layout_balance` (`video_analyzer.py:258-284`) computes the intensity-
weighted centre of visual mass and reports `is_centered`, which
`calculate_quality_score:1383-1384` rewards with **+15**.

This is **inverted with respect to the bug it should detect.** Two text blocks
that overlap produce a *more* centred mass than the same two blocks correctly
separated. So the metric awards its highest score to the exact failure —
overlapping text — that a layout check exists to catch. Do not reimplement it,
and do not trust centre-of-mass as a layout proxy at all. The layout work needs
a bounding-box sidecar from the renderer, not a pixel statistic.

---

## Ideas worth keeping

Genuinely useful, and NOT yet implemented in `qa_gate`. Recorded as candidates,
each with the condition that would make it honest.

| idea | from | what it needs to be real |
|---|---|---|
| **Glitch / sudden-volume-change detection** | `detect_animation_glitches:1022`; also advertised in `video_analyzer.py:7` and **never implemented** | A 200 ms artefact does not move a whole-file mean. Needs a short-window RMS envelope (e.g. `astats` with `metadata=1:reset=N`) and a delta threshold, not `volumedetect`. |
| **Countdown word interpolation** ("3… atención 2…") | `analyze_countdown_timing:405` | It only measured gaps, never interpolated words. The countdown is silent so `words[]` is empty and it returned `found:False`. Needs ASR over the countdown span — deferred. The current defensive regex at `tts_openai.py:204` is applied at the *generator* and never verified at the *output*. |
| **Animation smoothness / frame-delta** | `analyze_animation_smoothness:320` | Legitimate idea, wrong layer for an audio gate. Belongs with the layout work, driven off rendered frames plus a layout sidecar. |
| **Option-timing evenness** | `analyze_option_timing:484` | Superseded and done properly by `qa_gate.drift_table` + `letter_to_word`, which measure the waveform instead of the declared array. |
| **Question→options transition** | `analyze_question_transition:562` | Already covered by the drift table's `transition` row. |
| **Text readability / contrast** | `analyze_text_readability:218` | Real check, needs the layout sidecar. Not OCR. |
| **Colour-palette consistency** | `analyze_color_palette:168` | Cosmetic; low value against the failures that actually shipped. |
| **Per-type structural assertions** | `_check_quiz_structure:604`, `_check_true_false_structure:634`, `_check_educational_structure:652` | Already superseded by `src/script_schema.py`, which enforces these at three validation points with pydantic rather than ad-hoc ifs. |

## The one check they got right in principle

`quality_reviewer._check_audio_quality:257` ran `volumedetect` and flagged
`max_volume > -1.0 dB` as clipping. That is a real waveform measurement, and it
is carried forward as `qa_gate.CLIP_MAX_DB`. It is the only line of either file
that survives into the replacement.

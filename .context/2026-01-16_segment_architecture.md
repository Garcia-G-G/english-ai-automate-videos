# Context File: Segment-Based Architecture Implementation
**Date:** 2026-01-16
**Session Focus:** Fixing audio-visual sync issues permanently

---

## EXECUTIVE SUMMARY

Implemented **segment-based architecture** across all major video types (quiz, true_false, educational) to eliminate persistent audio-visual sync issues. The core problem was that text grouping logic was unreliable - words from one phrase would appear in the wrong animation frame.

**Root Cause:** Two parallel timing systems coexisted (Whisper estimation + exact segment timestamps), and the code inconsistently switched between them.

**Solution:** ONE source of truth - `segment_times` from TTS generation. No fallbacks, no estimation.

---

## CHANGES MADE

### 1. video.py - Major Refactor

**DELETED:**
- `parse_quiz_timestamps()` function (186 lines) - old Whisper-based estimation
- `group_words()` function (140 lines) - complex phrase grouping heuristics

**MODIFIED:**
- `create_frame_quiz()` - now uses segment_times directly, no fallbacks
- `create_frame_true_false()` - now uses segment_times directly, no fallbacks
- `create_frame_educational()` - completely rewritten to use segments array
- `generate_video()` - added strict validation for segment_times

**Key Lines:**
- Quiz validation: lines 1982-1996
- True/false validation: lines 2005-2020
- Educational validation: lines 1796-1808

### 2. tts_openai.py - New Educational Segment Generation

**ADDED:**
- `generate_educational_audio_segmented()` (lines 998-1130) - generates each phrase as separate audio with exact timestamps

**MODIFIED:**
- `generate_from_script()` - routes educational videos to new segment-based function

### 3. script_generator.py - New Educational Format

**MODIFIED:**
- `build_prompt_educational()` - GPT now outputs `segments` array instead of `full_script`

**New Format:**
```json
{
  "type": "educational",
  "segments": [
    {"id": "hook", "text": "¡Cuidado con 'embarrassed'!"},
    {"id": "intro", "text": "Muchos creen que significa 'embarazada'."},
    ...
  ],
  "english_phrases": [...],
  "translations": {...}
}
```

### 4. main.py - Fixed Data Merge

**MODIFIED:**
- `run_tts()` - protected `segments`, `segment_times`, `duration` from being overwritten during merge
- `run_pipeline()` - handles both segment-based and legacy formats
- Script preview - shows segments for educational videos

---

## ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│                    UNIFIED ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────┤
│  Quiz:        segment-based (12 segments)                   │
│  True/False:  segment-based (8 segments)                    │
│  Educational: segment-based (5-8 segments)                  │
│  Fill_blank:  legacy (can migrate later)                    │
│  Pronunciation: legacy (can migrate later)                  │
└─────────────────────────────────────────────────────────────┘

Flow:
GPT Script (segments) → TTS (exact timestamps) → Video (display segment)

Result: Text on screen ALWAYS matches what is being said.
```

---

## KEY DESIGN DECISIONS

1. **Fail-fast validation**: If segment_times is missing, raise ValueError immediately - don't render broken video

2. **No fallbacks**: Removed ALL fallback logic (999, duration * 0.5, etc.) - one path only

3. **Protected keys in merge**: `segments`, `segment_times`, `duration`, `words` are never overwritten

4. **GPT phrase segmentation**: Let GPT determine natural phrase breaks during script generation

---

## TEST RESULTS

| Video Type | Status | Duration |
|------------|--------|----------|
| Educational (embarrassed) | PASSED | 29.78s |
| Quiz (actually) | PASSED | 33.34s |
| True/False (library) | PASSED | 21.62s |

---

## FILES CHANGED

```
src/video.py          - Major refactor (~300 lines deleted, ~50 lines added)
src/tts_openai.py     - Added educational segment generation (~130 lines)
src/script_generator.py - Updated educational prompts (~80 lines modified)
main.py               - Fixed merge logic, preview (~30 lines modified)
```

---

## REMAINING WORK

- [ ] Migrate fill_blank to segment-based
- [ ] Migrate pronunciation to segment-based
- [ ] Clean up any remaining legacy code paths

---

## HOW TO USE

**Generate educational video:**
```bash
python3 main.py --category false_friends --topic embarrassed --type educational
```

**Generate quiz:**
```bash
python3 main.py --category false_friends --topic actually --type quiz
```

**Generate true/false:**
```bash
python3 main.py --category false_friends --topic library --type true_false
```

---

## DASHBOARD

Running on: http://localhost:8501
Command: `python3 -m streamlit run src/admin.py --server.port 8501`

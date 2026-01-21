# Context File: Dashboard Queue Fixes
**Date:** 2026-01-16
**Session Focus:** Fixed dashboard queue failures and improved UX

---

## EXECUTIVE SUMMARY

Fixed critical bug where dashboard queue was failing with TTS errors. All 7 queued videos were failing because the admin.py was passing empty text to TTS instead of using the `--script` flag. Also added JSON repair/retry logic for GPT responses and improved progress display.

**Test Results:** 4/5 videos successful (80% success rate). The 1 failure was due to GPT JSON error (now has retry logic).

---

## BUGS FIXED

### 1. TTS Command Bug (Critical)
**File:** `src/admin.py` lines 211-216

**Problem:** Dashboard was calling TTS with empty `full_script` text:
```python
# OLD (broken)
full_script = script_data.get('full_script', '')  # Empty for segment-based!
tts_cmd = ["python3", "tts_openai.py", full_script, "-o", audio_path]
```

**Solution:** Use `--script` flag to pass the script file:
```python
# NEW (working)
tts_cmd = ["python3", "tts_openai.py", "--script", script_path, "-o", audio_path]
```

### 2. TTS Data Merge Bug
**File:** `src/admin.py` lines 227-241

**Problem:** Merge logic was overwriting TTS-generated timestamps.

**Solution:** Added protected keys that are never overwritten:
```python
protected_keys = {'words', 'segments', 'segment_times', 'duration'}
```

### 3. GPT JSON Parsing Errors
**File:** `src/script_generator.py` lines 450-508

**Problem:** GPT sometimes returns malformed JSON, causing immediate failure.

**Solution:** Added:
- JSON repair function (removes trailing commas, fixes unquoted keys)
- Retry logic (up to 2 retries with GPT asking to fix JSON)
- Better error messages

---

## NEW FEATURES ADDED

### 1. Retry Functionality
- **Generate Page:** Retry button on failed jobs in history
- **Queue Page:** "Retry All Failed" button, individual retry buttons
- **Function:** `retry_failed_job()` in admin.py

### 2. Clear History Buttons
- "Clear Failed" - removes only failed jobs
- "Clear All History" - removes all history
- **Function:** `clear_job_history()` in admin.py

### 3. Improved Progress Display
- Elapsed time shown during generation
- Estimated time remaining during video rendering
- Step progress bar: ✅ Topic → ✅ Script → 🔊 Audio → 🎥 Video
- Animated progress during rendering (doesn't stay at 60%)

### 4. Better Queue Summary
- Shows success/error for each video as it completes
- Final summary with success rate
- Tip to retry failed videos
- Balloons animation on 100% success

### 5. Upload Page Improvements
- Video preview for each approved video
- Details card with name, type, date, size
- Remove button to reject approved videos

---

## FILES CHANGED

```
src/admin.py           - TTS fix, retry logic, progress display (~150 lines)
src/script_generator.py - JSON repair/retry logic (~60 lines)
```

---

## TEST RESULTS

Queue test with 5 educational videos:

| Video | Status | Notes |
|-------|--------|-------|
| fabric | ✅ Completed | 7.1 MB |
| realize | ❌ Failed | GPT JSON error (now has retry) |
| find out | ✅ Completed | 7.4 MB |
| take off | ✅ Completed | 7.1 MB |
| work out | ✅ Completed | 8.3 MB |

**Success Rate:** 80% (4/5)

---

## DASHBOARD PAGES STATUS

| Page | Status | Features |
|------|--------|----------|
| Dashboard | ✅ Working | Stats, quick actions, history |
| Generate | ✅ Working | Single video, progress, retry |
| Queue | ✅ Working | Batch processing, history, retry all |
| Review | ✅ Working | Preview, approve/reject, bulk actions |
| Upload | ✅ Working | Preview, remove, details |
| Library | ✅ Working | Filter, search, preview |
| Scheduler | ⏸️ Placeholder | Future feature |

---

## ARCHITECTURE SUMMARY

```
Dashboard Queue Flow:
1. User adds videos to queue
2. Click "Start Processing"
3. For each video:
   a. Create job (tracked in generation_jobs.json)
   b. Step 1: Select topic (5-10%)
   c. Step 2: Generate script with GPT (15-30%)
   d. Step 3: Generate audio with TTS (35-55%)
   e. Step 4: Render video with MoviePy (60-100%)
   f. Move job to history
4. Show final summary

Error Handling:
- GPT JSON errors → Retry up to 2x with repair
- TTS errors → Show error message, continue queue
- Video errors → Show error message, continue queue
- All errors logged in job history with full message
```

---

## HOW TO USE

**Start Dashboard:**
```bash
python3 -m streamlit run src/admin.py --server.port 8501
```

**Generate Single Video:**
1. Go to "Generate" page
2. Select video type, topic selection method
3. Click "Generate Video"

**Process Queue:**
1. Go to "Queue" page
2. Add videos (Quick Batch or Custom Add)
3. Click "Start Processing"
4. Watch progress, retry any failures

**Review Videos:**
1. Go to "Review" page
2. Preview each video
3. Approve or Reject

---

## REMAINING WORK

- [ ] Add video quality preview before approval
- [ ] Implement actual upload to TikTok/YouTube/Instagram
- [ ] Add scheduler for automatic batch generation
- [ ] Migrate fill_blank and pronunciation to segment-based

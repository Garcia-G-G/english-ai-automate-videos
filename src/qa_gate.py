#!/usr/bin/env python3
"""QA gate — measures RENDERED AUDIO, never the generator's self-report.

    python3 src/qa_gate.py                      # whole corpus -> output/qa/
    python3 src/qa_gate.py output/audio/quiz/cool_20260416_084217.json

REPORT MODE ONLY. Writes output/qa/<name>.json, prints a summary, moves no
files, never changes the exit code. Blocking is switched on in Step 3 by
flipping BLOCKING below.

Why this exists at all: the repo carried two analyzers (quality_reviewer.py,
video_analyzer.py) that audited the JSON the generator produced about itself.
A generator that miscomputes a timestamp writes that same wrong timestamp into
its own report, so those tools agreed with the bug and caught nothing. Every
number here comes out of ffmpeg reading the waveform.

CALIBRATION — measured, not guessed. See docs/qa-gate-calibration.md.

  Noise floor, from regions ffmpeg actually finds quiet, edges inset 60 ms:

    eleven_v3          n=288   p10 -91.0   median -65.2   p90 -54.7 dB
    eleven_turbo_v2_5  n=169   p10 -71.2   median -62.4   p90 -55.3 dB

  The two differ in SHAPE, not at the decision boundary. v3's p10 is exactly
  -91.0 dB — 16-bit digital silence — because the quiz path splices anullsrc
  between segments (tts_elevenlabs.py:622-633). turbo has no synthesized
  silence at all, so its quiet is entirely LAME room tone and its floor is
  unimodal. At the p90 end, where the threshold decision is actually made,
  they agree within 0.6 dB. One threshold therefore serves both, and that is
  a measured conclusion rather than an assumption.

  SILENCE_THRESHOLD_DB = -45: about 5 dB above the loudest silence observed in
  either model, and about 27 dB below speech (whole-file mean runs -15 to
  -18 dB). A boundary-stability sweep is flat from -30 to -60 dB and collapses
  at -70 (5 speech regions instead of ~20, p90 drift 3.8 s), because at -70
  only the spliced digital silence is visible and every natural pause is
  swallowed.

  SILENCE_MIN_DUR = 0.10, deliberately shorter than any threshold applied to
  it. silencedetect with d=0.25 cannot tell "exactly 250 ms" from "not
  detected"; durations are compared in Python instead.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "output" / "audio"
QA_DIR = ROOT / "output" / "qa"

#: Model routing, from pipeline.py:157. Recorded per artifact because the TTS
#: JSONs do NOT store which TTS model produced them — `_meta.model` is the
#: SCRIPT generator (gpt-4o-mini). Only 3 .ttsplan.json files carry model_id.
#:
#: These now live in timing_contract, because studio/media_validation.py had
#: re-implemented the same rule stricter and typeless and blocked production
#: for every video type. Re-exported here so every existing importer of
#: qa_gate.TURBO_TYPES keeps working.
from timing_contract import (  # noqa: E402  (re-export, see above)
    REQUIRES_SEGMENT_TIMES,
    REQUIRES_WORD_TIMELINE,
    TURBO_TYPES,
    V3_TYPES,
)

#: When True, `verdict()` returns REJECT for a failing artifact and the
#: pipeline writes it to output/rejected/ with its report. The gate NEVER
#: exits non-zero and NEVER aborts a batch — one bad video must not take the
#: run down with it.
BLOCKING = True

#: Per-type timing requirement. NOT "segment_times required" globally — that
#: would reject every educational video, which legitimately carries a word
#: timeline instead and is checked by check 2 at sentence granularity.
#:
#:   quiz / true_false / fill_blank / vocabulary -> segment_times
#:   educational / pronunciation                 -> word timeline
#:   neither                                     -> REJECT
#:
#: Defined in timing_contract and imported above. studio.media_validation
#: enforces the SAME objects at the production boundary.

#: Flags that REJECT when BLOCKING. Everything else is reported and shipped.
#:
#: Deliberately NOT here: any sentence-drift measure for educational. Fresh
#: output shows a systematic tail (max drift 1.148 s and 3.205 s on two of
#: three artifacts), but that is mechanism B — char-proportional word
#: estimation never aligned to the waveform — which needs ASR and is
#: explicitly deferred. Blocking on a defect we have decided not to fix yet
#: would reject educational wholesale for a known, accepted limitation.
BLOCKING_FLAGS = (
    "letter_to_word",                    # option letter elided into its word
    "speech_in_declared_silence",        # countdown drawn over speech
    "clipping",                          # samples pinned at full scale
    "dead_air",                          # unexplained silence
    "UNCOVERED_no_timing_declaration",   # nothing to check against
    "missing_required_timing",           # wrong timing kind for the type
    "no_word_timeline",                  # word karaoke with no timeline
)

# ── THRESHOLD PROVENANCE ────────────────────────────────────────────
# Every constant below is either DERIVED (with the measurement recorded
# beside it) or INHERITED-UNVALIDATED (with its source named). Nothing is
# allowed to be a bare number.
#
# The rule exists because CLIP_MAX_DB = -1.0 was carried over from
# quality_reviewer.py — a module deleted for shipping unvalidated numbers —
# and it turned out to be wrong in both directions: 24 false positives out of
# 39 flags, and it would have rejected 100% of freshly-fixed output. Numbers
# are the LAST thing to harvest from code you are deleting for its numbers.

#: DERIVED. See the calibration block above and docs/qa-gate-calibration.md.
SILENCE_THRESHOLD_DB = -45.0

#: DERIVED, from trap (c): must be SHORTER than any threshold applied to its
#: output, because silencedetect with d=X cannot distinguish "exactly X" from
#: "not detected". The shortest consumer is LETTER_WORD_MIN_SILENCE at 0.250,
#: so anything <= ~0.2 works; 0.10 leaves room for a shorter one later.
SILENCE_MIN_DUR = 0.10

#: INHERITED-UNVALIDATED — chosen by me during calibration to stop speech at a
#: region's edge leaking into a floor measurement, never swept. It only
#: affects the CALIBRATION harness, not any live verdict, which is why it has
#: survived unmeasured. If it is ever used in a check, derive it first.
EDGE_INSET = 0.06

#: Check 3. INHERITED, and deliberately so — this is a PRODUCT assertion, not
#: a measurement. It comes from tests/fixtures/known_bad/manifest.json
#: (afabric_option_letter_elision): "at least 250 ms of silence between each
#: option letter and its word". The gate reproduces that verdict from audio
#: rather than from an input string. A test pins the two together so the
#: manifest and the gate cannot drift apart.
LETTER_WORD_MIN_SILENCE = 0.250

#: Check 5. CLIPPING, as a COUNT of samples pinned at full scale — not a peak
#: level. DERIVED, 2026-07-30, over all 191 measurable corpus artifacts.
#:
#: The previous rule was `max_volume > -1.0 dB`, INHERITED UNVALIDATED from
#: quality_reviewer._check_audio_quality — a module deleted for shipping
#: unvalidated numbers. Carrying its number forward was the same mistake in
#: miniature. Measured, that rule flagged 39 of 191 artifacts: 24 had fewer
#: than 100 full-scale samples per million and were merely normalised, not
#: clipped, and only 2 were real. It also failed every fresh artifact
#: (-0.5 to -0.7 dB), which would have rejected 100% of freshly-fixed output.
#:
#: max_volume cannot separate "normalised to -0.5 dB" from "limited and
#: clipped" — both peak near full scale. What differs is how MANY samples sit
#: there. histogram_0db counts exactly that.
#:
#:   full-scale samples per million, 191 artifacts:
#:     p10..p75  0.0        three quarters have none at all
#:     p90       27.1
#:     p95      132.5
#:     p99      475.9
#:     then     17851.8    vocabulary/pull_vs_pool
#:              81629.6    educational/he_said_me_the_truth
#:
#: A 38x gap between p99 and the nearest real case. Any threshold in
#: 1000-5000 ppm flags the same two artifacts, so 1000 is chosen: ~2x above
#: p99, ~18x below the nearest true positive. Not a knife edge in either
#: direction.
CLIP_FULLSCALE_PPM = 1000.0

#: Check 5. DERIVED. Dead air, in seconds, for silence NOT explained by the
#: declared structure. Measured over 837 silence regions in 40 artifacts: p50 0.32,
#: p90 0.70, p95 1.13, then a hard jump to p99 7.09 which is the intentional
#: countdown block. 1.5 s sits above p95 and far below the countdown, so it
#: catches unexplained gaps without firing on designed ones.
DEAD_AIR_S = 1.5

#: Check 2 span tolerance. DERIVED. Measured: last_word_end / measured_duration has
#: median 0.98 over 66 artifacts, 0 of 66 exceeding 1.02, 2 of 66 under 0.90.
SPAN_MIN_COVERAGE = 0.90
SPAN_MAX_COVERAGE = 1.02

#: Declared segments that sit on spliced digital silence rather than speech.
#: TRAP (a): the quiz countdown is ~7 s of anullsrc carrying THREE declared
#: segments, so any "detected regions == declared segments" count can never
#: reconcile. These are checked against the declared SILENCE MAP — they must
#: contain no speech — and excluded from boundary drift.
SILENT_SEGMENT_PREFIXES = ("countdown_",)

#: A countdown is only SILENT when its segment text is the bracketed
#: placeholder the silent path writes: '[3]', '[2]', '[1]'.
#:
#: "countdown means silent" is NOT a safe assumption and asserting it cost the
#: baseline 78 false violations. Two eras and one LIVE provider speak the
#: countdown aloud and record the spoken word as the segment text:
#:
#:   tts_elevenlabs / tts_openai   add_segment(..., f'[{num}]', ...)   silent
#:   tts_google                    add_segment(..., f'{name}.', ...)   SPOKEN
#:
#: So the evidence has to come from the artifact, not from a guess about which
#: generator produced it. A segment whose text is 'Tres.' is supposed to
#: contain the word "tres", and flagging it for containing speech is the gate
#: being wrong, not the audio.
_SILENT_TEXT = re.compile(r"^\s*\[\s*\d+\s*\]\s*$")

_VOL_RE = re.compile(r"\[Parsed_volumedetect.*?\]\s*(\w+):\s*(-?[\d.]+|-inf)")
_SIL_RE = re.compile(r"silence_(start|end):\s*(-?[\d.]+)")
_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):([\d.]+)")


# ── ffmpeg primitives ────────────────────────────────────────────────

def _run(cmd: List[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stderr


def probe_duration(path: str) -> Optional[float]:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except (TypeError, ValueError):
        return None


def volumedetect(path: str, ss: float = None, t: float = None) -> Dict[str, float]:
    cmd = ["ffmpeg", "-hide_banner", "-nostats"]
    if ss is not None:
        cmd += ["-ss", f"{ss:.4f}"]
    if t is not None:
        cmd += ["-t", f"{t:.4f}"]
    cmd += ["-i", path, "-af", "volumedetect", "-f", "null", "-"]
    stderr = _run(cmd)
    out = {}
    for k, v in _VOL_RE.findall(stderr):
        out[k] = float("-inf") if v == "-inf" else float(v)
    # n_samples is printed TWICE — an empty first instance reporting 0, then
    # the real one. Take the max, never the first, and never `x or default`:
    # a legitimate 0.0 is falsy and would silently become the default. That
    # is the same shape as `not False` treating a real value as missing.
    counts = [int(x) for x in re.findall(r"n_samples:\s*(\d+)", stderr)]
    out["n_samples"] = float(max(counts)) if counts else 0.0
    out["histogram_0db"] = float(
        max((int(x) for x in re.findall(r"histogram_0db:\s*(\d+)", stderr)), default=0))
    return out


def silence_regions(path: str, threshold_db: float = SILENCE_THRESHOLD_DB,
                    min_dur: float = SILENCE_MIN_DUR) -> Tuple[List[Tuple[float, float]], Optional[float]]:
    """Silent (start, end) spans, plus the file duration ffmpeg reports."""
    stderr = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
                   f"silencedetect=noise={threshold_db}dB:d={min_dur}",
                   "-f", "null", "-"])
    duration = None
    m = _DUR_RE.search(stderr)
    if m:
        duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    spans, cur = [], None
    for kind, val in _SIL_RE.findall(stderr):
        if kind == "start":
            cur = float(val)
        elif cur is not None:
            spans.append((cur, float(val)))
            cur = None
    if cur is not None and duration is not None:
        spans.append((cur, duration))
    return spans, duration


def speech_regions(path: str, **kw) -> Tuple[List[Tuple[float, float]], Optional[float]]:
    """Complement of the silence spans."""
    spans, duration = silence_regions(path, **kw)
    out, t = [], 0.0
    for s, e in spans:
        if s - t > 0.05:
            out.append((t, s))
        t = e
    if duration is not None and duration - t > 0.05:
        out.append((t, duration))
    return out, duration


# ── check 1: the drift table ─────────────────────────────────────────

def _nearest_edge(edges: List[float], x: float) -> Optional[float]:
    return min(edges, key=lambda e: abs(e - x)) if edges else None


def _silent_segment_ids(data: Dict) -> set:
    """Segment ids the artifact itself declares as silence.

    Read from the `segments` array's text, never inferred from the id alone —
    see _SILENT_TEXT. An artifact with no `segments` array falls back to the
    id prefix, which is the old behaviour and the best available guess.
    """
    segs = data.get("segments") or []
    by_id = {s.get("id"): s.get("text") for s in segs if isinstance(s, dict)}
    out = set()
    for name in (data.get("segment_times") or {}):
        if not name.startswith(SILENT_SEGMENT_PREFIXES):
            continue
        text = by_id.get(name)
        if text is None:
            out.add(name)                      # no evidence either way
        elif _SILENT_TEXT.match(str(text)):
            out.add(name)                      # '[3]' -> genuinely silent
        # else: 'Tres.' -> spoken on purpose, not a silence declaration
    return out


def drift_table(data: Dict, mp3: str) -> Dict:
    """Declared segment boundaries vs boundaries measured on the waveform.

    The centrepiece. For each declared entry in segment_times, emit declared,
    measured and delta for both edges. Segments declared over spliced silence
    are reported separately against the silence map rather than matched to a
    speech boundary they can never have.
    """
    st = data.get("segment_times") or {}
    if not st:
        return {"available": False,
                "reason": "no segment_times — this type declares a word timeline instead"}

    sp, duration = speech_regions(mp3)
    starts = [s for s, _ in sp]
    ends = [e for _, e in sp]
    silent_ids = _silent_segment_ids(data)

    rows, silent_rows = [], []
    for name, v in sorted(st.items(), key=lambda kv: (kv[1] or {}).get("start", 0)
                          if isinstance(kv[1], dict) else 0):
        if not isinstance(v, dict) or "start" not in v:
            continue
        d_start, d_end = float(v["start"]), float(v.get("end", v["start"]))

        if name in silent_ids:
            # TRAP (a): assert against the declared silence map. This segment
            # claims a span that should contain NO speech.
            overlap = sum(max(0.0, min(d_end, e) - max(d_start, s)) for s, e in sp)
            vol = volumedetect(mp3, ss=d_start, t=max(0.01, d_end - d_start))
            silent_rows.append({
                "segment": name,
                "declared_start": round(d_start, 3),
                "declared_end": round(d_end, 3),
                "speech_overlap_s": round(overlap, 3),
                "max_volume_db": vol.get("max_volume"),
                "verdict": "SPEECH_IN_DECLARED_SILENCE" if overlap > 0.05 else "ok",
            })
            continue

        m_start = _nearest_edge(starts, d_start)
        m_end = _nearest_edge(ends, d_end)
        rows.append({
            "segment": name,
            "declared_start": round(d_start, 3),
            "measured_start": round(m_start, 3) if m_start is not None else None,
            "delta_start": round(m_start - d_start, 3) if m_start is not None else None,
            "declared_end": round(d_end, 3),
            "measured_end": round(m_end, 3) if m_end is not None else None,
            "delta_end": round(m_end - d_end, 3) if m_end is not None else None,
        })

    deltas = [abs(r["delta_start"]) for r in rows if r["delta_start"] is not None]
    deltas += [abs(r["delta_end"]) for r in rows if r["delta_end"] is not None]
    deltas.sort()
    return {
        "available": True,
        "threshold_db": SILENCE_THRESHOLD_DB,
        "n_declared": len(rows) + len(silent_rows),
        "n_speech_regions": len(sp),
        "rows": rows,
        "declared_silence": silent_rows,
        "abs_drift_median": round(deltas[len(deltas) // 2], 3) if deltas else None,
        "abs_drift_p90": round(deltas[int(len(deltas) * 0.9) - 1], 3) if deltas else None,
        "abs_drift_max": round(deltas[-1], 3) if deltas else None,
    }


# ── check 2: word timeline, at SENTENCE granularity ──────────────────

def sentence_timeline(data: Dict, mp3: str) -> Dict:
    """For types that declare a word timeline instead of segment_times.

    DELIBERATELY NOT A WORD-LEVEL ASSERTION. Word-timeline gaps measure -7 to
    -30 dB — they land mid-speech — so individual word boundaries cannot be
    validated against silence. Doing it anyway would produce a check that can
    never fire, which is how the analyzers this replaces ended up useless.
    Validating word boundaries needs forced alignment, i.e. ASR, deferred.

    What IS honestly verifiable without ASR, and is what this does:
      1. SPAN     — last_word_end vs measured duration
      2. SENTENCE — words grouped by add_sentence_boundaries' segment_id, and
                    those spans validated against silence exactly as check 1
                    validates segments
      3. COUNT    — detected speech regions vs sentence count
    """
    words = data.get("words") or []
    if not words:
        return {"available": False, "reason": "no word timeline either"}

    sp, duration = speech_regions(mp3)
    starts = [s for s, _ in sp]
    ends = [e for _, e in sp]

    out: Dict = {
        "available": True,
        "granularity": "sentence",
        "covers": ["span: last_word_end vs measured duration",
                   "sentence spans vs measured silence boundaries",
                   "speech-region count vs sentence count"],
        "does_not_cover": [
            "individual word boundaries — word-timeline gaps measure -7 to "
            "-30 dB (mid-speech), so there is no non-ASR instrument at that "
            "granularity",
            "what was actually said — needs ASR, deferred",
        ],
    }

    # 1. SPAN
    last_end = max((w.get("end", 0.0) for w in words if isinstance(w, dict)), default=0.0)
    if duration:
        cov = last_end / duration
        out["span"] = {
            "last_word_end": round(last_end, 3),
            "measured_duration": round(duration, 3),
            "coverage": round(cov, 4),
            "verdict": ("ok" if SPAN_MIN_COVERAGE <= cov <= SPAN_MAX_COVERAGE
                        else ("TIMELINE_EXCEEDS_AUDIO" if cov > SPAN_MAX_COVERAGE
                              else "TIMELINE_UNDERRUNS_AUDIO")),
        }

    # 2. SENTENCE spans, via the renderer's own grouping
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from video.educational import add_sentence_boundaries
        grouped = add_sentence_boundaries([dict(w) for w in words],
                                          data.get("full_script") or "")
    except Exception as e:                      # noqa: BLE001 - report, never crash
        out["sentences"] = {"error": f"could not group: {e}"}
        return out

    buckets: Dict[int, List[Dict]] = {}
    for w in grouped:
        buckets.setdefault(w.get("segment_id", 0), []).append(w)

    rows = []
    for sid in sorted(buckets):
        ws = buckets[sid]
        s = min(w["start"] for w in ws if "start" in w)
        e = max(w["end"] for w in ws if "end" in w)
        m_s = _nearest_edge(starts, s)
        m_e = _nearest_edge(ends, e)
        rows.append({
            "sentence_id": sid,
            "n_words": len(ws),
            "declared_start": round(s, 3),
            "measured_start": round(m_s, 3) if m_s is not None else None,
            "delta_start": round(m_s - s, 3) if m_s is not None else None,
            "declared_end": round(e, 3),
            "measured_end": round(m_e, 3) if m_e is not None else None,
            "delta_end": round(m_e - e, 3) if m_e is not None else None,
        })

    d = sorted(abs(r[k]) for r in rows for k in ("delta_start", "delta_end")
               if r[k] is not None)
    out["sentences"] = {
        "n_sentences": len(rows),
        "rows": rows,
        "abs_drift_median": round(d[len(d) // 2], 3) if d else None,
        "abs_drift_p90": round(d[int(len(d) * 0.9) - 1], 3) if d else None,
        "abs_drift_max": round(d[-1], 3) if d else None,
    }

    # 3. COUNT
    out["region_count"] = {
        "speech_regions": len(sp),
        "sentences": len(rows),
        "delta": len(sp) - len(rows),
    }
    return out


# ── check 3: letter-to-word silence in quiz options ──────────────────

def letter_to_word(data: Dict, mp3: str) -> Dict:
    """>= 250 ms between an option letter and its word.

    Fails by construction today: tts_elevenlabs.py:562 builds
    f"Opción {letter}, {word}." and :565 joins all four options plus the
    transition into ONE utterance sent in a single TTS call, so letter and
    word are separated only by a comma inside one breath. That is the
    'afabric' defect — "Opción A, fábrica" heard as "Opción afábrica".

    Non-ASR method, from structure rather than from words. Each option should
    be spoken as TWO chunks — the letter, a pause, then the word — so N
    options should yield 2N speech chunks. Chunks are assigned to options by
    which declared option span contains their midpoint, and an option's
    letter-to-word gap is the first gap BETWEEN its own chunks. Gaps between
    chunks of different options are between-option pauses and are excluded by
    construction.

    An option spoken as a SINGLE chunk has no internal gap at all: its letter
    is fully elided into its word. That is reported as 0.0 s — the worst case,
    not a missing measurement.

        cool_20260416   7 chunks / 4 options -> gaps 0.171 0.171 0.216, D elided
        fabric_20260116 4 chunks / 4 options -> ALL FOUR fully elided

    An earlier version split the gap distribution at its own midpoint. It
    worked on cool, where the pauses are cleanly bimodal, and broke on fabric,
    where every option is one chunk and the smallest BETWEEN-option gap
    (1.314 s) was misread as a letter gap — reporting 3/4 failing instead of
    4/4. Assigning chunks to options first removes the guess.
    """
    st = data.get("segment_times") or {}
    opts = {k: v for k, v in st.items()
            if k.startswith("option_") and isinstance(v, dict) and "end" in v}
    if len(opts) < 2:
        return {"available": False,
                "reason": "fewer than 2 per-option segment_times (not a quiz, or older format)"}

    sp, _ = speech_regions(mp3)
    rows, between = [], []
    prev_last_end = None

    for name, v in sorted(opts.items(), key=lambda kv: float(kv[1]["start"])):
        s, e = float(v["start"]), float(v["end"])
        mine = [(a, b) for a, b in sp if s <= (a + b) / 2.0 <= e]
        mine.sort()
        if prev_last_end is not None and mine:
            between.append(round(mine[0][0] - prev_last_end, 3))
        if mine:
            prev_last_end = mine[-1][1]

        inner = [round(b_s - a_e, 3) for (_, a_e), (b_s, _) in zip(mine, mine[1:])]
        # The LARGEST internal gap, not the first.
        #
        # An option is usually two chunks — "Opción A," | pause | "fábrica." —
        # and then there is only one gap to choose. But the TTS sometimes puts
        # its own short pause INSIDE the letter clip, between "Opción" and the
        # letter, producing three chunks and two gaps. Taking the first then
        # measures that intra-letter pause (0.110 s) instead of the real
        # letter-to-word boundary (0.496 s) and reports a false failure.
        #
        # The largest is the right pick because the letter-to-word gap is
        # SPLICED — PAUSE_LETTER_TO_WORD plus both clips' edge silence — while
        # anything the model inserts on its own is incidental and shorter.
        #
        # LIMIT, stated rather than hidden: without ASR the gate cannot tell
        # which chunk is the letter and which is the word. If a word were ever
        # split by a pause longer than the spliced one, this would measure that
        # instead. No case of it exists in the corpus or in fresh output.
        gap = max(inner) if inner else 0.0
        rows.append({
            "option": name,
            "span": [round(s, 3), round(e, 3)],
            "n_chunks": len(mine),
            "gap_s": gap,
            "all_internal_gaps_s": inner,
            "verdict": ("ok" if gap >= LETTER_WORD_MIN_SILENCE
                        else "LETTER_ELIDED_INTO_WORD"),
            "note": None if inner else "single chunk — letter fully elided into word",
        })

    measured = [r["gap_s"] for r in rows]
    total_chunks = sum(r["n_chunks"] for r in rows)
    return {
        "available": True,
        "required_s": LETTER_WORD_MIN_SILENCE,
        "n_options": len(opts),
        "speech_chunks": total_chunks,
        "expected_chunks": 2 * len(opts),
        "between_option_gaps_s": between,
        "letter_to_word_gaps_s": measured,
        "rows": rows,
        "worst_s": min(measured) if measured else None,
        "best_s": max(measured) if measured else None,
        "n_failing": sum(1 for r in rows if r["verdict"] != "ok"),
        "n_fully_elided": sum(1 for r in rows if not r["all_internal_gaps_s"]),
        "verdict": "ok" if all(r["verdict"] == "ok" for r in rows) else "LETTER_ELIDED_INTO_WORD",
    }


# ── check 4: segment count ───────────────────────────────────────────

def segment_count(data: Dict, mp3: str) -> Dict:
    """Detected speech regions vs declared SPEECH segments.

    TRAP (a): declared segments sitting on spliced silence are excluded from
    the expected count — three countdown segments over one 7 s anullsrc block
    can never appear as three speech regions.
    """
    st = data.get("segment_times") or {}
    if not st:
        return {"available": False, "reason": "no segment_times"}
    silent_ids = _silent_segment_ids(data)
    speech_declared = [k for k, v in st.items()
                       if isinstance(v, dict) and "start" in v and k not in silent_ids]
    silent_declared = [k for k in st if k in silent_ids]
    sp, _ = speech_regions(mp3)
    return {
        "available": True,
        "declared_speech_segments": len(speech_declared),
        "declared_silent_segments": len(silent_declared),
        "detected_speech_regions": len(sp),
        "delta": len(sp) - len(speech_declared),
        "note": "detected regions normally EXCEED declared segments: one "
                "declared segment can contain several sentences, each with "
                "its own internal pauses",
    }


# ── check 5: clipping and dead air ───────────────────────────────────

def _declared_silence_envelope(data: Dict) -> List[Tuple[float, float]]:
    """Spans where silence is intended: declared-silent segments, plus the
    gaps between consecutive declared segments.

    READS BOTH SHAPES, and it has to. This looked only at `segment_times`,
    the dict the segmented generators write. The bilingual path — the one
    educational and pronunciation take — writes a `segments` LIST and no
    segment_times at all, so for those two types the envelope was always
    empty and EVERY gap over DEAD_AIR_S counted as unexplained.

    That went unnoticed while their narration had no deliberate pauses in
    it. Adding "repeat after me" to pronunciation put real 0.9 s gaps in
    the audio, and the gate rejected a correct artifact for dead air it had
    no way to know was intended. The gate was right to ask; the artifact
    had simply never declared anything.

    The rule itself is unchanged — gaps between consecutive declared
    segments are intended — and is now applied to whichever declaration the
    artifact actually carries.
    """
    st = data.get("segment_times") or {}
    silent_ids = _silent_segment_ids(data)
    spans = []
    for k, v in st.items():
        if isinstance(v, dict) and "start" in v and "end" in v and k in silent_ids:
            spans.append((float(v["start"]), float(v["end"])))

    bounds = [(float(v["start"]), float(v["end"])) for v in st.values()
              if isinstance(v, dict) and "start" in v and "end" in v]
    if not bounds:
        bounds = [(float(seg["start"]), float(seg["end"]))
                  for seg in (data.get("segments") or [])
                  if isinstance(seg, dict) and "start" in seg and "end" in seg]

    ordered = sorted(bounds)
    for (s0, e0), (s1, _e1) in zip(ordered, ordered[1:]):
        if s1 > e0:
            spans.append((e0, s1))
    return spans


def levels(data: Dict, mp3: str) -> Dict:
    vol = volumedetect(mp3)
    mx = vol.get("max_volume")
    n_samples = vol.get("n_samples") or 0.0
    at_full_scale = vol.get("histogram_0db") or 0.0
    ppm = (at_full_scale / n_samples * 1e6) if n_samples else 0.0
    sil, duration = silence_regions(mp3)
    env = _declared_silence_envelope(data)

    dead = []
    for s, e in sil:
        w = e - s
        if w < DEAD_AIR_S:
            continue
        covered = sum(max(0.0, min(e, be) - max(s, bs)) for bs, be in env)
        if covered < 0.5 * w:          # more than half of it is unexplained
            dead.append({"start": round(s, 3), "duration": round(w, 3),
                         "explained_s": round(covered, 3)})

    return {
        "available": True,
        "max_volume_db": mx,
        "mean_volume_db": vol.get("mean_volume"),
        "clipping": {
            "threshold_ppm": CLIP_FULLSCALE_PPM,
            "full_scale_samples": int(at_full_scale),
            "n_samples": int(n_samples),
            "full_scale_ppm": round(ppm, 1),
            "verdict": "CLIPPED" if ppm >= CLIP_FULLSCALE_PPM else "ok",
        },
        "dead_air": {
            "threshold_s": DEAD_AIR_S,
            "regions": dead,
            "total_s": round(sum(r["duration"] for r in dead), 3),
            "verdict": "DEAD_AIR" if dead else "ok",
        },
    }


# ── per-artifact report ──────────────────────────────────────────────

def model_for(video_type: Optional[str]) -> str:
    if video_type in TURBO_TYPES:
        return "eleven_turbo_v2_5"
    if video_type in V3_TYPES:
        return "eleven_v3"
    return "unknown"


def analyze(json_path: Path) -> Optional[Dict]:
    mp3 = str(json_path)[:-5] + ".mp3"
    if not os.path.exists(mp3):
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if not isinstance(data, dict):
        return None

    vtype = data.get("type")
    actual = probe_duration(mp3)
    declared = data.get("duration")

    report = {
        "artifact": str(json_path.relative_to(ROOT)),
        "audio": str(Path(mp3).relative_to(ROOT)),
        "video_type": vtype,
        "tts_model": model_for(vtype),
        "declared_duration": declared,
        "measured_duration": round(actual, 3) if actual else None,
        "duration_delta": (round(actual - declared, 3)
                           if actual and isinstance(declared, (int, float)) else None),
        "has_segment_times": bool(data.get("segment_times")),
        "n_words": len(data.get("words") or []),
        "checks": {},
    }
    report["checks"]["drift_table"] = drift_table(data, mp3)          # 1
    report["checks"]["sentence_timeline"] = sentence_timeline(data, mp3)  # 2
    report["checks"]["letter_to_word"] = letter_to_word(data, mp3)    # 3
    report["checks"]["segment_count"] = segment_count(data, mp3)      # 4
    report["checks"]["levels"] = levels(data, mp3)                    # 5

    # An artifact is COVERED if at least one timing check could run on it.
    # Reported explicitly so the coverage number cannot quietly become
    # "everything passed" when it means "nothing was looked at".
    report["covered_by"] = [
        n for n in ("drift_table", "sentence_timeline")
        if report["checks"][n].get("available")
    ]
    report["flags"] = _collect_flags(report)
    return report


def _collect_flags(report: Dict) -> List[str]:
    f = []
    c = report["checks"]
    for row in c["drift_table"].get("declared_silence", []):
        if row["verdict"] != "ok":
            f.append(f"speech_in_declared_silence:{row['segment']}")
    stl = c["sentence_timeline"]
    if stl.get("available") and stl.get("span", {}).get("verdict", "ok") != "ok":
        f.append(f"span:{stl['span']['verdict']}")
    if c["letter_to_word"].get("available") and c["letter_to_word"]["verdict"] != "ok":
        f.append(f"letter_to_word:{c['letter_to_word']['n_failing']}_options")
    if c["levels"]["clipping"]["verdict"] != "ok":
        f.append("clipping")
    if c["levels"]["dead_air"]["verdict"] != "ok":
        f.append(f"dead_air:{c['levels']['dead_air']['total_s']}s")
    if not report["covered_by"]:
        f.append("UNCOVERED_no_timing_declaration")
    # Per-type timing requirement. A quiz without segment_times has no measured
    # option boundaries and the renderer would fall back to the /4 estimator at
    # video/quiz.py:130 — inventing timing and presenting it as sound. An
    # educational without a word timeline has nothing to drive its karaoke.
    # Different types, different requirement; one global rule would be wrong
    # for both.
    vt = report["video_type"]
    if vt in REQUIRES_SEGMENT_TIMES and not report["has_segment_times"]:
        f.append("missing_required_timing")
    elif vt in REQUIRES_WORD_TIMELINE and report["n_words"] == 0:
        f.append("missing_required_timing")
    # educational and pronunciation render WORD-level karaoke, so an empty
    # word array is a defect even when segment_times is present and the drift
    # table is happy. This is the audio-visible half of the
    # fabric_educational_20260116_192025 known-bad case: segment_times exist,
    # words: [] does not, and nothing drives the karaoke.
    if report["video_type"] in TURBO_TYPES and report["n_words"] == 0:
        f.append("no_word_timeline")
    return f


def verdict(report: Dict) -> Dict:
    """PASS / REJECT for one artifact, plus the reasons.

    The pipeline calls this. It NEVER raises and never affects an exit code:
    a rejected video is moved aside and the batch continues. One bad artifact
    taking down a whole run is a worse failure than the artifact.

    With BLOCKING False every artifact passes and the flags are advisory,
    which is how this ran for all of Step 2.
    """
    blocking = [f for f in report.get("flags", [])
                if f.split(":")[0] in BLOCKING_FLAGS]
    return {
        "artifact": report.get("artifact"),
        "video_type": report.get("video_type"),
        "blocking_enabled": BLOCKING,
        "verdict": "REJECT" if (BLOCKING and blocking) else "PASS",
        "blocking_flags": blocking,
        "advisory_flags": [f for f in report.get("flags", []) if f not in blocking],
    }


def _summarise(reports: List[Dict]) -> None:
    from collections import Counter, defaultdict
    print(f"\n{'='*78}\nQA GATE BASELINE — report mode, nothing blocked\n{'='*78}")
    print(f"artifacts analyzed : {len(reports)}")

    by_type = Counter(r["video_type"] for r in reports)
    print(f"\n{'type':16}{'model':20}{'n':>5}{'w/ segtimes':>13}{'drift med':>11}{'drift p90':>11}")
    groups = defaultdict(list)
    for r in reports:
        groups[(r["video_type"], r["tts_model"])].append(r)
    for (t, m), rs in sorted(groups.items(), key=lambda x: str(x[0][0])):
        seg = [r for r in rs if r["checks"]["drift_table"].get("available")]
        meds = sorted(r["checks"]["drift_table"]["abs_drift_median"] for r in seg
                      if r["checks"]["drift_table"].get("abs_drift_median") is not None)
        p90s = sorted(r["checks"]["drift_table"]["abs_drift_p90"] for r in seg
                      if r["checks"]["drift_table"].get("abs_drift_p90") is not None)
        med = f"{meds[len(meds)//2]:.3f}" if meds else "-"
        p90 = f"{p90s[len(p90s)//2]:.3f}" if p90s else "-"
        print(f"  {str(t):14}{m:20}{len(rs):>5}{len(seg):>13}{med:>11}{p90:>11}")

    # ── coverage, stated so it cannot be mistaken for "passed" ──
    by_cov = Counter()
    for r in reports:
        by_cov[tuple(r["covered_by"]) or ("NONE",)] += 1
    print(f"\n{'COVERAGE':16}{'n':>6}")
    for k, n in by_cov.most_common():
        print(f"  {'+'.join(k):14}{n:>6}")
    uncovered = [r for r in reports if not r["covered_by"]]
    if uncovered:
        print(f"\n  {len(uncovered)} artifacts have NO timing declaration at all "
              f"(no segment_times, no words) — checked only for level/dead-air:")
        for t, n in Counter(r["video_type"] for r in uncovered).most_common():
            print(f"     {str(t):16}{n:>4}")

    # ── check 2 ──
    st2 = [r for r in reports if r["checks"]["sentence_timeline"].get("available")]
    spans = [r["checks"]["sentence_timeline"].get("span") for r in st2]
    spans = [s for s in spans if s]
    bad_span = [s for s in spans if s["verdict"] != "ok"]
    sdr = sorted(r["checks"]["sentence_timeline"]["sentences"]["abs_drift_median"]
                 for r in st2
                 if r["checks"]["sentence_timeline"].get("sentences", {}).get("abs_drift_median") is not None)
    print(f"\nCHECK 2 sentence timeline : {len(st2)} artifacts")
    print(f"   span ok {len(spans)-len(bad_span)}/{len(spans)}   "
          f"sentence drift median-of-medians "
          f"{sdr[len(sdr)//2]:.3f}s" if sdr else "")

    # ── check 3 ──
    l2w = [r for r in reports if r["checks"]["letter_to_word"].get("available")]
    fails = [r for r in l2w if r["checks"]["letter_to_word"]["verdict"] != "ok"]
    worst = sorted(r["checks"]["letter_to_word"]["worst_s"] for r in l2w
                   if r["checks"]["letter_to_word"]["worst_s"] is not None)
    print(f"\nCHECK 3 letter-to-word    : {len(l2w)} artifacts with per-option spans")
    if worst:
        print(f"   FAILING (<{LETTER_WORD_MIN_SILENCE}s): {len(fails)}/{len(l2w)}"
              f"   worst gap: min={worst[0]:.3f}s median={worst[len(worst)//2]:.3f}s max={worst[-1]:.3f}s")

    # ── check 4 / 5 ──
    sc = [r["checks"]["segment_count"] for r in reports if r["checks"]["segment_count"].get("available")]
    if sc:
        dl = sorted(x["delta"] for x in sc)
        print(f"\nCHECK 4 segment count     : {len(sc)} artifacts   "
              f"detected-minus-declared median={dl[len(dl)//2]}  range {dl[0]}..{dl[-1]}")
    clip = [r for r in reports if r["checks"]["levels"]["clipping"]["verdict"] != "ok"]
    dead = [r for r in reports if r["checks"]["levels"]["dead_air"]["verdict"] != "ok"]
    print(f"\nCHECK 5 levels            : clipping {len(clip)}/{len(reports)}   "
          f"dead-air {len(dead)}/{len(reports)} (>{DEAD_AIR_S}s unexplained)")

    speech_in_silence = [1 for r in reports
                         for row in r["checks"]["drift_table"].get("declared_silence", [])
                         if row["verdict"] != "ok"]
    print(f"\ndeclared-silence violations (speech where silence was declared): "
          f"{len(speech_in_silence)}")
    print(f"\nartifacts with at least one flag: "
          f"{sum(1 for r in reports if r['flags'])}/{len(reports)}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="QA gate over rendered audio artifacts")
    ap.add_argument("targets", nargs="*", help="artifact JSONs (default: whole corpus)")
    ap.add_argument("--out", default=str(QA_DIR))
    args = ap.parse_args(argv)

    if args.targets:
        paths = [Path(t).resolve() for t in args.targets]
    else:
        paths = sorted(p for p in AUDIO_DIR.rglob("*.json")
                       if not p.name.endswith(".ttsplan.json"))

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    reports = []
    for i, p in enumerate(paths, 1):
        r = analyze(p)
        if r is None:
            continue
        reports.append(r)
        name = str(p.relative_to(AUDIO_DIR)).replace("/", "__")[:-5]
        (outdir / f"{name}.json").write_text(
            json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
        if i % 25 == 0:
            print(f"  ... {i}/{len(paths)}", file=sys.stderr)

    (outdir / "_baseline_summary.json").write_text(
        json.dumps({"n": len(reports), "threshold_db": SILENCE_THRESHOLD_DB,
                    "blocking": BLOCKING, "reports": reports},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    _summarise(reports)
    return 0            # never non-zero in report mode


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())

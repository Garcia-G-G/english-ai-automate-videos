#!/usr/bin/env python3
"""Segment-based bilingual narration with ElevenLabs.

Architecture (replaces the old single-call educational TTS):

    script JSON ──► tts_segmenter ──► [ {text, lang} ... ]
                                        │  one API call per segment with an
                                        ▼  explicit language_code (es / en)
                              per-segment mp3 + char timestamps
                                        │  ffmpeg concat with natural gaps
                                        ▼
                    final mp3 + GLOBAL word timestamps (offset-summed)

Why per-segment ``language_code``: ElevenLabs multilingual models decide
the accent from the dominant language of the WHOLE text.  A Spanish script
with a few English words gets read with an anglo accent (or vice versa).
``eleven_turbo_v2_5`` / ``eleven_flash_v2_5`` accept ``language_code`` to
FORCE the language per request — one voice, two accents, per segment.
(eleven_v3 does NOT accept language_code, so this path uses turbo v2.5 by
default; override via audio.segment_model / ELEVENLABS_SEGMENT_MODEL.)

Timestamps: the primary source is ElevenLabs' own character timings
(``convert_with_timestamps``), aggregated into words and shifted by each
segment's offset in the stitched file — exact by construction, and each
word inherits ``is_english`` from its segment's language (no more fragile
word-list heuristics).  If timestamps are unavailable the caller can still
run the legacy Whisper pass over the final audio: stitching does not break
that path either, because Whisper only ever sees the finished file.

Dry-run: set ``dry_run=True`` (or env ``TTS_DRY_RUN=1``) to log every call
that would be made (text, lang, voice, model) without importing the
ElevenLabs SDK or touching the network.
"""

import base64
import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from tts_segmenter import LANGUAGE_POLICIES, segment_script, describe_segments
import stitch

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent

# Chars-per-second used only for dry-run duration estimates.
_EST_CPS = {'es': 14.5, 'en': 11.0}


def _load_audio_config() -> Dict:
    """audio: section of config.yaml (best-effort, never raises)."""
    try:
        import yaml
        with open(_ROOT / "config.yaml", 'r', encoding='utf-8') as f:
            return (yaml.safe_load(f) or {}).get('audio', {}) or {}
    except Exception:
        return {}


def _norm_lang(code: str, default: str) -> str:
    """'en-US' -> 'en' (ElevenLabs language_code is ISO 639-1)."""
    code = (code or default or '').strip()
    return code.split('-')[0].lower() or default


def resolve_settings() -> Dict:
    """Voice / model / language settings honoring profile env overrides."""
    # Load .env at the ENTRY POINT, not at import. Without it a standalone
    # run silently falls back to the HARDCODED default voice below and
    # produces audio in the wrong voice — output that sounds fine and is
    # wrong, which is worse than a visible failure.
    from env_setup import ensure_env_loaded
    ensure_env_loaded()

    cfg = _load_audio_config()
    voice_id = (os.getenv("VIDEO_PROFILE_VOICE_ID")
                or os.getenv("ELEVENLABS_VOICE_ID"))
    model = (os.getenv("ELEVENLABS_SEGMENT_MODEL")
             or cfg.get("segment_model")
             or "eleven_turbo_v2_5")
    return {
        "voice_id": voice_id,
        "model_id": model,
        "narration_lang": _norm_lang(cfg.get("narration_lang", "es"), "es"),
        "english_lang": _norm_lang(cfg.get("english_accent", "en-US"), "en"),
        "stability": float(os.getenv("VIDEO_PROFILE_TTS_STABILITY",
                                     str(cfg.get("stability", 0.5)))),
        "similarity": float(cfg.get("similarity_boost", 0.8)),
        "style": float(os.getenv("VIDEO_PROFILE_TTS_STYLE",
                                 str(cfg.get("style", 0.05)))),
        "speed": float(os.getenv("VIDEO_PROFILE_TTS_SPEED",
                                 str(cfg.get("global_speed", 1.0)))),
        # English teaching words read slightly slower for clarity
        "english_speed_factor": float(cfg.get("english_speed_factor", 0.92)),
    }


def plan_calls(script_data: Dict, settings: Dict = None,
               language_policy=None) -> List[Dict]:
    """Build the ordered list of TTS calls (text, lang, voice, model...)."""
    settings = settings or resolve_settings()
    if language_policy is None:
        native = settings.get("native_language", settings["narration_lang"])
        language_policy = LANGUAGE_POLICIES.get(native)
    if language_policy is None:
        raise ValueError(f"unsupported native language policy: {native}")
    segments = segment_script(script_data, language_policy=language_policy)

    # REPETITION PAUSE, for the types that teach by repetition.
    #
    # The segmenter's pause_after is a STITCHING hint from trailing
    # punctuation and tops out at 0.18s for a full stop. That is right for
    # prose and useless for "repeat after me": 0.18s is not a pause a
    # learner can say a word into, so a repeat without this override is
    # three utterances run together rather than three takes.
    #
    # Applied only to short ENGLISH segments, and only for types whose
    # config declares takes > 1. educational declares 1, so its pacing —
    # which the owner judges good — is untouched by construction.
    from duration_spec import repetition_pause, takes as _takes_for
    repeat_takes = _takes_for(script_data.get("type"))
    repeat_gap = repetition_pause() if repeat_takes > 1 else None

    calls = []
    for i, seg in enumerate(segments):
        lang = (settings["english_lang"] if seg["lang"] == "en"
                else settings["narration_lang"])
        speed = settings["speed"]
        if seg["lang"] == "en" and len(seg["text"].split()) <= 6:
            speed = round(speed * settings["english_speed_factor"], 3)
        calls.append({
            "index": i,
            "text": seg["text"],
            "lang": lang,
            "is_english": seg["lang"] == "en",
            # NO WORD-COUNT FILTER. The first version reused the <=6 words
            # condition from english_speed_factor above, and a pronunciation
            # topic of "How Are You? (Not a Real Question)" — 7 words — fell
            # straight through it and got the 0.03s stitching gap instead of
            # a pause. In a type that teaches by repetition every English
            # utterance is something the learner repeats, whatever its
            # length, so length is not the right question to ask.
            # STEP 76 §2: the clips are trimmed to their speech, so the gap is the
            # punctuation's own (stitch.gap_after), as in the lessons.
            "pause_after": (
                repeat_gap
                if (repeat_gap is not None and seg["lang"] == "en")
                else stitch.gap_after(seg["text"])
            ),
            "voice_id": settings["voice_id"],
            "model_id": settings["model_id"],
            "speed": max(0.7, min(1.2, speed)),
        })
        # At a language switch only next_text (stitch.context): the previous text made
        # the model start mid-sound («m-make», «d-do»).
        previous, following = stitch.context(
            segments[i - 1]["lang"] if i > 0 else None, seg["lang"],
            segments[i - 1]["text"] if i > 0 else "",
            segments[i + 1]["text"] if i + 1 < len(segments) else "")
        calls[-1]["previous_text"] = previous or None
        calls[-1]["next_text"] = following or None
    return calls


# ── Real synthesis ────────────────────────────────────────────────────

def _synthesize_segment(call: Dict, out_path: str, settings: Dict, take: int = 0) -> Dict:
    """One ElevenLabs request. Returns {'duration', 'words': [...] or None}.

    Tries the with-timestamps endpoint first (exact char timings); falls
    back to the plain convert stream. A cached identical request (tts_cache,
    the take index included) is copied with its alignment instead.
    """
    from tts_elevenlabs import get_client, _elevenlabs_with_retry
    from tts_common import get_audio_duration
    from elevenlabs.types import VoiceSettings

    vs = VoiceSettings(
        stability=settings["stability"],
        similarity_boost=settings["similarity"],
        style=settings["style"],
        use_speaker_boost=True,
        speed=call["speed"],
    )
    if not call.get("voice_id"):
        raise RuntimeError("ELEVENLABS_VOICE_ID no está configurado. Ponlo en .env (el ID de la voz del canal); ya no hay voz por defecto en el código.")
    kwargs = dict(
        voice_id=call["voice_id"],
        text=call["text"],
        model_id=call["model_id"],
        language_code=call["lang"],
        voice_settings=vs,
        output_format="mp3_44100_128",
    )
    if call.get("previous_text"):
        kwargs["previous_text"] = call["previous_text"]
    if call.get("next_text"):
        kwargs["next_text"] = call["next_text"]

    import tts_cache
    from tts_common import get_audio_duration as _duration
    cache_key = tts_cache.key({**kwargs, "endpoint": "with_timestamps"}, take)
    cached = tts_cache.restore(cache_key, out_path)
    if cached is not None:
        a = cached.get("alignment") or {}
        words = (_chars_to_words(a["characters"], a["character_start_times_seconds"],
                                 a["character_end_times_seconds"]) if a.get("characters") else None)
        return {"duration": _duration(out_path), "words": words}
    client = get_client()

    # Cost tracking (best-effort)
    try:
        from cost_tracker import get_tracker
        get_tracker().log_elevenlabs_tts(
            characters=len(call["text"]), model=call["model_id"],
            label="tts_bilingual_segment")
    except Exception:
        pass

    words = None
    try:
        resp = client.text_to_speech.convert_with_timestamps(**kwargs)
        audio_b64 = getattr(resp, "audio_base_64", None) or (
            resp.get("audio_base64") if isinstance(resp, dict) else None)
        alignment = getattr(resp, "alignment", None) or (
            resp.get("alignment") if isinstance(resp, dict) else None)
        if not audio_b64:
            raise RuntimeError("no audio in with_timestamps response")
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(audio_b64))
        if alignment is not None:
            chars = (getattr(alignment, "characters", None)
                     or alignment.get("characters"))
            starts = (getattr(alignment, "character_start_times_seconds", None)
                      or alignment.get("character_start_times_seconds"))
            ends = (getattr(alignment, "character_end_times_seconds", None)
                    or alignment.get("character_end_times_seconds"))
            if chars and starts and ends:
                words = _chars_to_words(chars, starts, ends)
                tts_cache.store(cache_key, out_path, {**kwargs, "endpoint": "with_timestamps"},
                                {"characters": list(chars), "character_start_times_seconds": list(starts),
                                 "character_end_times_seconds": list(ends)})
            else:
                tts_cache.store(cache_key, out_path, {**kwargs, "endpoint": "with_timestamps"})
    except Exception as e:
        logger.info("with_timestamps unavailable (%s) — using plain convert", e)
        _elevenlabs_with_retry(client, out_path, take=take, **kwargs)

    duration = get_audio_duration(out_path)
    if duration <= 0:
        raise RuntimeError(f"Zero-length TTS segment: {call['text'][:60]}")
    return {"duration": duration, "words": words}


def _chars_to_words(chars: List[str], starts: List[float],
                    ends: List[float]) -> List[Dict]:
    """Aggregate ElevenLabs character timings into word timings."""
    words, cur, w_start, w_end = [], [], None, None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append({"word": "".join(cur),
                              "start": round(w_start, 3),
                              "end": round(w_end, 3)})
                cur = []
            continue
        if not cur:
            w_start = s
        cur.append(ch)
        w_end = e
    if cur:
        words.append({"word": "".join(cur), "start": round(w_start, 3),
                      "end": round(w_end, 3)})
    return words


def _estimate_words(text: str, duration: float) -> List[Dict]:
    """Uniform char-proportional word estimate inside one segment."""
    toks = text.split()
    total = sum(len(t) + 1 for t in toks) or 1
    t, out = 0.0, []
    for tok in toks:
        d = duration * (len(tok) + 1) / total
        out.append({"word": tok, "start": round(t, 3),
                    "end": round(t + d, 3)})
        t += d
    return out


def generate_bilingual_narration(
    script_data: Dict,
    output_path: str,
    voice_id: Optional[str] = None,
    dry_run: Optional[bool] = None,
    settings: Optional[Dict] = None,
    language_policy=None,
) -> Dict:
    """Generate the full narration mp3 + timestamp dict for a script.

    Returns {'duration', 'words', 'segments', 'tts_calls'} where every
    word has global start/end and an is_english flag derived from its
    segment's language.
    """
    if dry_run is None:
        dry_run = os.getenv("TTS_DRY_RUN", "").strip() in ("1", "true", "yes")

    settings = dict(settings or resolve_settings())
    if voice_id:
        settings["voice_id"] = voice_id
    calls = plan_calls(script_data, settings, language_policy=language_policy)
    if not calls:
        raise ValueError("Script produced no TTS segments (empty full_script?)")

    logger.info("Bilingual TTS: %d segments (%d EN) voice=%s model=%s",
                len(calls), sum(1 for c in calls if c["is_english"]),
                settings["voice_id"], settings["model_id"])

    if dry_run:
        return _dry_run(calls, script_data, output_path, settings)

    from tts_common import (measure_speech_end, merge_punctuation_tokens,
                            trim_clip_silence)
    import loudness

    temp_dir = tempfile.mkdtemp(prefix="el_bilingual_")
    clips: List[Dict] = []
    asr_segments = estimated_segments = clamped_segments = 0
    try:
        for call in calls:
            seg_path = os.path.join(temp_dir, f"seg_{call['index']:03d}.mp3")
            logger.info("  [%02d] %-2s %s", call["index"], call["lang"],
                        call["text"][:70])

            # ONSET GATE (stitch): re-ask a clip that starts mid-sound or doubled, up to
            # ONSET_RETRIES times, and keep the cleanest take — never just the last.
            takes = []
            for attempt in range(1 + stitch.ONSET_RETRIES):
                path = seg_path if not attempt else seg_path.replace(".mp3", f".t{attempt}.mp3")
                res = _synthesize_segment(call, path, settings, take=attempt)
                takes.append((path, res, stitch.onset_values(path)))
                if stitch.onset_clean(takes[-1][2], call["model_id"]):
                    break
            keep = stitch.cleanest_take([t[2] for t in takes], call["model_id"])
            seg_path, res, onset = takes[keep]
            call["takes"], call["onset"] = len(takes), {**onset, "clean": stitch.onset_clean(onset, call["model_id"])}
            if not call["onset"]["clean"]:
                logger.warning("  [%02d] no clean onset in %d takes; kept the cleanest %s",
                               call["index"], len(takes), onset)

            # REAL TIMINGS, NOT AN ESTIMATE. This is D5.
            #
            # Order of preference: what the TTS itself reported, then ASR,
            # then the estimate. None of the three ever fabricates: ASR
            # returns None when no backend is available and the estimate is
            # what we had before. Per CLIP, so each word's language is the
            # call's language by construction.
            seg_words = res["words"]
            if not seg_words:
                from asr_timings import fit_to_clip, transcribe_words
                measured = transcribe_words(
                    seg_path, language="en" if call["is_english"] else "es")
                if measured:
                    seg_words = fit_to_clip(measured, res["duration"])
                    asr_segments += 1
            if not seg_words:
                seg_words = _estimate_words(call["text"], res["duration"])
                estimated_segments += 1

            # Punctuation-only tokens ("," ".") are absorbed into their words, per clip.
            seg_words = merge_punctuation_tokens(seg_words, boundary_key=None)

            # TRIMMED TO ITS SPEECH (STEP 76 §2, the lessons' rule): a TTS clip carries
            # 0.3-1.3 s of silence the model chose, different on every run; the pause
            # between clips is set by stitch.gap_after instead. Words move with the cut.
            trim = trim_clip_silence(seg_path)
            cut = float(trim["start"]) if trim.get("trimmed") else 0.0
            call["trim_start"] = round(cut, 3)

            # CLAMP THE DECLARED END TO WHERE THE VOICE ACTUALLY STOPS: the alignment
            # runs to the end of the file, so a word would swallow the silence after it
            # and the QA gate would call the real silence dead air.
            speech_end = measure_speech_end(seg_path)
            words = []
            for w in seg_words:
                start, end = float(w["start"]) - cut, float(w["end"]) - cut
                if speech_end > 0:
                    start, end = min(start, speech_end), min(end, speech_end)
                start = max(0.0, start)
                if end > start:
                    words.append({**w, "start": start, "end": end})
            if speech_end > 0 and any(float(w["end"]) - cut > speech_end for w in seg_words):
                clamped_segments += 1
            clips.append({"call": call, "path": seg_path, "words": words or seg_words})

        # LEVEL MATCH (loudness.level_clips): every clip to the median level, ±6 dB, as
        # WAV — the Spanish line and the English word next to it at the same loudness.
        levelled = loudness.level_clips([c["path"] for c in clips], Path(temp_dir))

        # One PCM timeline: clip, gap, clip … every piece WAV, one encode at the end.
        audio_files: List[str] = []
        all_words: List[Dict] = []
        running = 0.0
        for n, (clip, lv) in enumerate(zip(clips, levelled)):
            call = clip["call"]
            call["gain_db"] = lv["gain_db"]
            length = loudness.decode(lv["path"]).size / loudness.RATE
            for w in clip["words"]:
                all_words.append({
                    "word": w["word"],
                    "start": round(min(w["start"], length) + running, 3),
                    "end": round(min(w["end"], length) + running, 3),
                    "is_english": call["is_english"],
                })
            audio_files.append(str(lv["path"]))
            call["clip_start"], call["clip_end"] = round(running, 3), round(running + length, 3)
            running += length
            gap = call["pause_after"]
            if n + 1 < len(clips) and gap > 0.01:
                sil = Path(temp_dir) / f"sil_{call['index']:03d}.wav"
                loudness._write_wav(np.zeros(int(round(gap * loudness.RATE))), sil)
                audio_files.append(str(sil))
                running += round(gap * loudness.RATE) / loudness.RATE

        # Stitch — concat demuxer with re-encode (uniform format/bitrate).
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        concat = os.path.join(temp_dir, "concat.txt")
        with open(concat, "w") as f:
            for p in audio_files:
                f.write(f"file '{p}'\n")
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat,
               "-acodec", "libmp3lame", "-q:a", "2", "-ar", "44100",
               "-ac", "1", output_path]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {r.stderr[:400]}")

        from tts_common import get_audio_duration
        duration = get_audio_duration(output_path)

        result = _build_result(
            script_data, all_words, duration, calls,
            timing_source={
                "asr_segments": asr_segments,
                "estimated_segments": estimated_segments,
                "clamped_segments": clamped_segments,
                "backend": (__import__("asr_timings").backend_name()
                            if asr_segments else "elevenlabs_alignment"),
            })
        logger.info("Bilingual narration done: %.2fs, %d words (%d EN)",
                    duration, len(result["words"]),
                    sum(1 for w in result["words"] if w["is_english"]))
        return result
    finally:
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except OSError:
            pass


def _build_result(script_data: Dict, words: List[Dict], duration: float,
                  calls: List[Dict], timing_source: Dict = None) -> Dict:
    """Attach sentence boundaries + build renderer-ready segments."""
    full_script = script_data.get("full_script", "")
    try:
        from video.educational import add_sentence_boundaries
        words = add_sentence_boundaries(words, full_script)
    except Exception as e:  # renderer package not importable (tests)
        logger.warning("add_sentence_boundaries unavailable: %s", e)
        for w in words:
            w.setdefault("segment_id", 0)
            w.setdefault("segment_end", False)

    segments, cur_id, bucket = [], None, []
    for w in words:
        sid = w.get("segment_id", 0)
        if sid != cur_id and bucket:
            segments.append({"start": bucket[0]["start"],
                             "end": bucket[-1]["end"],
                             "text": " ".join(x["word"] for x in bucket)})
            bucket = []
        cur_id = sid
        bucket.append(w)
    if bucket:
        segments.append({"start": bucket[0]["start"],
                         "end": bucket[-1]["end"],
                         "text": " ".join(x["word"] for x in bucket)})

    return {
        "duration": round(duration, 3),
        "words": words,
        "segments": segments,
        # Written FORWARD only — never backfilled onto the existing corpus.
        # Backfilling would write today's INFERENCE about which model ran into
        # a data file where it would later be read as a recorded measurement,
        # which is the exact failure this project has been unwinding: the
        # generator's self-report becoming the oracle. Named tts_model_id, not
        # model_id, because _meta.model in these same files holds the SCRIPT
        # model (gpt-4o-mini) and a bare `model` here would read as the TTS one.
        # Taken from the calls actually made, not from resolve_settings() —
        # `calls` records what was really sent, which is the point of recording
        # it at all. (The first version read a `settings` local that does not
        # exist in this scope; it raised NameError on every educational
        # generation and no test caught it, because nothing exercised this
        # module. tests/test_tts_bilingual_result.py now does.)
        # WHERE THE WORD TIMINGS CAME FROM. Recorded, not inferred: an
        # artifact whose karaoke is driven by these numbers should say
        # whether they were measured or estimated.
        #
        # PASSED IN, not read from an enclosing scope. The comment two
        # paragraphs down records that reading a caller's local from here
        # raised NameError on every educational generation for two commits;
        # this is the same function and the same trap.
        "timing_source": dict(timing_source or {}),
        "tts_model_id": (calls[0].get("model_id") if calls else None),
        # takes / onset / trim_start / gain_db: what the stitch rule did to each clip (STEP 76 §2).
        "tts_calls": [{k: c[k] for k in
                       ("index", "lang", "text", "speed", "pause_after",
                        "takes", "onset", "trim_start", "gain_db", "clip_start", "clip_end") if k in c}
                      for c in calls],
    }


def _dry_run(calls: List[Dict], script_data: Dict, output_path: str,
             settings: Dict) -> Dict:
    """Log the exact calls that would be made; estimate a timeline."""
    print("=" * 72)
    print("TTS DRY-RUN — bilingual segment plan (no API calls made)")
    print(f"voice={settings['voice_id']}  model={settings['model_id']}  "
          f"narration={settings['narration_lang']}  "
          f"english={settings['english_lang']}")
    print("=" * 72)

    words: List[Dict] = []
    running = 0.0
    for c in calls:
        dur = max(0.35, len(c["text"]) / _EST_CPS.get(c["lang"], 13.0))
        print(f"[{c['index']:02d}] lang={c['lang']:2}  speed={c['speed']:.2f}  "
              f"~{dur:5.2f}s  prev={'y' if c['previous_text'] else '-'} "
              f"next={'y' if c['next_text'] else '-'}  "
              f"text={c['text']!r}")
        for w in _estimate_words(c["text"], dur):
            words.append({"word": w["word"],
                          "start": round(w["start"] + running, 3),
                          "end": round(w["end"] + running, 3),
                          "is_english": c["is_english"]})
        running += dur + c["pause_after"]
    print("-" * 72)
    print(f"TOTAL estimated: {running:.2f}s in {len(calls)} calls "
          f"({sum(1 for c in calls if c['is_english'])} english segments)")
    print("=" * 72)

    result = _build_result(script_data, words, running, calls)
    result["dry_run"] = True
    if output_path:
        json_path = str(output_path).rsplit(".", 1)[0] + ".dryrun.json"
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info("Dry-run plan saved: %s", json_path)
        except OSError:
            pass
    return result


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Bilingual segment-based TTS")
    ap.add_argument("--script", "-s", required=True)
    ap.add_argument("--output", "-o", default="output/audio/bilingual_test.mp3")
    ap.add_argument("--voice", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.script, "r", encoding="utf-8") as f:
        data = json.load(f)
    res = generate_bilingual_narration(data, args.output, voice_id=args.voice,
                                       dry_run=args.dry_run or None)
    if not res.get("dry_run"):
        json_path = args.output.rsplit(".", 1)[0] + ".json"
        res_out = dict(res)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(res_out, f, ensure_ascii=False, indent=2)
        print(f"Audio: {args.output}  Duration: {res['duration']:.2f}s")

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

from tts_segmenter import LANGUAGE_POLICIES, segment_script, describe_segments

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
                or os.getenv("ELEVENLABS_VOICE_ID")
                or "ZOgeDYxfyev5qgOXq2lN")
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
            "pause_after": seg["pause_after"],
            "voice_id": settings["voice_id"],
            "model_id": settings["model_id"],
            "speed": max(0.7, min(1.2, speed)),
            "previous_text": segments[i - 1]["text"] if i > 0 else None,
            "next_text": segments[i + 1]["text"] if i + 1 < len(segments) else None,
        })
    return calls


# ── Real synthesis ────────────────────────────────────────────────────

def _synthesize_segment(call: Dict, out_path: str, settings: Dict) -> Dict:
    """One ElevenLabs request. Returns {'duration', 'words': [...] or None}.

    Tries the with-timestamps endpoint first (exact char timings); falls
    back to the plain convert stream.
    """
    from tts_elevenlabs import get_client, _elevenlabs_with_retry
    from tts_common import get_audio_duration
    from elevenlabs.types import VoiceSettings

    client = get_client()
    vs = VoiceSettings(
        stability=settings["stability"],
        similarity_boost=settings["similarity"],
        style=settings["style"],
        use_speaker_boost=True,
        speed=call["speed"],
    )
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
    except Exception as e:
        logger.info("with_timestamps unavailable (%s) — using plain convert", e)
        _elevenlabs_with_retry(client, out_path, **kwargs)

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
) -> Dict:
    """Generate the full narration mp3 + timestamp dict for a script.

    Returns {'duration', 'words', 'segments', 'tts_calls'} where every
    word has global start/end and an is_english flag derived from its
    segment's language.
    """
    if dry_run is None:
        dry_run = os.getenv("TTS_DRY_RUN", "").strip() in ("1", "true", "yes")

    settings = resolve_settings()
    if voice_id:
        settings["voice_id"] = voice_id
    calls = plan_calls(script_data, settings)
    if not calls:
        raise ValueError("Script produced no TTS segments (empty full_script?)")

    logger.info("Bilingual TTS: %d segments (%d EN) voice=%s model=%s",
                len(calls), sum(1 for c in calls if c["is_english"]),
                settings["voice_id"], settings["model_id"])

    if dry_run:
        return _dry_run(calls, script_data, output_path, settings)

    from tts_common import generate_silence

    temp_dir = tempfile.mkdtemp(prefix="el_bilingual_")
    audio_files: List[str] = []
    all_words: List[Dict] = []
    running = 0.0
    try:
        for call in calls:
            seg_path = os.path.join(temp_dir, f"seg_{call['index']:03d}.mp3")
            logger.info("  [%02d] %-2s %s", call["index"], call["lang"],
                        call["text"][:70])
            res = _synthesize_segment(call, seg_path, settings)
            seg_words = res["words"] or _estimate_words(call["text"],
                                                        res["duration"])
            for w in seg_words:
                all_words.append({
                    "word": w["word"],
                    "start": round(w["start"] + running, 3),
                    "end": round(w["end"] + running, 3),
                    "is_english": call["is_english"],
                })
            audio_files.append(seg_path)
            running += res["duration"]

            gap = call["pause_after"]
            if call["index"] + 1 < len(calls) and gap > 0.01:
                sil = os.path.join(temp_dir, f"sil_{call['index']:03d}.mp3")
                generate_silence(gap, sil)
                audio_files.append(sil)
                running += gap

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

        result = _build_result(script_data, all_words, duration, calls)
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
                  calls: List[Dict]) -> Dict:
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
        "tts_model_id": (calls[0].get("model_id") if calls else None),
        "tts_calls": [{k: c[k] for k in
                       ("index", "lang", "text", "speed", "pause_after")}
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

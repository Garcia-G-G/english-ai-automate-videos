#!/usr/bin/env python3
"""Generate a lesson's narration — one mp3 + word timings per beat — for lesson_scene.py.

    python3 gen_audio.py --lesson lessons/third-person-s.json                 # ElevenLabs, Matilda
    python3 gen_audio.py --lesson lessons/x.json --voices laura=VOICE_ID     # another voice
    python3 gen_audio.py --lesson lessons/x.json --offline                   # sandbox: Piper voices

Default (owner's ear, 2026-10-14): ONE request per beat with eleven_multilingual_v2, both
languages in the same text, word timings from the with-timestamps alignment. A {{pause:N}}
splits the beat into one request per side, joined with the silence. Of six ways tried on
make-vs-do b18 and can-could-pedir b05/b08 it was the only one with no cuts and no strange
sounds in all three (audio/_probe/variants, STEP_51.md). Since STEP 55 the model is
eleven_v4 with language_code=es at speed 0.92: multilingual_v2 (still `--model
eleven_multilingual_v2`) read short English words with Spanish sounds; v4 was the only
variant the owner heard say every one right. No onset gate on this path: the detector
flags this audio wrongly and a retry would pay for a whole beat. After the audio, the
English-words audit (probes/english_words_audit.py, local Whisper) lists the beats it
flags — a report for the owner's ear, not a retry (--no-english-audit skips it).

--stitch keeps the old path for comparison: `[[English]]` spans synthesized as their own
segments with language_code=en (turbo v2.5), the rest es, stitched with ffmpeg and the word
timings shifted by each segment's offset, with the onset gate. --offline always stitches.

The ElevenLabs key is read from english-ai-videos/.env, overridden by ./.env (the
admin's Manim page writes that one). It is never printed or stored elsewhere.
Standard library + ffmpeg/ffprobe; the offline mode additionally needs sherpa-onnx
and the Piper models under ../tts-models/ (sandbox only, never the product voice).

Cache: a beat is regenerated only when its spoken text changed since the last run
(the manifest remembers the text), so editing one sentence costs one sentence.
"""
import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lesson as L  # noqa: E402

DEFAULT_ENV = HERE.parent.parent / ".env"          # english-ai-videos/.env
MATILDA = "XrExE9yKIg1WjnnlVkGX"
PRICE_PER_1K_CHARS = 0.10
# Models that accept language_code (per-segment accent) and return timestamps.
SEGMENT_MODELS = ("eleven_turbo_v2_5", "eleven_flash_v2_5")
DEFAULT_MODEL = "eleven_turbo_v2_5"           # --stitch only (the lesson's "model" applies there)
LANGUAGE_CODE_MODELS = SEGMENT_MODELS + ("eleven_v4",)   # multilingual_v2 refuses language_code
ONE_REQUEST_MODEL = "eleven_v4"     # owner's ear, STEP 55: every English word English, no cuts; --model eleven_multilingual_v2 for the old one
# The stitch rule (context, onset gate, gaps) is shared with the Shorts: src/stitch.py.
_SRC = str(HERE.parents[1] / "src")
if _SRC not in sys.path:
    sys.path.append(_SRC)
import stitch as S  # noqa: E402

GAP_AFTER, DEFAULT_GAP = S.GAP_AFTER, S.DEFAULT_GAP
EDGE_PAD = 0.04             # silence kept at each end of a segment after trimming
SILENCE_DB = -42            # below this a segment edge counts as silence
TARGET_RMS_DB = -20.0       # every segment is brought near this level before joining
MAX_GAIN_DB = 6.0


# ── env ───────────────────────────────────────────────────────────────────────

def read_env(path: Path) -> dict:
    values = {}
    for source in (path, HERE / ".env"):
        if source.exists():
            for line in source.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    values[k.strip()] = v.strip().strip('"').strip("'")
    return values


# ── ElevenLabs ────────────────────────────────────────────────────────────────

def alignment_to_words(alignment: dict) -> list:
    words, current, start, end = [], "", None, None
    for ch, cs, ce in zip(alignment["characters"], alignment["character_start_times_seconds"],
                          alignment["character_end_times_seconds"]):
        if ch.isspace():
            if current:
                words.append({"word": current, "start": start, "end": end})
                current, start = "", None
        else:
            if not current:
                start = cs
            current += ch
            end = ce
    if current:
        words.append({"word": current, "start": start, "end": end})
    return words


def eleven_segment(api_key: str, voice_id: str, text: str, lang: str, model: str, settings: dict,
                   previous_text: str = "", next_text: str = "", previous_request_ids: list = (),
                   on_body=None) -> tuple:
    """(mp3 bytes, words, request_id) for one segment.

    Request stitching: `previous_text` / `next_text` tell the model what surrounds this
    segment and `previous_request_ids` lets it continue the prosody of the segments just
    generated — so a switch of language does not restart the voice "cold"."""
    body = {"text": text, "model_id": model, "voice_settings": dict(settings)}
    speed = float(body["voice_settings"].pop("speed", 1.0) or 1.0)
    if abs(speed - 1.0) >= 0.01:
        body["voice_settings"]["speed"] = round(speed, 2)     # 0.7–1.2; slower English for learners
    if model in LANGUAGE_CODE_MODELS:
        body["language_code"] = lang
    if previous_text:
        body["previous_text"] = previous_text[-300:]
    if next_text:
        body["next_text"] = next_text[:300]
    if previous_request_ids:
        body["previous_request_ids"] = list(previous_request_ids)[-3:]
    if on_body is not None:
        on_body(body)                                          # --keep-raw: what was asked (the key is a header)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128"
    for attempt in range(2):
        request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                         headers={"xi-api-key": api_key, "Content-Type": "application/json",
                                                  "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.load(response)
                request_id = response.headers.get("request-id", "")
            break
        except urllib.error.HTTPError as error:
            detail = error.read()[:400].decode("utf-8", "replace")
            if attempt == 0 and error.code in (400, 422) and "speed" in detail and "speed" in body["voice_settings"]:
                body["voice_settings"].pop("speed")       # this model/plan does not take speed: say it once, go on
                print("  note: ElevenLabs refused voice_settings.speed for this model; continuing at 1.0", flush=True)
                continue
            raise urllib.error.HTTPError(error.url, error.code, detail, error.headers, None) from None
    alignment = result.get("normalized_alignment") or result["alignment"]
    return base64.b64decode(result["audio_base64"]), alignment_to_words(alignment), request_id


def stitch_context(segs: list, n: int, previous_spoken: str, request_ids: list, full: bool = False) -> tuple:
    """(previous_text, next_text, previous_request_ids) for segment n of a beat — stitch.context:
    at a language switch and at the start of a beat only the text that follows is sent; full
    stitching where the voice continues in the same language (across a {{pause}})."""
    after = " ".join(x["text"] for x in segs[n + 1:] if "text" in x).strip()
    before = " ".join(x["text"] for x in segs[:n] if "text" in x).strip()
    last = next((x["lang"] for x in reversed(segs[:n]) if "lang" in x), None)
    previous, following = S.context(last, segs[n]["lang"], before or previous_spoken, after, full)
    return previous, following, (list(request_ids) if previous else [])


def beat_chunks(narration: str, lang: str) -> list:
    """[{text, lang}] / [{pause}]: the beat cut only at {{pause:N}} — each text side, both
    languages in it, is one request."""
    parts = L.PAUSE.split(narration)                # text, seconds, text, …
    out = []
    for n, part in enumerate(parts):
        if n % 2:
            out.append({"pause": min(L.MAX_PAUSE, float(part))})
        elif L.spoken_text(part):
            out.append({"text": L.spoken_text(part), "lang": lang})
    return out


# ── Onset gate ────────────────────────────────────────────────────────────────
# Even with the stitching fix the model starts ~3 segments in 10 mid-sound or with a ~50 ms
# fragment. Every segment is checked as it arrives and re-asked up to ONSET_RETRIES times.
ONSET_RETRIES = S.ONSET_RETRIES


def onset_report(path: Path) -> dict:
    """{clean, first_db, fragment} for one segment as ElevenLabs returned it (stitch.onset_values
    and stitch.onset_clean at the lessons' −30 dB start limit)."""
    v = S.onset_values(path)
    return {"clean": S.onset_clean(v), "first_db": v["start_db"] if v["start_db"] is not None else 0.0,
            "fragment": v["fragment"] or v["doubled_onset"]}


def cleanest(takes: list) -> dict:
    """The first clean take, else the one with no fragment and the quietest start."""
    return next((t for t in takes if t["onset"]["clean"]), None) or min(
        takes, key=lambda t: (t["onset"]["fragment"] is not None, t["onset"]["first_db"]))


# ── Offline (sandbox) voices ──────────────────────────────────────────────────

class OfflinePiper:
    MODELS = {"es": "vits-piper-es_MX-claude-high", "en": "vits-piper-en_US-amy-medium"}

    def __init__(self, models_dir: Path):
        import sherpa_onnx
        self.tts = {}
        for lang, name in self.MODELS.items():
            d = models_dir / name
            cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(next(d.glob("*.onnx"))), tokens=str(d / "tokens.txt"),
                                                           data_dir=str(d / "espeak-ng-data")),
                num_threads=4, provider="cpu"), max_num_sentences=1)
            self.tts[lang] = sherpa_onnx.OfflineTts(cfg)

    def segment(self, text: str, lang: str) -> tuple:
        import numpy as np
        audio = self.tts[lang].generate(text, sid=0, speed=0.9 if lang == "es" else 0.95)
        pcm = (np.clip(np.asarray(audio.samples), -1, 1) * 32767).astype("<i2").tobytes()
        mp3 = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(audio.sample_rate), "-ac", "1",
                              "-i", "pipe:0", "-codec:a", "libmp3lame", "-q:a", "3", "-f", "mp3", "pipe:1"],
                             input=pcm, capture_output=True, check=True).stdout
        duration, n = len(audio.samples) / audio.sample_rate, max(1, len(text))
        words = [{"word": m.group(0), "start": round(duration * m.start() / n, 3), "end": round(duration * m.end() / n, 3)}
                 for m in re.finditer(r"\S+", text)]          # linear guess — offline has no alignment
        return mp3, words, ""


# ── Stitching ─────────────────────────────────────────────────────────────────

def probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    value = out.stdout.strip()
    return float(value) if value and value != "N/A" else 0.0


gap_after = S.gap_after


def shift_words(pieces: list) -> list:
    """pieces = [{words, offset, lead_cut?}] → one flat list with global times: each word
    moves by the segment's offset in the beat, minus the leading silence that was trimmed."""
    out = []
    for piece in pieces:
        cut = piece.get("lead_cut", 0.0)
        for w in piece["words"]:
            start = max(0.0, w["start"] - cut)
            end = max(start, w["end"] - cut)
            out.append({"word": w["word"], "start": round(start + piece["offset"], 3),
                        "end": round(end + piece["offset"], 3)})
    return out


def rms_db(wav: Path) -> float:
    out = subprocess.run(["ffmpeg", "-i", str(wav), "-af", "astats=measure_overall=RMS_level:measure_perchannel=none",
                          "-f", "null", "-"], capture_output=True, text=True)
    match = re.search(r"RMS level dB:\s*(-?[\d.]+|-inf)", out.stderr)
    return float(match.group(1)) if match and match.group(1) != "-inf" else -60.0


def prepare_segment(src: Path, wav: Path) -> tuple:
    """Decode, trim edge silence to EDGE_PAD, fade the edges. Returns (lead_cut, duration):
    `lead_cut` is how much leading silence went away, so word times can be shifted."""
    raw = wav.with_suffix(".raw.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ar", "44100", "-ac", "1", str(raw)], check=True)
    total = probe_duration(raw)
    head = wav.with_suffix(".head.wav")
    trim = f"silenceremove=start_periods=1:start_threshold={SILENCE_DB}dB:start_silence={EDGE_PAD}"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af", trim, str(head)], check=True)
    after_head = probe_duration(head)
    if after_head < 0.05:                      # nothing but silence: keep it as it is
        shutil.copyfile(raw, wav)
        for tmp in (raw, head):
            tmp.unlink(missing_ok=True)
        return 0.0, total
    lead_cut = max(0.0, total - after_head)
    both = wav.with_suffix(".both.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(head), "-af", f"areverse,{trim},areverse", str(both)], check=True)
    duration = probe_duration(both)
    fade_out = max(0.0, duration - 0.02)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(both), "-af",
                    f"afade=t=in:st=0:d=0.012,afade=t=out:st={fade_out:.3f}:d=0.02", str(wav)], check=True)
    for tmp in (raw, head, both):
        tmp.unlink(missing_ok=True)
    return lead_cut, duration


def level_match(wavs: list) -> None:
    """Bring every segment to the same loudness (median of the beat, near TARGET_RMS_DB), ±MAX_GAIN_DB."""
    levels = [rms_db(w) for w in wavs]
    if not levels:
        return
    target = sorted(levels)[len(levels) // 2]
    target = max(min(target, TARGET_RMS_DB + 3), TARGET_RMS_DB - 3)
    for wav, level in zip(wavs, levels):
        gain = max(-MAX_GAIN_DB, min(MAX_GAIN_DB, target - level))
        if abs(gain) >= 0.5:
            out = wav.with_suffix(".lvl.wav")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af", f"volume={gain:.2f}dB", str(out)], check=True)
            out.replace(wav)


def stitch(segment_files: list, texts: list, target: Path, keep_dir: Path = None, names: list = None) -> tuple:
    """Trim, level and join the segments with punctuation-sized gaps and 12/20 ms fades.
    Returns (offsets, lead_cuts): where each trimmed segment starts in the beat, and how much
    leading silence each one lost (word times shift by -lead_cut + offset)."""
    offsets, lead_cuts, cursor = [], [], 0.0
    with tempfile.TemporaryDirectory() as tmp:
        wavs = []
        for n, path in enumerate(segment_files):
            wav = Path(tmp) / f"seg{n}.wav"
            lead_cut, _ = prepare_segment(Path(path), wav)
            wavs.append(wav)
            lead_cuts.append(lead_cut)
        level_match(wavs)
        if keep_dir is not None:                               # --keep-raw: each segment as it goes into the beat
            for wav, name in zip(wavs, names):
                shutil.copyfile(wav, Path(keep_dir) / f"{name}.processed.wav")
        parts = []
        for n, (wav, text) in enumerate(zip(wavs, texts)):
            offsets.append(cursor)
            parts.append(wav)
            cursor += probe_duration(wav)
            if n < len(wavs) - 1:
                gap = gap_after(text)
                silence = Path(tmp) / f"gap{n}.wav"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                                "-t", f"{gap:.3f}", str(silence)], check=True)
                parts.append(silence)
                cursor += gap
        listing = Path(tmp) / "list.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                        "-codec:a", "libmp3lame", "-b:a", "128k", str(target)], check=True)
    return offsets, lead_cuts


def english_report(out: Path, lesson: dict, made_ids: set, name: str):
    """List the beats whose English the local Whisper does not hear as English — a report, no retry."""
    try:
        from probes import english_words_audit as E
        flagged = E.lesson_report(out, lesson, made_ids)
    except Exception as error:                                # the audio is made; a missing Whisper must not undo it
        print(f"  [{name}] English-words audit skipped: {error}")
        return
    print(f"  [{name}] English-words audit: {len(flagged)} span(s) flagged → {(out / 'english_audit.json').relative_to(HERE)}")
    for beat, r in flagged:
        print(f"    {beat} {r['time']:>6}s  {r['expected']!r} heard {r['heard_en']!r}{'  (es too)' if r['es_too'] else ''}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lesson", required=True, type=Path)
    parser.add_argument("--voices", default=None, help="name=VOICE_ID[,name=VOICE_ID]; default matilda")
    parser.add_argument("--model", default=None, help=f"default {ONE_REQUEST_MODEL}; with --stitch the lesson's, else {DEFAULT_MODEL}")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--offline", action="store_true", help="Piper voices via sherpa-onnx (sandbox only)")
    parser.add_argument("--models-dir", type=Path, default=HERE.parent / "tts-models")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="regenerate every beat even if its text did not change")
    parser.add_argument("--stitch", action="store_true",
                        help="the old path: one turbo request per language segment, stitched, with the onset gate")
    parser.add_argument("--no-onset-gate", action="store_true",
                        help=f"keep the first take of every segment (default: re-ask a dirty onset up to {ONSET_RETRIES} times)")
    parser.add_argument("--full-stitching", action="store_true",
                        help="send previous text and request ids at language switches too (the old behaviour; dirtier onsets)")
    parser.add_argument("--no-english-audit", action="store_true",
                        help="skip the local Whisper report of English words heard with Spanish sounds")
    parser.add_argument("--only", default=None, help="b05,b08: regenerate just these beats (others are left as they are)")
    parser.add_argument("--keep-raw", action="store_true",
                        help="save every segment as ElevenLabs returned it, its request (no key) and its processed form, "
                             "under audio/<lesson>/<voice>/_raw/")
    args = parser.parse_args()

    lesson = L.load(args.lesson)
    problems = L.validate(lesson)
    if problems:
        sys.exit("lesson.json has problems:\n  " + "\n  ".join(problems))
    for note in L.warnings(lesson):
        print("note:", note)
    beats = lesson["beats"]
    chars = L.character_count(lesson)
    settings = lesson.get("voice_settings") or {"stability": 0.45, "similarity_boost": 0.8, "style": 0.3,
                                                "use_speaker_boost": True}
    stitched = args.stitch or args.offline           # Piper speaks one language per call
    shape = "stitched" if stitched else "one-request"
    model = args.model or (lesson.get("model") or DEFAULT_MODEL if stitched else ONE_REQUEST_MODEL)
    speeds = {"en": float(lesson.get("english_speed", 0.92)), lesson.get("language", "es"): float(lesson.get("speed", 1.0))}
    speed = float(lesson.get("speed", L.DEFAULT_SPEED))   # one request: the whole beat at one pace
    language = lesson.get("language", "es") if model in LANGUAGE_CODE_MODELS else None   # what language_code said

    if args.offline:
        voices = {"offline": "piper"}
    else:
        env = read_env(args.env)
        api_key = env.get("ELEVENLABS_API_KEY", "")
        if not args.dry_run and len(api_key) < 10:
            sys.exit("ELEVENLABS_API_KEY missing (english-ai-videos/.env or ./.env).")
        voices = dict(pair.split("=", 1) for pair in args.voices.split(",")) if args.voices else {"matilda": MATILDA}

    n_segments = sum(1 for b in beats for x in (L.segments if stitched else beat_chunks)(b["narration"], "es") if "text" in x)
    print(f"lesson {lesson['id']}: {len(beats)} beats, {n_segments} segments, {chars} characters, "
          f"≈{L.estimate_minutes(lesson)} min, model {model}, {shape}")
    print(f"voices: {', '.join(f'{n} ({v[:4]}…{v[-4:]})' if len(v) > 8 else f'{n} ({v})' for n, v in voices.items())}")
    if not args.offline:
        print(f"estimated cost: ~${chars * len(voices) / 1000 * PRICE_PER_1K_CHARS:.2f} (cached beats cost nothing)")
    if args.dry_run:
        for b in beats:
            for x in L.segments(b["narration"]):
                print(f"  {b['id']:>5} [{x['lang']}] {x['text']}" if "text" in x else f"  {b['id']:>5} [pause] {x['pause']} s")
        return 0

    piper = OfflinePiper(args.models_dir) if args.offline else None
    for name, voice_id in voices.items():
        out = HERE / "audio" / lesson["id"] / name
        out.mkdir(parents=True, exist_ok=True)
        manifest_path = out / "manifest.json"
        previous = {}
        if manifest_path.exists():
            previous = {b["id"]: b for b in json.loads(manifest_path.read_text()).get("beats", [])}
        manifest = {"voice": name, "voice_id": voice_id, "model": model, "shape": shape, "voice_settings": settings,
                    "lesson": lesson["id"], "beats": []}
        made, extra_chars, made_ids = 0, 0, set()
        request_ids, previous_spoken = [], ""     # stitching context carried across segments and beats
        only = set(args.only.split(",")) if args.only else None
        raw_dir = out / "_raw"
        if args.keep_raw:
            raw_dir.mkdir(exist_ok=True)
        for beat in beats:
            spoken, pause_list = L.spoken_text(beat["narration"]), L.pauses(beat["narration"])
            mp3, words_path = out / f"{beat['id']}.mp3", out / f"{beat['id']}.words.json"
            old = previous.get(beat["id"])
            if only is not None and beat["id"] not in only:      # --only: every other beat stays as it is
                if old:
                    manifest["beats"].append(old)
                previous_spoken = spoken
                continue
            if (not args.force and only is None and old and old.get("text") == spoken and old.get("pauses", []) == pause_list
                    and old.get("model") == model and old.get("shape") == shape     # never reuse another model's audio
                    and (stitched or (old.get("speed", 1.0) == speed               # ...or another pace's,
                                      and old.get("language") == language))         # ...or another language_code's
                    and mp3.exists() and words_path.exists()):
                manifest["beats"].append({**old, "text": spoken})
                previous_spoken = spoken
                continue
            segs = (L.segments if stitched else beat_chunks)(beat["narration"], lesson.get("language", "es"))
            take_log = []
            names = [f"{beat['id']}_{n:02d}_{seg.get('lang', 'pause')}" for n, seg in enumerate(segs)]
            requests = []
            with tempfile.TemporaryDirectory() as tmp:
                files, pieces = [], []
                for n, seg in enumerate(segs):
                    if "pause" in seg:                       # {{pause:N}} — silence, no words, no call
                        path = Path(tmp) / f"seg{n}.mp3"
                        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                                        "-t", f"{seg['pause']:.2f}", "-codec:a", "libmp3lame", "-b:a", "128k", str(path)], check=True)
                        files.append(path)
                        pieces.append({"words": []})
                        continue
                    before, after, context_ids = stitch_context(segs, n, previous_spoken, request_ids, args.full_stitching)
                    lang_settings = {**settings, "speed": speeds.get(seg["lang"], 1.0)}
                    try:
                        if piper:
                            audio, words, rid = piper.segment(seg["text"], seg["lang"])
                        elif not stitched:
                            def keep(body, n=n):
                                requests.append({"segment": names[n], "text": body["text"], "model": body["model_id"]})
                            audio, words, rid = eleven_segment(
                                api_key, voice_id, seg["text"], seg["lang"], model,
                                {**settings, "speed": speed}, on_body=keep if args.keep_raw else None)
                        else:
                            last_lang = next((x["lang"] for x in reversed(segs[:n]) if "lang" in x), None)

                            def keep(body, n=n, seg=seg, last_lang=last_lang):
                                requests.append({"segment": names[n], "lang": seg["lang"], "text": body["text"],
                                                 "after_language_switch": last_lang is not None and last_lang != seg["lang"],
                                                 "previous_text": bool(body.get("previous_text")),
                                                 "next_text": bool(body.get("next_text")),
                                                 "previous_request_ids": len(body.get("previous_request_ids", [])),
                                                 "language_code": body.get("language_code"), "model": body["model_id"],
                                                 "speed": body["voice_settings"].get("speed", 1.0)})
                            takes = []
                            for attempt in range(1 + (0 if args.no_onset_gate else ONSET_RETRIES)):
                                audio, words, rid = eleven_segment(api_key, voice_id, seg["text"], seg["lang"], model,
                                                                   lang_settings, previous_text=before, next_text=after,
                                                                   previous_request_ids=context_ids,
                                                                   on_body=keep if args.keep_raw and not takes else None)
                                probe = (raw_dir / f"{names[n]}_take{attempt + 1}.mp3" if args.keep_raw
                                         else Path(tmp) / f"take{n}_{attempt}.mp3")        # --keep-raw keeps every take
                                probe.write_bytes(audio)
                                takes.append({"audio": audio, "words": words, "rid": rid, "onset": onset_report(probe)})
                                if args.no_onset_gate or takes[-1]["onset"]["clean"]:
                                    break
                            best = cleanest(takes)
                            audio, words, rid = best["audio"], best["words"], best["rid"]
                            extra_chars += len(seg["text"]) * (len(takes) - 1)
                            log = {"segment": names[n], "takes": len(takes), "kept": takes.index(best) + 1,
                                   "clean": best["onset"]["clean"], "first_db": best["onset"]["first_db"]}
                            take_log.append(log)
                            if not best["onset"]["clean"]:
                                print(f"  ! {names[n]}: no clean onset in {len(takes)} takes — kept the cleanest "
                                      f"(first 5 ms {best['onset']['first_db']} dB, fragment {best['onset']['fragment']})")
                            if args.keep_raw and requests:
                                requests[-1].update(log)
                    except urllib.error.HTTPError as error:
                        detail = error.msg if isinstance(error.msg, str) else error.read()[:300].decode("utf-8", "replace")
                        sys.exit(f"ElevenLabs answered {error.code} on {beat['id']} segment {n} ({name}): {detail}")
                    if rid:
                        request_ids = (request_ids + [rid])[-3:]
                    path = Path(tmp) / f"seg{n}.mp3"
                    path.write_bytes(audio)
                    if args.keep_raw:
                        (raw_dir / f"{names[n]}.mp3").write_bytes(audio)      # exactly as ElevenLabs returned it
                    files.append(path)
                    pieces.append({"words": words})
                offsets, lead_cuts = stitch(files, [s.get("text", ".") for s in segs], mp3,
                                            keep_dir=raw_dir if args.keep_raw else None, names=names)
                if args.keep_raw:
                    (raw_dir / f"{beat['id']}.requests.json").write_text(
                        json.dumps({"beat": beat["id"], "requests": requests,
                                    "offsets": [round(o, 3) for o in offsets], "lead_cuts": [round(c, 3) for c in lead_cuts]},
                                   ensure_ascii=False, indent=1))
                for piece, offset, cut in zip(pieces, offsets, lead_cuts):
                    piece["offset"], piece["lead_cut"] = offset, cut
            previous_spoken = spoken
            words_path.write_text(json.dumps(shift_words(pieces), ensure_ascii=False, indent=1))
            retried = [t for t in take_log if t["takes"] > 1]
            manifest["beats"].append({"id": beat["id"], "text": spoken, "pauses": pause_list, "model": model, "shape": shape,
                                      **({} if stitched else {"speed": speed, "language": language}), "mp3": mp3.name,
                                      "words": words_path.name, "segments": len(segs), "takes": take_log})
            made += 1
            made_ids.add(beat["id"])
            print(f"  [{name}] {beat['id']}: {len(segs)} segment(s), {mp3.stat().st_size // 1024} KB, "
                  f"{len(retried)} re-asked for a clean onset, {sum(not t['clean'] for t in take_log)} still dirty")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
        print(f"  [{name}] {made} beat(s) generated, {len(beats) - made} reused → {manifest_path.relative_to(HERE)}")
        if not (piper or args.no_english_audit):
            english_report(out, lesson, made_ids, name)
        if extra_chars:
            print(f"  [{name}] onset gate: +{extra_chars} characters re-asked (~${extra_chars / 1000 * PRICE_PER_1K_CHARS:.3f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

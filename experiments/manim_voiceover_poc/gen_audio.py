#!/usr/bin/env python3
"""Generate a lesson's narration — one mp3 + word timings per beat — for lesson_scene.py.

    python3 gen_audio.py --lesson lessons/third-person-s.json                 # ElevenLabs, Matilda
    python3 gen_audio.py --lesson lessons/x.json --voices laura=VOICE_ID     # another voice
    python3 gen_audio.py --lesson lessons/x.json --offline                   # sandbox: Piper voices

Bilingual by construction: `[[English]]` spans in the narration are synthesized as
their own segments with language_code=en, the rest with language_code=es — one
voice, two accents, exactly like the channel's tts_bilingual.py — then stitched
with ffmpeg and the word timings shifted by each segment's offset. That is what
makes the English read as English and the Spanish as Spanish.

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
DEFAULT_MODEL = "eleven_turbo_v2_5"
GAP_AFTER = {".": 0.30, "?": 0.30, "!": 0.30, ":": 0.20, ",": 0.14, ";": 0.18}
DEFAULT_GAP = 0.05          # a language switch mid-sentence: pad + gap + pad ≈ 130 ms
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
                   previous_text: str = "", next_text: str = "", previous_request_ids: list = ()) -> tuple:
    """(mp3 bytes, words, request_id) for one segment.

    Request stitching: `previous_text` / `next_text` tell the model what surrounds this
    segment and `previous_request_ids` lets it continue the prosody of the segments just
    generated — so a switch of language does not restart the voice "cold"."""
    body = {"text": text, "model_id": model, "voice_settings": dict(settings)}
    speed = float(body["voice_settings"].pop("speed", 1.0) or 1.0)
    if abs(speed - 1.0) >= 0.01:
        body["voice_settings"]["speed"] = round(speed, 2)     # 0.7–1.2; slower English for learners
    if model in SEGMENT_MODELS:
        body["language_code"] = lang
    if previous_text:
        body["previous_text"] = previous_text[-300:]
    if next_text:
        body["next_text"] = next_text[:300]
    if previous_request_ids:
        body["previous_request_ids"] = list(previous_request_ids)[-3:]
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


def gap_after(text: str) -> float:
    return GAP_AFTER.get(text.rstrip()[-1:], DEFAULT_GAP)


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


def stitch(segment_files: list, texts: list, target: Path) -> tuple:
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lesson", required=True, type=Path)
    parser.add_argument("--voices", default=None, help="name=VOICE_ID[,name=VOICE_ID]; default matilda")
    parser.add_argument("--model", default=None, help=f"default {DEFAULT_MODEL}")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--offline", action="store_true", help="Piper voices via sherpa-onnx (sandbox only)")
    parser.add_argument("--models-dir", type=Path, default=HERE.parent / "tts-models")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="regenerate every beat even if its text did not change")
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
    model = args.model or lesson.get("model") or DEFAULT_MODEL
    speeds = {"en": float(lesson.get("english_speed", 0.92)), lesson.get("language", "es"): float(lesson.get("speed", 1.0))}

    if args.offline:
        voices = {"offline": "piper"}
    else:
        env = read_env(args.env)
        api_key = env.get("ELEVENLABS_API_KEY", "")
        if not args.dry_run and len(api_key) < 10:
            sys.exit("ELEVENLABS_API_KEY missing (english-ai-videos/.env or ./.env).")
        voices = dict(pair.split("=", 1) for pair in args.voices.split(",")) if args.voices else {"matilda": MATILDA}

    n_segments = sum(1 for b in beats for x in L.segments(b["narration"]) if "text" in x)
    print(f"lesson {lesson['id']}: {len(beats)} beats, {n_segments} segments, {chars} characters, "
          f"≈{L.estimate_minutes(lesson)} min, model {model}")
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
        manifest = {"voice": name, "voice_id": voice_id, "model": model, "voice_settings": settings,
                    "lesson": lesson["id"], "beats": []}
        made = 0
        request_ids, previous_spoken = [], ""     # stitching context carried across segments and beats
        for beat in beats:
            spoken, pause_list = L.spoken_text(beat["narration"]), L.pauses(beat["narration"])
            mp3, words_path = out / f"{beat['id']}.mp3", out / f"{beat['id']}.words.json"
            old = previous.get(beat["id"])
            if (not args.force and old and old.get("text") == spoken and old.get("pauses", []) == pause_list
                    and mp3.exists() and words_path.exists()):
                manifest["beats"].append({**old, "text": spoken})
                previous_spoken = spoken
                continue
            segs = L.segments(beat["narration"], lesson.get("language", "es"))
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
                    before = " ".join(x.get("text", "") for x in segs[:n]).strip() or previous_spoken
                    after = " ".join(x.get("text", "") for x in segs[n + 1:]).strip()
                    lang_settings = {**settings, "speed": speeds.get(seg["lang"], 1.0)}
                    try:
                        if piper:
                            audio, words, rid = piper.segment(seg["text"], seg["lang"])
                        else:
                            audio, words, rid = eleven_segment(api_key, voice_id, seg["text"], seg["lang"], model, lang_settings,
                                                               previous_text=before, next_text=after,
                                                               previous_request_ids=request_ids)
                    except urllib.error.HTTPError as error:
                        detail = error.msg if isinstance(error.msg, str) else error.read()[:300].decode("utf-8", "replace")
                        sys.exit(f"ElevenLabs answered {error.code} on {beat['id']} segment {n} ({name}): {detail}")
                    if rid:
                        request_ids = (request_ids + [rid])[-3:]
                    path = Path(tmp) / f"seg{n}.mp3"
                    path.write_bytes(audio)
                    files.append(path)
                    pieces.append({"words": words})
                offsets, lead_cuts = stitch(files, [s.get("text", ".") for s in segs], mp3)
                for piece, offset, cut in zip(pieces, offsets, lead_cuts):
                    piece["offset"], piece["lead_cut"] = offset, cut
            previous_spoken = spoken
            words_path.write_text(json.dumps(shift_words(pieces), ensure_ascii=False, indent=1))
            manifest["beats"].append({"id": beat["id"], "text": spoken, "pauses": pause_list, "mp3": mp3.name,
                                      "words": words_path.name, "segments": len(segs)})
            made += 1
            print(f"  [{name}] {beat['id']}: {len(segs)} segment(s), {mp3.stat().st_size // 1024} KB")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
        print(f"  [{name}] {made} beat(s) generated, {len(beats) - made} reused → {manifest_path.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

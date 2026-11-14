"""The one speech service the lesson scene uses: pre-generated audio.

gen_audio.py makes `audio/<lesson>/<voice>/<beat>.mp3` + `<beat>.words.json` +
`manifest.json` (ElevenLabs on the owner's Mac, or the offline voices in a
sandbox). The scene never talks to a TTS API: it looks each beat up by id, checks
the text still matches what was recorded, and turns the word timings into
manim-voiceover word boundaries so `<bookmark/>` lands on the spoken word.
"""
import hashlib
import json
from pathlib import Path

from manim_voiceover.helper import remove_bookmarks
from manim_voiceover.services.base import SpeechService

AUDIO_OFFSET_RESOLUTION = 10_000_000  # manim-voiceover's unit for audio_offset


class StaleAudioError(RuntimeError):
    """The narration changed after the audio was generated — regenerate it."""


def _deesser():
    """src/deesser.py (STEP 80 §00): the one de-esser every narration path uses."""
    import sys
    src = str(Path(__file__).resolve().parents[2] / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import deesser
    return deesser


class PrerecordedService(SpeechService):
    def __init__(self, folder, deess=True, **kwargs):
        super().__init__(**kwargs)
        self.folder = Path(folder)
        self.deess = deess                       # STEP 80 §00: the voice is de-essed into the cache
        self.deesser = {}                        # beat id -> the de-esser's measure
        manifest = json.loads((self.folder / "manifest.json").read_text(encoding="utf-8"))
        self.voice = manifest["voice"]
        self.by_id = {b["id"]: b for b in manifest["beats"]}

    def generate_from_text(self, text, cache_dir=None, path=None, beat_id=None, **kwargs):
        cache_dir = Path(cache_dir or self.cache_dir)
        plain = " ".join(remove_bookmarks(text).split())
        beat = self.by_id.get(beat_id)
        if beat is None:
            raise StaleAudioError(f"No audio for beat {beat_id!r} in {self.folder}. Run gen_audio.py.")
        if " ".join(beat["text"].split()) != plain:
            raise StaleAudioError(f"Beat {beat_id!r}: narration changed since the audio was made. Run gen_audio.py.")
        # THE CACHE KEY IS THE MARKED TEXT AND THE AUDIO ITSELF, not the plain text.
        # Keyed on `plain`, two things went wrong silently:
        #   1. bookmarks live only in `text`. Adding {{pause:3}} to a quiz changes the
        #      marks (a new <bookmark mark='p0'/>) but not one spoken word, so the old
        #      entry came back with an input_text that had no p0, and the scene died on
        #      "There is no <bookmark mark='p0' />" (third-person-s b26-b28, 2026-10-08).
        #   2. gen_audio.py regenerates a beat's mp3 when its pauses change, but the
        #      same stale entry also handed back the OLD audio, without the silence.
        # And the copied file was named "<voice>-<beat>.mp3" for every lesson, so b26 of
        # one lesson overwrote b26 of another inside the shared media/voiceovers folder.
        mp3_bytes = (self.folder / beat["mp3"]).read_bytes()
        words_bytes = (self.folder / beat["words"]).read_bytes()
        digest = hashlib.sha1(mp3_bytes + b"\0" + words_bytes).hexdigest()[:12]
        de_cfg = _deesser().settings() if self.deess else {"enabled": False}
        input_data = {"service": "prerecorded", "voice": self.voice, "folder": str(self.folder),
                      "id": beat_id, "input_text": " ".join(text.split()), "audio": digest, "deesser": de_cfg,
                      "model": beat.get("model"), "shape": beat.get("shape"),   # one-request vs stitched, never mixed
                      "speed": beat.get("speed"), "language": beat.get("language")}
        cached = self.get_cached_result(input_data, cache_dir)
        if cached is not None and (cache_dir / cached["original_audio"]).exists():
            saved = cache_dir / (cached["original_audio"] + ".deesser.json")
            if saved.exists():
                self.deesser[beat_id] = json.loads(saved.read_text(encoding="utf-8"))
            return cached

        lesson_id = self.folder.parent.name
        measure = None
        if de_cfg.get("enabled"):
            # the voice alone, before Manim mixes the effects and before the final loudnorm;
            # a wav, so no encoder padding moves the word times
            audio_name = f"{lesson_id}-{self.voice}-{beat_id}-{digest}-deessed.wav"
            measure = _deesser().deess(self.folder / beat["mp3"], cache_dir / audio_name, de_cfg)
            (cache_dir / (audio_name + ".deesser.json")).write_text(json.dumps(measure), encoding="utf-8")
            self.deesser[beat_id] = measure
        else:
            audio_name = f"{lesson_id}-{self.voice}-{beat_id}-{digest}.mp3"
            (cache_dir / audio_name).write_bytes(mp3_bytes)
        words = json.loads(words_bytes.decode("utf-8"))
        return {"input_text": text, "input_data": input_data, "original_audio": audio_name,
                "word_boundaries": word_boundaries(plain, words)}


def word_boundaries(plain: str, words: list) -> list:
    """Map timed words onto character offsets of the plain text, in order."""
    boundaries, cursor = [], 0
    for w in words:
        token = w["word"]
        offset = plain.find(token, cursor)
        if offset < 0:                       # normalized text differs (numbers etc.)
            stripped = token.strip(".,;:!?¿¡\"'")
            offset = plain.find(stripped, cursor) if stripped else -1
            token = stripped
        if offset < 0:
            continue
        boundaries.append({"audio_offset": int(w["start"] * AUDIO_OFFSET_RESOLUTION), "text_offset": offset,
                           "word_length": len(token), "text": token, "boundary_type": "Word"})
        cursor = offset + len(token)
    return boundaries


class StillsService(SpeechService):
    """STEP 79 §1, stills mode: no TTS, ever. A beat whose recorded audio exists and still matches
    its narration uses it (real timings); any other beat gets a silent clip of the estimated
    length (lesson.SECONDS_PER_WORD, the fitted speaking rate, plus its {{pause}} seconds) with its
    words spaced evenly over it. `estimated` lists the beats that were guessed."""

    def __init__(self, folder=None, lesson=None, **kwargs):
        super().__init__(**kwargs)
        self.beats = {b["id"]: b for b in (lesson or {}).get("beats", [])}
        self.recorded = None
        if folder is not None and (Path(folder) / "manifest.json").exists():
            self.recorded = PrerecordedService(folder, deess=False, **kwargs)     # a still has no sound
        self.estimated = []

    def generate_from_text(self, text, cache_dir=None, path=None, beat_id=None, **kwargs):
        if self.recorded is not None:
            beat = self.recorded.by_id.get(beat_id)
            plain = " ".join(remove_bookmarks(text).split())
            if (beat and " ".join(beat["text"].split()) == plain and (self.recorded.folder / beat["mp3"]).exists()
                    and (self.recorded.folder / beat["words"]).exists()):
                return self.recorded.generate_from_text(text, cache_dir=cache_dir, path=path, beat_id=beat_id, **kwargs)
        return self._estimate(text, Path(cache_dir or self.cache_dir), beat_id)

    def _estimate(self, text, cache_dir, beat_id):
        import subprocess
        import lesson as L
        plain = " ".join(remove_bookmarks(text).split())
        words = plain.split()
        pause_s = sum(L.pauses(self.beats[beat_id]["narration"])) if beat_id in self.beats else 0.0
        seconds = max(1.0, len(words) * L.SECONDS_PER_WORD + pause_s)
        self.estimated.append(beat_id)
        name = f"stills-{hashlib.sha1(f'{beat_id}|{plain}|{seconds:.2f}'.encode()).hexdigest()[:12]}.mp3"
        target = cache_dir / name
        if not target.exists():
            cache_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t",
                            f"{seconds:.2f}", "-q:a", "9", str(target)], check=True)
        step = seconds / max(1, len(words))
        timed = [{"word": w, "start": round(k * step, 3), "end": round((k + 1) * step, 3)} for k, w in enumerate(words)]
        return {"input_text": text, "input_data": {"service": "stills", "id": beat_id, "input_text": plain},
                "original_audio": name, "word_boundaries": word_boundaries(plain, timed)}

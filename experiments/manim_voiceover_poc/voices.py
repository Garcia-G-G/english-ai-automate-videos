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


class PrerecordedService(SpeechService):
    def __init__(self, folder, **kwargs):
        super().__init__(**kwargs)
        self.folder = Path(folder)
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
        input_data = {"service": "prerecorded", "voice": self.voice, "folder": str(self.folder),
                      "id": beat_id, "input_text": " ".join(text.split()), "audio": digest,
                      "model": beat.get("model"), "shape": beat.get("shape"),   # one-request vs stitched, never mixed
                      "speed": beat.get("speed"), "language": beat.get("language")}
        cached = self.get_cached_result(input_data, cache_dir)
        if cached is not None and (cache_dir / cached["original_audio"]).exists():
            return cached

        lesson_id = self.folder.parent.name
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

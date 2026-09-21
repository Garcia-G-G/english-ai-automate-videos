# Manim lessons — long, narrated, bilingual explainer videos

Drive it from the admin: `./run_admin.sh` → http://localhost:8501/?page=Manim (or «🎞️ Manim» under
TOOLS). Everything the page does is also a command here, so it can run unattended.

```
lessons/<id>.json      the script: title + beats (narration with [[English]] spans, one visual per beat)
prompts/lesson_script.md   what the writer model is told — the pedagogy, the format, the limits
gen_script.py          topic → lessons/<id>.json with OpenAI (validated, one repair round)
gen_audio.py           lesson → audio/<lesson>/<voice>/<beat>.mp3 + word timings + manifest (ElevenLabs)
lesson_scene.py        the one Manim scene that renders any lesson.json
batch_run.py           N lessons → audio (only what changed) → render → renders/<lesson>/…mp4 + ledger
                       each render also gets .srt, .jpg (poster from the title card), .chapters.txt (YouTube) and .timeline.json
publish.py             a render → a Learning Routes step (WP-38 API: LR_BASE_URL + LR_STUDIO_TOKEN)
lesson.py · voices.py · renders.py   the shared contracts (validation, cues, prerecorded speech, ledger)
```

## Why the voice reads English as English and Spanish as Spanish

Every English word or phrase in a narration is written inside `[[ ]]`. `gen_audio.py` turns each
beat into segments — Spanish / English / Spanish… — and asks ElevenLabs for each one with
`language_code` (`eleven_turbo_v2_5` or `eleven_flash_v2_5`; `multilingual_v2` and `v3` ignore it),
then stitches them with ffmpeg and short pauses, and shifts every word's timestamp by its
segment's offset. One voice, two accents, exact word times. Three things keep the seams inaudible:
ElevenLabs **request stitching** (`previous_text`, `next_text`, `previous_request_ids`, so each segment
continues the prosody of the last instead of starting cold), **edge trimming** of every segment to a
40 ms pad with 12/20 ms fades and per-beat level matching, and **fewer switches** in the scripts
(enumerations in one span — see the prompt's "Fewer seams" rule). This is the same architecture as the
channel's `src/tts_bilingual.py`, in 200 lines and with an explicit marker instead of heuristics.

## Karaoke captions, think pauses, slower English

The narration runs at the bottom of every beat, sentence by sentence, and each word lights up when
it is spoken — Spanish from grey to ink, English (the `[[ ]]` spans) in bold blue. Times come from
the same word boundaries the cues use, so with ElevenLabs they are exact. `CAPTIONS=0` renders
without them. `{{pause:3}}` in a narration is three seconds of silence in the audio and a thinking
ring on screen (every quiz has one, right after the options are read). English segments are spoken
at `english_speed` (0.92 by default; ElevenLabs `voice_settings.speed`, with a silent fallback to 1.0
if a model refuses it). There is a short breath between beats, longer after a section card.

## Why the picture follows the voice

A beat says which words it animates on (a highlighted chip, the first word of a dialogue line,
the first cell of a table row, the correct quiz option). `lesson.marked_narration` inserts a
`<bookmark/>` before the first time the narration says each one; the scene waits for that bookmark
(`wait_until_bookmark`) using the ElevenLabs timings — no Whisper. If the narration never says a
cue word, `lesson.warnings()` tells the writer and the scene falls back to a proportional guess.

## The three lessons that ship (≈ 7½ min each, 28–31 beats, dialogue, 3 quizzes, recap)

`third-person-s` · `simple-vs-continuous` · `morning-phrasal-verbs`. Narration ≈ 4.5–5.0 k
characters each → about $0.45–0.50 of ElevenLabs per lesson per voice.

## Commands

```sh
# write a new lesson (OPENAI_API_KEY from ../../.env or ./.env)
python3 gen_script.py --topic "Past simple: verbos irregulares del día a día" --level A2 --minutes 7 --model gpt-4o

# audio for one lesson (ELEVENLABS_API_KEY from ../../.env or ./.env), Matilda by default
python3 gen_audio.py --lesson lessons/third-person-s.json
python3 gen_audio.py --lesson lessons/third-person-s.json --voices laura=VOICE_ID

# render one lesson
LESSON=lessons/third-person-s.json VOICE_DIR=audio/third-person-s/matilda manim -qm lesson_scene.py Lesson

# everything, for every lesson, one command
python3 batch_run.py --all --voices matilda=XrExE9yKIg1WjnnlVkGX          # 1080p30 by default
```

Manim on the Mac, once: `python3 -m venv .venv && .venv/bin/pip install "manim==0.21.0" "manim-voiceover==0.4.0"`
and `brew install pango ffmpeg`. The admin page finds `.venv/bin/manim` by itself.

Keys live in `english-ai-videos/.env` or in this folder's own `.env` (the admin page writes it,
mode 600, git-ignored). They are never printed. `audio/`, `renders/` and `media/` are outputs.

## Into a course (Learning Routes, WP-38)

The Rails side (`PROMPT_29_WP38_VIDEO_LESSONS_FROM_THE_STUDIO.md` in the Learning-routes repo) adds a
`video` block and an owner-token API. Once it is deployed and `studio.api_token` exists in the Rails
credentials, put the same token here as `LR_STUDIO_TOKEN` (and `LR_BASE_URL`) in `./.env` — the admin
page's «Entorno» panel does it — and the page's step 4 lists the courses, writes a script from a
step's title and description, and publishes the latest render into that step:

```sh
python3 publish.py routes
python3 publish.py publish --step <STEP_ID> --lesson third-person-s
```

## Adding a visual

`lesson.TYPES` + a `_validate_fields` branch + a `beat_<type>` method in `lesson_scene.py` + a line
in `prompts/lesson_script.md` so the writer knows it exists. Keep the measured-legibility rule:
text is wrapped and scaled to fit the stage, never clipped.

## Sandbox note

`gen_audio.py --offline` uses Piper voices through sherpa-onnx (`../tts-models/`) so the pipeline can
be exercised without a key. Those voices are for checking timing and layout; the product voice is
ElevenLabs.

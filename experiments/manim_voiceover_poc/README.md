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

## The look — English Unlimited on paper (or on the dark stage)

`lesson_scene.py` reads the colours from `assets/branding/english-unlimited/brand.json` →
`manim.themes` (see `theme.py`): **sand** (warm paper, the default), **stone** (cooler grey paper)
and **dark** (the ink stage). `THEME=dark` picks one for a render, else the lesson's `"theme"`, else
`manim.default_theme`; the dashboard's Manim page has a «Tema» dropdown. Every theme passes a
contrast test (text ≥ 4.5:1 on the ground and on cards, blue/green/red ≥ 3:1), yellow is only ever
a fill or a highlighter on paper, and the ground is never flat: a soft vignette and a faint grain,
generated once with numpy and used as the camera's background image. The Shorts read the same
brand file. The scene registers Fredoka Bold (chips, headings, English) and Manrope (Spanish, captions)
from `assets/fonts/`, never a system font. One grammar colour code in every lesson: subject blue,
auxiliary yellow, main verb green, error red; a `tags` label takes the colour of the role it
names. Sizes are cap heights at 1080p, for a phone: English chips 68 px, glosses 46, captions 42
(minimums 64 / 44 / 40); a long sentence breaks into rows instead of shrinking, a long dialogue
scrolls. Punctuation stays on its word (`seven.`). Every render ends on a silent 20 s card — the
logo, «Sigue aprendiendo» and two empty frames for YouTube's end-screen elements.

## The notebook page (STEP 63, design E)

Every beat is written on a landscape notebook page: paper a shade lighter than the ground, an ink
outline with a hard ink shadow, spiral rings on the left, and the part's name at the top in Fredoka
on the yellow marker (an updater on the clock, so it adds no time). The top bar stays above the page
and a small blue «learningroutes.com» pill sits under its dashes. The caption is a yellow sticky note,
bottom right, slightly turned, as wide as the beat's widest line and two lines at most. A table prints
every row from the first frame; each meaning waits under one shared grey blurred bar and comes into
focus on the yellow highlighter when the narration reaches it. A quiz reveals the answer with a green
hand-drawn circle and a tick, and strikes the wrong options in red.

## Grammar in motion — `transform`, `timeline`, `sort`

The camera eases ≈ 1.06× in on a transform morph, a sentence fix and a sort, and back on the next
beat; captions and the top bar (lesson title + one progress segment per `heading`, filling as the
part plays) are pinned to the frame. A transform that adds a word first marks the gap with a red
caret that pulses and then becomes the word; a transform whose `from` is the sentence already on
screen morphs from it. Sound effects (`sfx.py`, synthesised with numpy): a soft pop on chip drops
and sort landings, a whoosh on moves and camera pushes, a tick each second of a quiz pause — 22 dB
under the voice, 6 dB lower on a spoken word; `SFX=0` (or `batch_run.py --no-sfx`) turns them off.
The render's timeline JSON lists every effect played.

`transform` morphs one sentence into another (shared words glide, a moved word arcs over, a word
only in `from` turns red, shakes and falls, a word only in `to` drops in green); `timeline` draws
tenses as shapes on an axis with «ahora» at 0; `sort` pops each item up as it is said and flies it
into its bin; `syllables` shows a word in syllable chips, the stressed one big and yellow, with a dot
hopping across them as it is said. A quiz `{{pause}}` shows «Pausa y piénsalo» beside the thinking ring. The title may
be beat 2 or 3, so a lesson can open on the mistake. `lessons/demo-motion.json` shows all of it
in two minutes.

## Why the picture follows the voice

A beat says which words it animates on (a highlighted chip, the first word of a dialogue line,
the first cell of a table row, the correct quiz option). `lesson.marked_narration` inserts a
`<bookmark/>` before the first time the narration says each one; the scene waits for that bookmark
(`wait_until_bookmark`) using the ElevenLabs timings — no Whisper. If the narration never says a
cue word, `lesson.warnings()` tells the writer and the scene falls back to a proportional guess.
The motion types cue in order (two timeline labels that both start with «I» get two cues) and only
inside the English, and a `transform` waits until the narration has said `from`.

## The three lessons that ship (≈ 7½ min each, 28–31 beats, dialogue, 3 quizzes, recap)

`third-person-s` · `simple-vs-continuous` · `morning-phrasal-verbs`. Narration ≈ 4.5–5.0 k
characters each → about $0.45–0.50 of ElevenLabs per lesson per voice.

## How long a lesson runs

`lesson.estimate_minutes` is fitted on real renders, not guessed: every render writes its words,
beats, pause seconds and end card into `renders/ledger.jsonl`, and `batch_run.py` prints the refit
when it finishes. On 2026-10-13 that is n = 5 lessons as rendered (re-renders of the same content count once), ≈ 138 wpm everything included plus a fixed
0.75 s per beat (the scene's own fade and breath); residuals within ±32 s. With fewer than six
renders only the speaking rate is fitted — three points gave a negative cost per beat.

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

`lesson.TYPES` (+ `lesson.ORDERED` if its cues are English-only or repeat) + a `cue_words` branch + a `_validate_fields` branch + a `beat_<type>` method in `lesson_scene.py` + a line
in `prompts/lesson_script.md` so the writer knows it exists. Keep the measured-legibility rule:
text is wrapped and scaled to fit the stage, never clipped.

## Sandbox note

`gen_audio.py --offline` uses Piper voices through sherpa-onnx (`../tts-models/`) so the pipeline can
be exercised without a key. Those voices are for checking timing and layout; the product voice is
ElevenLabs.

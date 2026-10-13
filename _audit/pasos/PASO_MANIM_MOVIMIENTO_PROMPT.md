# Brief for Code — Manim lessons: brand, legibility and "grammar in motion"

## 0. Why

The owner: the long lessons must be more interactive and eye-catching, "so the
viewer stays because they want to learn, and it looks good". His reference is
**3Blue1Brown**: also Manim, and what holds people there is not text on cards.
It is **ideas that move**. Things transform in front of you, a question comes
before its answer, every concept has its own shape and colour, and you get
"pause and ponder" moments.

An audit of the current render (`renders/used-to-soler/20261008-144509…mp4`,
stills in `_audit/stills/manim_used_to.png`) found:

1. **Off brand.** The frames are off-white/grey with DejaVu Sans. The Shorts
   are English Unlimited v2 "Pegatina" (Fredoka, yellow `#F2D66B`, blue
   `#1B6FA8`, ink `#1C1812`). The two products look like two channels.
2. **Small text and empty frames.** Dialogue text sits around 20 px tall, and the
   table fills the top-left quarter. Most viewers watch on a phone.
3. **Text cards, not motion.** Almost every beat is "text appears, voice
   reads". Nothing transforms. The sentence `fix` swaps a chip; that is the
   only real motion.
4. **The punctuation chip bug.** The final "." becomes its own chip (`[·]`
   after "seven").
5. **A weak opening.** A left-aligned title card holds for 10 s, while the
   first 15 s decide retention.
6. **No end screen.** YouTube end-screen elements need the last 5–20 s.
7. **Wrong duration estimate.** `estimate_minutes` said 7.1 min for
   used-to-soler, and the render runs 5.95 min. Three renders in the ledger
   (third-person-s 7.09, morning-phrasal-verbs 7.06, used-to-soler 5.95 min)
   put the real spoken rate at 133–155 wpm, and the 0.04 min/beat term does
   not appear. The owner asked for ≥ 6 min. I have already lengthened the 15
   shortest lessons (each now has ≥ 847 words); see §5.

Constraints, unchanged: no new paid services, ElevenLabs and OpenAI only,
everything else local. No MoviePy. Flag any change to per-lesson API cost
(≈ $0.45–0.50 today).

## 1. Phase A — look and legibility (no new beat types)

- **Theme: dark, in brand colours.** A dark stage gives the 3b1b feel, and the
  ink is already ours:
  `BG #1C1812 · TEXT #FBF6EA · YELLOW #F2D66B · BLUE #6CB4EE (brand blue lifted for dark) · GREEN #7FD49B · RED #F28B82 · MUTED #A39B8C`.
  Put these tokens in `brand.json` under a `dark` key so the Shorts and Manim
  read one source.
- **Fonts:** Fredoka Bold for chips, headings and English; Manrope for the
  Spanish gloss and captions. Both are in `assets/fonts/`. Register them with
  `manimpango.register_font`; never rely on system fonts.
- **Grammar colour code, the same in every lesson.** Subject = blue,
  auxiliary = yellow, main verb = green, error = red. The existing
  `highlight` colours map onto these, and `tags` labels use the same colour as
  the role they name.
- **Sizes for a phone:** English chips ≥ 64 px cap height at 1080p, glosses
  ≥ 44 px, captions ≥ 40 px. Layouts should use about 80 % of the frame width
  and stay centred. That includes the table, which should be centred and
  scaled to fill the frame.
- **Punctuation stays attached to its word** (`seven.`), never as a chip of
  its own.
- **End screen:** a 20 s closing card after the last beat. It shows the brand
  logo, "Sigue aprendiendo", and two empty rectangles where YouTube places
  the end-screen elements. The card is silent, with music only if a local
  track already exists in the repo.
- **Estimate:** refit `estimate_minutes` against `renders/ledger.jsonl`
  (words, beats, pauses → real duration). State n honestly (n = 3), and print
  the fit when `batch_run` finishes so it improves with every render.

## 2. Phase B — three new beat types ("grammar in motion")

All three keep the cue discipline: the visual reacts when the narration
**says** the word. `lesson.cue_words`, `validate` and `warnings` learn each new
type.

### `transform` — a sentence becomes another sentence
```json
{"type":"transform","from":"Where you live?","to":"Where do you live?","gloss":"¿Dónde vives?","narration":"…"}
```
Chips of `from` are shown, then morph into `to`. Use Manim's
`TransformMatchingStrings` or your own matching by word, case-insensitive
and ignoring punctuation:
- words in both sentences glide to their new position (inversion: `You are` →
  `Are you`);
- words only in `from` turn red, shake once and fall away;
- words only in `to` drop in green.

**Cue:** the morph starts at the first word of `to` that is new or has
moved. If nothing is new (a pure reorder), the cue is the first word of `to`.
This one type replaces "show the error, then fix it" chains and teaches word
order visually, which is the hardest thing for Spanish speakers.

### `timeline` — tenses as shapes in time
```json
{"type":"timeline","events":[{"label":"I used to live in Paris","start":-8,"end":-3,"kind":"span"}],"narration":"…"}
```
- A horizontal axis from −10 to +10, with **ahora** at 0 as a vertical
  glowing line. "pasado" sits to the left and "futuro" to the right, both in
  muted Spanish.
- `kind`: `point` is a dot; `span` is a bar that grows from start to end;
  `repeat` is a row of dots that pop in one by one (a habit).
- Each event's label sits above its shape. The event draws when the
  narration says the first word of its label.
- Up to 3 events per beat.

Tenses become shapes: used to = a closed bar in the past; present perfect =
an arrow that reaches *ahora*; going to = a dot in the future with a dashed
line from now.

### `sort` — words fly into the right box
```json
{"type":"sort","bins":["make","do"],"items":[["coffee",0],["homework",1]],"narration":"…"}
```
- 2–3 labelled bins along the bottom and up to 8 items.
- Each item pops in at the centre when it is said, holds for about 0.3 s,
  then arcs into its bin.

Covers make/do, countable/uncountable, -ing/to, in/on/at.

### Also
- **Hook first.** `title` may be beat 2 or 3, so a lesson can open on a
  `transform` that shows the mistake in the first 5 seconds. Chapters and
  the poster must not assume beat 1 is the title.
- **Pause and ponder.** During a quiz `{{pause}}`, show "⏸ Pausa y piénsalo"
  beside the ring.

## 3. Acceptance — proof, not claims

1. `lessons_drafts/demo-motion.json` (8 beats, ≈ 1.5 min) exercises every new
   type. Once the schema accepts it, move it into `lessons/`. Generate its
   audio (≈ $0.10) and render it at 1080p.
2. Send stills to the owner: one per new beat type mid-motion, a quiz with the
   pause card, and the end screen. Include the duration, the cost, and
   `validate` / `warnings` = 0 / 0 for all 22 lessons.
3. Run a byte-level check that nothing outside `experiments/manim_voiceover_poc/`
   and `brand.json` changed. The Shorts pipeline must be untouched.
4. Commit in logical steps with the repo-local identity. No keys, `.env`,
   voice IDs or home paths.
5. **Stop there.** Once the owner approves the look, I rewrite lessons to use
   the new beats. Do not batch-render the 22 lessons before that: each one
   costs ≈ $0.50 in audio.

## 4. Not in this step
publish.py / Learning Routes, thumbnails, Shorts.

## 5. Content already changed (FYI, for the audio cache)
15 lessons gained a "real situation" section (dialogue, list, examples, tip)
before Practice, and their beat ids were renumbered. Two of them already had
audio: `comparativos-superlativos` and `used-to-soler`. Their beats after the
insertion point will regenerate (≈ $0.20 each) the next time they are
rendered. `third-person-s` b30 narration changed (cue fix, ≈ $0.02).

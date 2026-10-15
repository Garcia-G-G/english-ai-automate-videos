# STEP 58 — Build the "level" Shorts on the notebook that already works

## 0. Why now, and the evidence

The owner has asked for more Shorts of the how_do_you_say family about six times. Public
view counts on the English Unlimited channel, read on 2026-10-15:

| type | Shorts | views each | uploaded |
|---|---|---|---|
| how_do_you_say | 6 | 505 · 1.0K · 1.1K · 1.1K · 1.2K · 1.2K | Oct 13–14 |
| everything else uploaded Oct 8–14 | 9 | 68 · 82 · 122 · 126 · 131 · 132 · 317 · … | Oct 8–14 |
| vocabulary (all time) | 7 | 131 – 554 | Sep–Oct |

About 8× the rest, after fewer days online. The hashtags are not the cause: every type uses
the same twelve-tag template, and only four tags differ. Upload times and voice are the same.
What differs, seen frame by frame (`output/qa/hook_frames/sheet.jpg`):

1. **The whole puzzle is on screen at second 0.** All ten Spanish words, each with an emoji,
   on a notebook page. The viewer starts testing themselves before the voice says a word.
   `vocabulary` opens on an **empty** table and adds one row at a time.
2. **The title is the search phrase.** "¿Cómo se dice COMIDA en inglés?", plain A1.
3. **An open loop to the last row.** Ten blanks fill one by one, so leaving early leaves
   the list unfinished.

The three Shorts the owner showed as references (other channels) share point 1: a full
list on a notebook or table from the first frame.

**Rule for every new Short in this family:** the full list is visible from frame 1. Rows
light up and their answers are written in, one at a time.

## 1. Push first

`6a-layout` is three commits ahead of origin, none pushed (the VM has no GitHub
credentials). Push all three:
- `43ad720`: 40 new how_do_you_say lists, bv021–bv060, plus their topics entries. The test
  that pinned bv001–bv020 now accepts a contiguous, growing set.
- the commit that adds this STEP;
- the commit that adds it to the index.

Do not commit the other uncommitted changes in the tree (`main.py`, `src/length_spec.py`,
`src/video/vocabulary.py`, the queue deletions, and so on) unless they are yours. Report
them, and the owner decides.

## 2. What changes from STEP 49

Keep STEP 49 §2–§6 as written: schema, audio segment plans, registry and doors, duration
levers, proof. **Replace §1 (the visual).** No level meter and no single item card.
These become **modes of the how_do_you_say notebook renderer** (`src/video/how_do_you_say.py`):

| mode | at frame 1 the page shows | row reveal |
|---|---|---|
| `level_test` (lv001–lv100) | the 10 English words | Spanish meaning written in |
| `say_it_level` (sy001–sy100) | the 10 Spanish sentences | English written under the Spanish, on the same row |

- **Tiers:** two thin coloured rules across the page, after row 3 and after row 7. The
  bands are labelled in the margin: BÁSICO (green), INTERMEDIO (amber), EXPERTO (accent),
  using the brand v2 colours. When row 4 and row 8 start, that label pulses once while
  the fixed tier line plays (recorded once, cached; STEP 49 §3).
- **Verdict:** after row 10, keep the page and show a sticky note over its lower part:
  "3 → básico · 7 → intermedio · 10 → experto". Show it while `verdict` is spoken.
- **Fit:** `say_it_level` rows hold sentences, so a row may use two lines (Spanish above,
  English below). Measure every one of the 100 drafts with `length_spec` at the real widths.
  Do not go below the brand minimum font size. Send me the list of drafts that do not fit,
  and I will shorten them.
- The current row is highlighted, with the same marker and pencil as how_do_you_say.
  `how_do_you_say` itself must render **byte-identically** before and after; a layout pin
  test proves it.

## 3. Order and stop point

Build `level_test` and `say_it_level` in this step (one engine, two modes). Move their
topic files and drafts into `content/topics/` and `content/queue/`, with
`footage_level_family.json` as in STEP 49b.

Render **one of each**: lv001 cocina and sy001 restaurante. Then **stop** for the owner's
eye and ear. `pronounce_level` comes after that approval, as a third mode.

Before cloning the segment plan, find where bv004's 3.4 s `dead_air` came from (STEP 49 §3).

## 4. Constraints

Only OpenAI and ElevenLabs are paid. Everything else is local and free: ffmpeg, PIL,
Python, Whisper. No MoviePy. The ceiling is $0.30 per Short; how_do_you_say costs
$0.01–0.09 today, so report the real cost per Short of each new mode. No keys, `.env`,
voice IDs or home paths in commits. Commit messages carry no attribution lines.

## 5. Report back

- Push confirmation for the three commits, plus the list of uncommitted changes you did not author.
- Stills of lv001 and sy001 → `_audit/stills/`:
  - frame 0, which must show all 10 rows;
  - row 4 being revealed, with the INTERMEDIO pulse;
  - row 10 revealed;
  - the verdict note.
- For each render: final QA, the duration, the number of characters and the cost.
- The `length_spec` report over lv001–lv100 and sy001–sy100.
- Test counts: pass / fail, naming any failure that is not yours.

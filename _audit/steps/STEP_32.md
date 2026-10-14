# STEP 32 — The pronunciation layout is ten coordinates, and the slot is
# smaller than one line of the font it was built for

Branch `6a-layout`, after VOCAB. One step.

---

## First, what I checked before writing this

The frame you saw came from a `business` topic that reached the pronunciation
prompt — the bug `e366f7f` fixed. So the honest question was whether this
renderer is still broken now that it draws from `content/topics/pronunciation.json`.

**It is, on 33 of the 56 words in that file.** And the reason is not what the
frame suggested.

## The defect

`PRON_TITLE_Y = 250`, `PRON_TRANSLATION_Y = 430`. The word gets a 180px slot.

```
_word_font_size buckets on character count (pronunciation.py:23-31):
  160px  (<=8 chars)   ONE line = 194px   ->  250..444   INVADES the translation
  120px  (9-12 chars)  ONE line = 146px   ->  250..396   clear
   88px  (>=13 chars)  ONE line = 108px   ->  250..358   clear
```

**A single line at the largest bucket does not fit the slot.** Not a long word,
not a wrapped word — one line, always, by 14px.

That bucket holds 25 of the 56 words: `knight`, `beach`, `sheet`, `thought` —
the short ones the type exists for. Eight more in the 88px bucket collide by
wrapping to two or three lines. 33 of 56, and **the worst case is the shortest
word**, which is the reverse of what the broken frame implied.

## What is NOT broken — do not "fix" these

I traced the four phase windows (`pronunciation.py:59-61` and each draw
condition) before counting:

```
A  0    .. 0.25   word, translation, question
B  0.25 .. 0.50   + mistake (650 / 720)
C  0.50 .. 0.80   mistake fading, phonetic at 1000 / 1080
D  0.80 .. end    phonetic at 650 / 750, tip at 900
```

- The mistake block and the phonetic **never share the screen at the same Y**.
  The phonetic sits at 1080 while the mistake is up, and only moves to 750
  after the mistake's alpha has reached 0. My first pass reported a 74px
  collision between them; that was a false positive from ignoring the phases.
- The phonetic never reaches the watermark on this content: 0 of 56.
- Only 2 of 56 have a phonetic long enough to reach the tip at 900.

On real pronunciation content there is exactly **one** live collision:
`word × translation`, and `word × question` when the word wraps.

## The contract

1. **Stack, do not place.** Each element's Y comes from the measured bottom of
   the one above it plus a gap. The ten `PRON_*_Y` constants encode a layout
   that assumed every element is one line of a size nobody measured; replacing
   the numbers with different numbers reproduces the bug at a different size.

2. **The word's size is a fit, not a bucket.** `_word_font_size` guesses from
   `len(word)`, which cannot know the rendered height and is what put 194px in
   a 180px slot. It should fit against the slot the stack actually gives it —
   `fit_text_font` already does exactly this and now has a proven caller in
   `vocabulary._draw_cell`.

3. **The column has a floor, and it is `watermark_top()`, not
   `SAFE_AREA_BOTTOM`.** This renderer budgets against nothing today. Of the
   six, only `quiz.py:847` and `true_false.py:601` use the mark. Take the
   floor here while the layout is being rebuilt — it is the same edit, and
   doing it later means touching this stack twice. It does not fire on today's
   content; it is the guard for the day a phonetic runs three lines.

4. **One element, one position.** The phonetic has two hardcoded Y pairs
   (1000/1080 in phase C, 650/750 in phase D) for the same block. Under a
   stack its position follows from what is above it and visible, and the two
   constants collapse into one rule.

5. **Nothing silently shrinks to illegibility.** State a floor for the word's
   font and report when a word reaches it, the way `fit_text_font` already
   logs.

## Proof required

- A test that measures **what reached the canvas**, as the vocabulary one does
  — capture the draw calls, run the real renderer, assert no two blocks visible
  in the same phase overlap, and assert nothing crosses `watermark_top()`.
  Drive it over all 56 words in `content/topics/pronunciation.json`, not one
  fixture: the defect is content-dependent and 23 of the 56 pass today.
- It must fail against the current tree on the 33.
- Two extracted frames: one short word (`knight`, the 160px bucket, worst case)
  and one long (`advertisement (British vs American)`), each in phase A and
  phase D.
- Report the font each of the 56 words resolved to and how many reached the
  floor.

## Out of scope

Every other renderer. The `_word_font_size` buckets may go, but nothing about
which words exist, the phase timings, or the script prompt.

## Cost

$0.00. All 56 words are on disk and the fonts are local. No render.

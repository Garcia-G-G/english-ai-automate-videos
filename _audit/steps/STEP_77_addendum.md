# STEP 77 — addendum after §2 (Claude's review, 22 Oct)

Read this before resuming at §3. It amends STEP 77; everything not mentioned here stands.

## A. The §2 decision: x264 `medium` (commit it as §2b)

- In `src/video/compositor.py`, change the default `preset` from `slow` to `medium`. Keep the CRF,
  `X264_PARAMS` and the BT.709 tags from STEP 75 exactly as they are. `ultrafast` stays for `--fast` drafts.
- Why: at a fixed CRF the preset trades file size against encoder CPU. It does not change colour.
  Your own numbers give −20 % encoder CPU for +3 % size. The platforms re-encode anyway.
- New speed target, replacing "≤ 60 s": an 80 s Short at **≤ 75 s estimated idle wall time**
  (CPU seconds ÷ workers, as in `s2_speed.md`). If the estimate lands between 75 and 90 s, note it
  and continue. Do not spend more sections on speed: 280 s → ~70 s is the win.
- Proof for §2b: re-run the same 900-frame encode-only A/B and one whole `how_do_you_say`
  render. Append both to `_audit/stills/STEP77/s2_speed.md`, along with the blue ΔE check from
  STEP 75 on one frame (it must stay ≤ 1.0).
- Before §2b, run the full suite once (it was not run after §2) and report pass/skip/xfail/fail.
  Any new failure stops the STEP.

## B. Fixes from the stills review (fold them into §3, with a test each where possible)

Reviewed: `s1_choose.png`, `s1_hdys_crop.png`, `s2_hdys_writing.png`.

1. **The ✓ touches what it marks.** In choose_level, the tick overlaps the circle around the right
   option (rows 1, 3, 5). In how_do_you_say, it sits glued to the word ("family✓"). Leave a
   gap of at least 14 px at 1080 width between the ink box of the word or circle and the tick. Test:
   the tick's bbox does not intersect the word's or circle's bbox in any mode that draws one.
2. **The pencil is clipped.** In `s1_choose.png` the pencil is cut off at the page's right edge
   (around x = 1035). The pencil is drawn after the tilt (§2), so it must not be clipped to the
   page; clip it to the frame only. Test: render the choose_level frame with the pencil on
   row 6, and check that the pencil sprite's alpha is fully inside the composited frame and not
   cut at the page edge.
3. **A hard diagonal seam in the background.** It appears at the top of `s1_choose.png`
   (y ≈ 80–130, blue against pink) and at the bottom of `s2_hdys_writing.png` (y ≈ 1700–1770).
   If this is the edge of a rotated or offset background layer showing through, fix it: the
   background must cover the full 1080×1920 on every frame, with no visible edge. If it really is
   part of the chosen background art, say so with the background's file name and leave it.
4. **The URL sits in the caption zone.** The URL "learningroutes.com" is at y ≈ 1575. TikTok, Reels
   and Shorts cover roughly the bottom 22 % with captions and buttons. When the STEP reaches
   safe zones, move it into the safe area or onto the page footer, and assert this in the
   safe-zone test.
5. Keep "Verdadero o falso (uno)" hidden in the panel. It is superseded by true_false_level,
   which now has 40 scripts.

## C. New final section §9: queue the 156 level scripts

Today's "no queued script left" failures come from these scripts. They are in `content/drafts/`
and their four types have no queue folder. They are queued only at the end, so that their first
renders already use the full new design.

- Create `content/queue/{choose_level,fill_level,true_false_level,phrases_level}/`.
- For each `content/drafts/<type>/*.json` with id `ec|fc|tf|vf 002–040` (and the existing 001s if
  they are not yet rendered), build `full_script` from the script itself, the same way the
  generator does for that type. Do not reword any field. Validate it with `validate_script` and
  write it to the queue folder. Leave the draft in place.
- Report the count per type. Then render **one** Short per new type (4 in total, ≤ $0.30 each,
  under $1.20 overall) as the STEP's final proof. Put the four MP4s and one still each under
  `_audit/stills/STEP77/`. Claude reviews them; Garcia does not need to listen to them.
- The panel queue moves (`content/queue/_done/…`) that come from Garcia's own renders: commit
  them in §9 as `chore: queue moves from renders`.

Same rules as always: one commit per section with its tests, push each one, stop on any failure,
no attribution lines.

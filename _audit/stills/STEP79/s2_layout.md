# STEP 79 §2 — layout

1. **The page**: centred, x −5.85…5.85 (82 % of the frame, inside 90 % title-safe), now down to
   y −2.2 to leave the band under it. The **header row** (lesson title, progress, site badge)
   sits at y 3.33, inside title-safe (it was 3.62, outside): title at the page's left edge, badge
   at its right edge, progress between them. The review's «left 55 %» did not match the 19 Oct
   frames I measured (the page spanned ~8–92 %); what made frames lopsided was the 1.06× camera
   push. It is now 1.03× and sideways only, so the page never runs into the header row or the band.
2. **Captions as a band**: up to 2 centred lines under the page, on the sand, 42 px as before.
   `lesson.caption_chunks`: sentences first, then their clauses (, ; : —) put back together
   while they fit, then the longest pause in the word times (plus a small preference for the
   breath before «y», «que», «pero», «because»…). Never inside an `[[English]]` span, never a lone
   word on a line, and a one-word page joins its neighbour. English stays blue and bold.
   The review's two fragments: «Una frase que se oye / muchísimo: She did a mistake.» and
   «Un error que suena completamente / normal en tu cabeza» | «y completamente raro en la del otro.».
3. **Collisions**: in stills mode every still records its text boxes as the viewer sees them
   (camera push undone) and `lesson.layout_problems` checks them: header texts in the header row,
   captions in the band, everything else inside the page as drawn, the page itself off the band
   and the header row, and no two texts overlapping. First run over 22 lessons: 7 problems in 3
   beats (a dialogue bubble taller than the page covered the page title; two 3-row sentences put
   their gloss under the page). Fixed: a bubble is laid out wider before it shrinks, and a
   sentence block is scaled to the page only when it does not fit. Dialogue that scrolls fades
   out what would leave the page before the rest moves up. **Final run: 0 problems in 22
   lessons, 760 stills** (`s2/index.md`, `s2/<lesson>/problems.txt`).
4. **English in blue everywhere**: list items, recaps and tips colour the English by
   `lesson.english_runs`: runs of the lesson's own English vocabulary (every word inside a
   `[[ ]]` of its narrations), cut at punctuation, Spanish-shared words trimmed off the edges.
   Words a lesson never says in English stay ink (make-vs-do: «make a cake» → «make» blue,
   «a cake» ink).

The STEP 63/69 sticky-note tests were replaced by band, header-row and page tests.

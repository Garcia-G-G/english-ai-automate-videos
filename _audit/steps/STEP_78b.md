# STEP 78b — Series polish from Claude's review, plus housekeeping

A short STEP. The lessons stay STEP 79.

Same rules as always:
- One commit per section with its tests; push each one.
- Run the full suite before every commit. On a failure, stop and report.
- No attribution lines.
- TTS cap: $0.30 per video, $0.50 total for this STEP.
- Proofs go to `_audit/stills/STEP78b/`. Claude reviews them.

Already done by Claude in commit 3a45a8f: 26 poster `hook_text`s gave the answer away at
frame 0 ("DESPITE OF → DESPITE / IN SPITE OF"). They now only ask the question, for example
"¿Está bien decir «DESPITE OF»?". The change is in both the drafts and the queue, and the 54 files
pass `validate_series`. Re-render nothing for this beyond the hc_p019 proof below.

## §1 — Series polish (reviewed: the 4 sheets, frame 0 of each, and frames at 62/80/88 % of each MP4)

1. **mensajes: the screen goes still and half empty.**
   - From the rule sticky to the challenge, about 16 s in hc_m001, nothing moves while the voice
     gives more examples. Meanwhile the lower half of the screen is empty.
   - Every `[[English]]` phrase spoken after the correction beat gets its own example card with a
     green tick, stacked under the rule sticky. Each card enters on the word time of its phrase:
     "She's 30 ✓", "My dad is 60 ✓".
   - The stack fills the empty lower area and stays out of the bottom 22 %. If it doesn't fit,
     the oldest card fades out.
2. **escena: frame 0 is an almost empty brown screen.** That frame is the feed thumbnail. At frame 0, show
   - `take1` as the yellow subtitle, not struck yet,
   - a small pill «¿Ves el error?»,
   - the clapper («TOMA 1»), as now.
3. **poster: bad line breaks.** "DESPITE / IN" | "SPITE OF" splits a phrase in two.
   - Prefer breaks right after ` / `, ` → `, ` = `, ` ≠ ` and ` — `, then balance the line lengths.
   - Never leave a separator at the start of a line, and never leave a lone short word.
   - Test it on `big_wrong` and `big_right` for all 27 posters, and add a sheet of the 54 laid-out
     blocks.
4. **comic: frame 0 says «¿Tú también dices esto?» with nothing for "esto" to point to.** At
   frame 0, show the quiz prompt card and the three options, static, under the hook card. The
   pop animation can play from that visible state.
5. **A rule for all four styles: no still stretch longer than 4.0 s.** Measure it as consecutive
   frames whose mean absolute difference stays below a small threshold. Small living motion counts:
   - a breathing Bubi,
   - a blinking cursor,
   - grain,
   - a slow push-in.

   Add this to the quality gate, and report the longest still stretch for each proof.

Proofs, from cached audio at $0: re-render **hc_m001** and **hc_p019**.

Then widen the coverage with **four new full renders**, one per style and none of them a proof
script already: **hc_m010**, **hc_e001**, **hc_p002** and **hc_c019**. They must cover all three
levels; if any of these IDs has the wrong level for that, pick the next ID of the same style that
does. They cost about $0.10 each.

For each render, save the MP4, a 5-frame sheet and frame 0. All of them must pass the gate.

## §2 — Housekeeping

1. **The 7 queued scripts whose topic was already produced.** This is Claude's decision: move them
   to `content/queue/_skipped/` with a `README.md` that lists each file and why it was skipped. Don't
   delete them. Then the guard has nothing left to block.
2. **The Inter licence.** Replace `assets/fonts/OFL-Inter.txt` with the exact `LICENSE.txt` from
   Inter's official GitHub repository (rsms/inter), matching the version of the vendored font files.
   Note the source URL in the commit message.
3. **One real render from the panel.** Start the panel's own server on a spare port and trigger
   «Hecho con Claude» through the same HTTP route the button calls. Let it render, gate and file one
   script the normal way, on a script not already rendered (≤ $0.15). Report the route, the output
   path and the gate result, then stop that server. Don't touch Garcia's running panel.

## Report

Give Claude:
- the commits;
- the suite totals;
- TTS per render and in total;
- the longest still stretch per proof;
- the paths;
- the panel route test;
- anything not verified.

# STEP 85b — Thumbnails: natural, chosen per video, built into the end-to-end. Run this BEFORE STEP 85.

Garcia:

> hay que optimizar al máximo las miniaturas … agregarlo al end-to-end de los vídeos, las miniaturas tienen que verse naturales, según el vídeo y bien.

## What we have today

Claude read the code on 14 Nov:
- **Shorts:**
  - No Short gets a thumbnail from us. YouTube and Facebook pick a frame on their own.
  - `uploader.set_thumbnail()` exists but only `manim_studio.py` (lessons) calls it.
  - No log shows it ever ran.
- **The panel's thumbnails** (`src/thumbnails.py`) are a 112×200 JPEG grabbed by ffmpeg at 1.5 s from the compressed MP4.
  - They are blurry on the Mac's screen.
  - They are made lazily, while a page draws.
  - They are often mid-animation.

## What the platforms allow (Claude checked on 14 Nov 2026)

**YouTube:**
- The Data API reference (updated 12 Nov 2026) says `thumbnails.set` works «for a video, including YouTube Shorts».
  - It must be called after `processingDetails.processingStatus == succeeded`.
  - The limit is 50 MB, and it costs about 50 quota units.
- Custom Shorts thumbnails rolled out in Studio from 25 Jul 2026. Sources disagree on who gets them: Partner Program members only, or any verified channel. The channel has about 126 subscribers, so **it may be refused with 403. Nobody has confirmed either way.** This STEP finds out once, on a real upload, and remembers the answer.
- In the Shorts swipe feed the video autoplays and no thumbnail shows. **Frame 0 is still what matters there,** and it stays as designed in STEP 82.
- The thumbnail shows in search, on the channel's Shorts tab, on hashtag pages and when a Short is shared.

**Facebook:**
- Reels publishing has no cover parameter.
- `POST /{video_id}/thumbnails` with `source` (the image) and `is_preferred=true` sets a custom thumbnail on a Page video, up to 10 MB, ideally in the video's aspect ratio.

## Garcia's rules for this STEP

- **«Natural»:** every Short thumbnail is a real frame of that video. No AI-generated image, no added arrows, faces or text that isn't in the video.
- **«Según el vídeo»:** the frame is chosen by a per-format rule and checked by measurements, not taken at a fixed second.
- **«Bien»:** it is sharp, steady (never mid-animation), readable at small size, and drawn losslessly where we can.
- **«End-to-end»:** it is made at render time and shown in Revisar. Garcia can pick another candidate there. It is uploaded with the video, and its result is logged.

Rules, as always:
- One commit per section with its tests. Push each one.
- Run the suite with `VIDEO_RENDER_WORKERS=2` and no pytest parallelism. Stop on failure.
- No attribution lines.
- **$0.** Make no paid call. Thumbnails cost nothing: they are frames and local images. YouTube quota is free.
- Tests mock every HTTP layer.
- Snapshot `.tokens` before any change to the uploaders.

## Skills — use these explicitly (Garcia's instruction)

Before §0, say which of these you have. Invoke each one at the step named below. If one is missing, say so in the report and follow its intent by hand.

**Every section:**
- `agent-protocols:planning-and-task-breakdown` — at the start of the STEP.
- `agent-protocols:incremental-implementation` — while building each section.
- `mattpocock-skills:tdd` — write the failing test first, for every rule and every metric.
- `mattpocock-skills:diagnosing-bugs` — whenever a test or a render fails, before changing code.
- `agent-protocols:code-review-and-quality` — on your own diff before each commit.
- `agent-protocols:git-workflow-and-versioning` — for each commit and push.

**This STEP:**
- §1 and §2, choosing and checking the frame:
  - `design:design-critique` — on every contact sheet, before you hand it over;
  - `hzblj-skills:ui-typography` — readability at small size.
- §3, the 16:9 thumbnails:
  - `vectorlab-ux-skills:typography`;
  - `design:accessibility-review` — text contrast;
  - `vectorlab-ux-skills:anti-slop` — no clickbait.
- §4, upload:
  - `agent-protocols:api-and-interface-design`;
  - `agent-protocols:security-and-hardening` — tokens.
- §5, the panel:
  - `agent-protocols:performance-optimization`;
  - `audit-suite:audit-as-perf-eng`.

## §0 — One module: `src/thumbs/`

It replaces `src/thumbnails.py`. Keep its public `ensure_thumbnail()` working for the Streamlit panel until STEP 88.

For every artifact it writes, next to the sidecar, a folder `thumb/` with:
- `thumb.jpg` — what gets uploaded;
- `cands/` — 3 candidates;
- `thumb.json` — which candidate was chosen, the metrics, and why.

The sidecar keeps `thumbnail: {chosen, metrics, platforms: {youtube: …, facebook: …}}`. The move helpers carry the `thumb/` folder through pending → approved → uploaded. This replaces the old cache-by-stem trick; keep a fallback that reads the old cache for videos made before this STEP.

## §1 — Choosing the frame, per format ("según el vídeo")

Each format declares a **moment rule**. The renderer reports the time stamps it already knows: the beats, reveals, item onsets and the outro start.

| Format | The moment | Why |
|---|---|---|
| `how_do_you_say` (Tablero) | Right after the **3rd reveal settles**: 3 tiles done (blue, English in yellow, with `pron`), the 4th active, the rest blank, counter «3/10», Bubi `wow` | Shows the answer style and still leaves 7 to find out |
| `how_do_you_say` (notebook control) | The same moment in the notebook look | Same reason |
| `phrases_level` / vida real | The Spanish phrase shown, English **not yet** revealed | The question is the hook |
| `level_test`, `say_it_level`, grammar types | The first question on screen, with its options, before any answer | The same |
| Series (comic, mensajes, escena, poster) | Frame 0 as designed in STEP 78b (it was built to be the thumbnail) | Already designed |
| Lessons and compilations (16:9) | See §3 | — |

**Candidates.** For each video, make 3:
- **A:** the format's moment;
- **B:** frame 0;
- **C:** the 6th reveal or the second question, whichever the format has.

**A** is the default. Garcia can switch to another candidate in Revisar (§5).

**Lossless.** For every format drawn by our PIL kits (Tablero, notebook, series), draw the chosen moment **directly** with the kit's stills mode at 1080×1920 as PNG. Add a `draw_frame(t)` to each kit if it doesn't have one. Never grab from the compressed MP4 for these. For anything else (stock-footage backgrounds, Manim), extract from the master before the final encode if it's kept; otherwise use `ffmpeg -ss <t> -accurate_seek` from the MP4, scaled with lanczos.

## §2 — Checking the frame ("bien")

Every candidate gets these measurements, stored in `thumb.json`:

| Check | Rule | Fail if |
|---|---|---|
| **Steady** | Mean absolute difference vs the frames at t±0.12 s | > threshold. Then slide forward in 40 ms steps up to 0.6 s for the steadiest frame, and record the shift |
| **Sharp** | Variance of the Laplacian on the text area | Below a per-format threshold, calibrated on 10 good frames |
| **Not dark or blank** | Mean luminance and edge density | Out of range |
| **Nothing cut** | Every text box the kit drew for that frame is fully inside 1080×1920 and inside the safe zone | Any box crosses it |
| **Readable small** | Downscale to 180×320. The topic chip and at least one tile's text keep a contrast ≥ 4.5:1 against their fill, and an x-height ≥ 7 px | Either fails |

A candidate that fails is replaced by the next steadiest frame inside its window. If no frame in the window passes, the next candidate becomes the default, and the reason goes in `thumb.json`.

**Encoding:**
- `thumb.jpg` at 1080×1920, sRGB, quality 92, 4:4:4 chroma (crisp text), progressive, under 2 MB. If it's over, lower the quality in steps down to 86, then go to 4:2:0.
- Strip the metadata.

**Test fixtures:**
- a mid-flip Tablero frame must be rejected;
- the settled frame 3 tiles later must pass;
- a black transition frame must be rejected.

## §3 — The 16:9 thumbnails (lessons and the STEP 81 §4 compilations): designed, but honest

There is one template, 1280×720:
- the **real frame** of the lesson's first `sentence` beat, or of the compilation's best video, on the right, as a 9:16 or 16:9 card with the ink outline;
- on the left, **at most 4 words** in Fredoka Bold, white on the topic family's gradient, with one word highlighted in yellow — the same words as the title's hook;
- Bubi in the matching expression, bottom left;
- the small `learningroutes.com` mark.

What it must not have:
- red arrows, shocked faces, «😱», or words the video doesn't say;
- text in the bottom-right 220×70 px (YouTube's duration badge).

Checks:
- readable at 320×180, with the same contrast and x-height rules as §2;
- the same template for every lesson, so the channel's long-video shelf looks like a set.

This replaces STEP 79 §4's thumbnail. Re-make the existing lessons' thumbnails from their renders, at $0.

## §4 — Upload, with the answer remembered

**YouTube:**
1. After a successful upload, poll `videos.list(part=processingDetails)` with backoff until processing has succeeded, up to 30 minutes. Do it in the background job, never blocking the panel.
2. Then call `thumbnails.set` with `thumb.jpg`.
3. Record the result in the sidecar and the ledger: `ok`, `forbidden_shorts` (403 on a vertical video), `forbidden_channel` (403 on a 16:9 video, meaning the channel isn't verified), `rate_limited`, or `error`, with the message.
4. **The capability memo** goes in `output/state/capabilities.json`: `{"youtube_shorts_custom_thumbnail": {"state": "unknown|yes|no", "checked": "<date>", "reason": "..."}}`.
   - The first Short upload after this STEP is the probe.
   - If the answer is `no`, stop calling it for Shorts, and re-check once every 30 days on one upload.
   - If it's `yes`, call it on every Short.
   - The same goes for 16:9 videos (`youtube_custom_thumbnail`).
   - The panel shows the state in one Spanish line, for example: «YouTube aún no deja poner miniatura a los Shorts de este canal (se vuelve a probar el 14 dic).»

**Facebook:** after the reel is published, `POST /{video_id}/thumbnails` with `source=thumb.jpg` and `is_preferred=true`. Record the result the same way. If the token lacks permission, record it and keep the reel.

**Never block or undo an upload** because the thumbnail failed. The video always stays published.

**Quota:** about 1,600 units per upload plus about 50 per thumbnail, at most 4 a day. Report the daily total against the 10,000 limit.

## §5 — In the panel (both panels until STEP 88, then only the new one)

- **Revisar** shows a «Miniatura» row under the frame strip.
  - It holds the 3 candidates at 90×160, with the chosen one outlined.
  - Clicking another one switches `thumb.jpg` at once, with no re-render.
  - It shows the capability line from §4.
- **Every thumbnail in the panel** (Inicio, Cola, Biblioteca, Revisar, the agenda) comes from the same chosen frame, as **WebP**:
  - 270×480 and 540×960 (`srcset` 2×), quality 82;
  - plus a 24-byte blurred placeholder (base64) so nothing pops in.
  - These are made at render time, never while a page draws.
  - In STEP 85's app: `loading="lazy"`, `decoding="async"`, fixed size boxes, no layout shift.
- **Backfill.** Make `thumb/` for every video on disk, made from the MP4 with the §2 checks, in one background run. Report the time it took.

## §6 — Changing thumbnails of published videos (only with Garcia's click)

- **«Miniaturas mejores para lo publicado»** lists the published videos whose new thumbnail differs from what the platforms show today, with before and after.
  - Put the 20 best-performing first.
  - Nothing is sent until Garcia ticks videos and clicks «Aplicar».
  - On YouTube it only appears if the capability memo says `yes`.
- **The quota guard:** at most 40 changes a day.

## §7 — Proofs ($0)

Save to `_audit/stills/STEP85b/`:
- **One contact sheet per format** for the last 10 videos of that format: each row shows the old ffmpeg 1.5 s still, then candidates A, B and C, with the chosen one marked and its metrics printed small.
- **The 180×320 sheet** of the same thumbnails: what search and the channel grid show.
- **The three fixture cases from §2,** with their measurements.
- **The 16:9 template** on 2 lessons.
- **The first real upload's thumbnail result.** It comes from Garcia's normal upload, not from you. If none happened during the STEP, say so.

## Report

Give Claude:
- the commits;
- the suite totals;
- the skills used per section;
- the moment rule per format;
- the thresholds you calibrated, and on what;
- the backfill time and file sizes;
- the capability memo's states;
- the quota per day;
- the proof paths;
- $ spent, which must be $0;
- anything not verified.

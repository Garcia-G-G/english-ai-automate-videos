# STEP 65 — Upload guards: no empty titles, no second copy of a topic, the script's own title

Run after STEP 61 Part A (it touches the same upload path), before Part B.

## What happened (public data, read 2026-10-16 15:40 UTC)

On 2026-10-15 23:13 PT, `cómo_se_dice_20261015_175246` was uploaded as **`8yA7dbOZeUY`**
with the title **«¿Cómo se dice  en inglés?»** (empty slot, double space). Its
description is the generic fallback «Sígueme para más tips de inglés 🦊». It has 2 views.

- It is **bv010 la ciudad**, the same script as `jKbncpSxnuY` (uploaded 25 minutes
  earlier as «¿Cómo se dicen los sitios de la CIUDAD en inglés?»).
- It is a 46 s render. The other one is 74 s.
- Its sidecar JSON has `gate: null`; I could not see a QA verdict.
- `output/audio/how_do_you_say/cómo_se_dice_20261015_175246.json` does carry
  `video_title` and `theme: "la ciudad"`, yet the uploaded title is empty. So the upload
  built its metadata from something other than the script.

Two more uploads lost the script's own metadata:
- `RRbZ-y2ohGY` (say_it_level) went up as «Dilo en inglés: 10 frases, de fácil a experto»,
  with no theme. Its description is the «Sígueme…» fallback.
- The level_test uploads have titles that are not the scripts' `video_title`.

## Fix

1. **Find the path** that produced the empty title and the fallback description, and
   say which one it was (the Review → Upload path, the batch, or the scheduler).
2. **The script's own `video_title` and `video_description` win** whenever they exist.
   Generated titles and the fallback description are only for scripts that have none.
3. **Refuse an upload** (a guard in `upload_guard.decide`, so every door gets it) when:
   - the title has an empty slot: two spaces in a row, «se dice  en», `{`, or "None";
   - the description is only the fallback CTA;
   - **another video of the same `_meta.topic_id` is already published**. Show «Ya hay
     un vídeo de bv010 (la ciudad) subido: {url}». A checkbox «Subir otra versión de
     todos modos» overrides it, and the override is logged.
4. **No upload without a QA verdict.** If the sidecar has `gate` null or missing, the
   Upload page shows «Sin revisión automática» and the button stays disabled until the
   gate runs.
5. **Tests:**
   - the empty-title case;
   - the duplicate topic_id case, with and without the override;
   - a level_test script uploads with its own `video_title`;
   - `gate: null` is refused.

Do not touch the published video. The owner decides what to do with `8yA7dbOZeUY` in
YouTube Studio.

## Constraints

No paid calls. No keys, `.env`, voice IDs or home paths in commits. Commit messages carry
no attribution lines. Do not commit the other session's uncommitted files.

## Report back

- The commit, pushed.
- Which path produced the empty title.
- The tests.
- A screenshot of the Upload page refusing a duplicate.

# STEP 56 — Upload the long lessons to YouTube from the dashboard

## What the owner asked (2026-10-14)
"An upload part for the big videos too, with an automatic name, description and #."
The long Manim lessons are approved (voice v4, pace 0.92, 7–9 min). Today the Manim page
can only publish to the course platform (publish.py); YouTube upload exists for Shorts only.

## What already exists — reuse it, do not build a second uploader
- `src/uploader.py` `YouTubeUploader.upload_video`: resumable upload, OAuth, privacy from
  `PLATFORM_PRIVACY` (youtube = public), category Education, `selfDeclaredMadeForKids:false`.
  It **always adds `#Shorts`** to the title — a long lesson must not get it.
- `src/publication_log.py` ledger + `src/upload_guard.py` (no double publish; uploads only on
  a click, never unattended — keep that).
- Every render already has beside it: `<name>.mp4`, `.jpg` (poster), `.srt` (subtitles) and
  `.chapters.txt` (YouTube chapter list, «0:00 Introducción …»). The lesson JSON has `title`,
  `kicker`, `level`, and every `heading` beat.

## 1. Metadata, generated from the lesson itself (free, no API)
`manim_studio.youtube_metadata(lesson, render) -> {title, description, tags, hashtags}`:
- **title** ≤ 100 chars, from the lesson title + a learner hook, e.g.
  «Make y do: dos verbos, una confusión | Inglés A2–B1». No `#Shorts`.
- **description**, in this order: 2-sentence summary written from `kicker` + the first beats;
  «En esta lección:» + 3–5 bullets taken from the `heading` beats; the chapter list exactly
  as in `.chapters.txt` (first line must be 0:00 or YouTube ignores them); one CTA line
  («Suscríbete: una lección nueva cada semana»); then 3–5 hashtags.
- **hashtags/tags**: from a fixed set per lesson type (#AprenderInglés #InglésFácil
  #GramáticaInglesa + 1–2 specific to the lesson, e.g. #MakeVsDo), ≤ 5 in the description;
  `tags` array up to 15, Spanish + English keywords.
- Preview it all on the page in editable fields BEFORE upload; what the owner edits is what
  is sent. Save the final text beside the render as `<name>.youtube.json`.
- Unit tests: chapters first line 0:00, title ≤ 100, no `#Shorts`, ≤ 5 hashtags in the
  description, no duplicated hashtag block (the old Shorts bug).

## 2. Uploader changes
- `upload_video(..., shorts: bool = True)`; the Manim page passes `shorts=False`, which skips
  the `#Shorts` title rule. Shorts behaviour byte-identical (test).
- After the upload succeeds: set the thumbnail from the `.jpg` (`thumbnails.set`; if the
  channel is not allowed custom thumbnails, log it and continue — never fail the upload).
- Subtitles: upload the `.srt` as Spanish captions (`captions.insert`). This needs the
  `youtube.force-ssl` scope: add it to `YOUTUBE_SCOPES`; the existing missing-scope check
  forces one re-consent. If the owner has not re-consented yet, skip captions with a visible
  note, don't fail.
- Upload timeout scaled to file size (lessons are 20–25 MB; 300 s is for Shorts).

## 3. The Manim page — a «Subir a YouTube» panel per render
For the newest render of the selected lesson (and a picker for older ones): the editable
title/description/tags, privacy shown in YouTube's words, the poster thumbnail, and one
«Subir a YouTube» button. During upload a progress bar in a fragment (not a page rerun,
see de83198). Afterwards: the YouTube link, written to the publication ledger, and the
render shows «Subido · fecha · enlace» everywhere; a second upload of the same render is
refused by the guard.

## Proof I need back
- `youtube.json` for make-vs-do, pasted (title, description, tags).
- One real upload of ONE lesson the owner chooses, as **unlisted** for this first test
  (override for the test only), with the link; chapters visible on YouTube; thumbnail set;
  captions present or the re-consent note.
- Shorts upload path unchanged (tests).
Cost: $0 (YouTube Data API is free; quota ≈ 1,600 units per upload of 10,000/day).

# STEP 64 — Long lessons upload to the same account, the same way as the Shorts (do this next)

The owner (2026-10-15): «los videos se suben a la misma cuenta de la misma manera que se
suben los shorts».

**Priority: run this right after STEP 59, before STEP 60.** The owner is about to upload
make-vs-do (board item w13), and today that click would open a Google consent screen.
The next Shorts upload would open it too.

## What is already the same

`manim_studio.upload_to_youtube` uses:
- the same `UploadManager` and the same `.tokens/youtube_token.json`, so the same channel;
- the same `upload_guard.decide`, so no second publication;
- the same `publication_log` ledger;
- the same default visibility, `resolve_privacy("youtube")` = public.

Keep all of that.

## What is not, and must change

1. **The captions scope made every upload ask Google again.** STEP 56 appended
   `youtube.force-ssl` to `YOUTUBE_SCOPES`, and `authenticate()` treats every entry as
   required. The stored token was granted without it (I read its scope list: upload,
   readonly, yt-analytics.readonly). So `_missing_scopes()` is non-empty and the next
   upload of *anything*, Shorts included, forces a full re-consent. The owner did not ask
   for that, and the Shorts never needed it.
   - Split the list: `YOUTUBE_REQUIRED_SCOPES` (upload, readonly, yt-analytics.readonly)
     decides `authenticate()`. `YOUTUBE_OPTIONAL_SCOPES` (force-ssl) only enables
     captions.
   - `upload_captions` keeps its current behaviour when force-ssl is missing: skip with a
     note, never fail the upload.
   - A fresh consent (no token, or a revoked one) still asks for required **and**
     optional scopes in one screen, so a future re-auth picks up captions for free.
   - Test: a token with only the three old scopes authenticates **without** opening the
     browser, uploads, and skips captions with the note. A token with no scopes at all
     still forces consent.
2. **The lesson panel must behave like the Shorts upload.**
   - `youtube_consent_note` warns only when there is **no usable token at all**.
   - A missing captions scope shows a small grey line: «Los subtítulos en español no se
     subirán: la cuenta no dio ese permiso. YouTube genera los suyos automáticamente.» It
     is not a yellow warning, and the button text does not change.
   - The button says «Subir a YouTube», as the Shorts page does.
3. **One place to upload.** On the «Subir» page, add a «Lecciones» tab next to the Shorts
   list. It shows the lesson renders that are ready, with the same row layout, the same
   «Subido · fecha · enlace» state from the ledger, and the same button. It calls the
   same `upload_to_youtube`. The Lecciones page keeps its own button too, so both doors
   lead to one function. If STEP 57 already started the «Subir» tab, extend it and do not
   duplicate it.

## Constraints

No new paid calls. Snapshot `.tokens` before any write-capable change touching it
(`cp -r .tokens .tokens.bak-YYYYMMDD`). Never print a token or a client secret. No keys,
`.env`, voice IDs or home paths in commits. Commit messages carry no attribution lines.
Do not commit the other session's uncommitted files.

## Report back

- Commit hash, pushed.
- The new tests.
- Proof with the real token, read only: list `_missing_scopes()` for the required set
  (must be empty) and for the optional set (force-ssl), and show that `authenticate()`
  returns True without opening the browser. Do not upload anything; the owner uploads.
- A screenshot of «Subir → Lecciones» with make-vs-do ready.

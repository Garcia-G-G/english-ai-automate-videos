# STEP 67 — Upload errors say why, and the panel knows the channel's daily limit

Small, $0. Run it now, before going on with STEP 63 (or between two of its sections).
One commit, pushed.

## What happened (read from `output/published/attempts.jsonl`, 2026-10-16)

- On 10:47:52 and 10:47:57 two Shorts went up. The third one, a second later, failed with
  `400 Client Error: Bad Request` on the resumable **init** POST (`session_uri: null`).
  Every attempt since then fails the same way: 14 failures, 5 different videos, at
  10:47, 10:49 and 16:30–16:31. Twice, the same video was started twice in the same
  second.
- The metadata of the failing videos is fine. Titles are 34–49 chars, descriptions
  43–81, 5 hashtags, no `<` or `>`. The same shape was published a second earlier.
- In the 24 h before the first failure the channel had published **10** uploads:
  - 15th: 17:35 ×3, 23:48 ×2
  - 16th: 00:13 ×3, 10:47 ×2

  The 11th failed. My reading: YouTube's per-channel upload limit
  (`uploadLimitExceeded`, which is a 400, unlike quota errors, which are 403). I can't
  prove it, because `upload_video` (around line 817 of `src/uploader.py`) calls
  `raise_for_status()` and throws the response body away.

## Fix

1. **Keep Google's reason.**
   - On any non-2xx from the init POST or the chunk PUTs, parse the JSON body. Keep
     `error.errors[0].reason` and `error.message`, and put them in `UploadResult.error`
     and the attempts log, e.g. `youtube 400 uploadLimitExceeded: The user has exceeded…`.
   - Never log the request headers (they carry the token).
2. **Say it in Spanish on the panel.**

   | reason | message |
   |---|---|
   | `uploadLimitExceeded` | «YouTube: el canal llegó a su límite de subidas de 24 h. Se libera hacia las HH:MM.» |
   | `quotaExceeded` (403) | «Cuota diaria de la API agotada; vuelve mañana después de la 1:00.» |
   | `invalidTitle` / `invalidDescription` / `invalidTags` | name the field |
   | anything else | the raw reason |

3. **Next free slot.** The HH:MM is the time of the oldest successful upload in the last
   24 h, plus 24 h. Read it from `attempts.jsonl`.
4. **Don't hammer.**
   - After an `uploadLimitExceeded`, the Upload button for YouTube is disabled with that
     message until the slot time.
   - A batch stops at the first one of these. It does not try the next video.
   - A second press on the same video while one attempt is running does nothing; log one
     `started` per real attempt.
5. **A counter on «Revisar y subir»:** «Subidos en las últimas 24 h: N».

## Tests

All with mocked HTTP:
- the reason is parsed and shown for 400 uploadLimitExceeded, 403 quotaExceeded and
  400 invalidTitle;
- no header or token text appears in any log;
- the slot time is computed from a fixture `attempts.jsonl`;
- a batch stops after uploadLimitExceeded;
- a double press makes one attempt.

## Proof

After the owner's next real upload, paste the attempts line. If it fails, the reason
must be in it.

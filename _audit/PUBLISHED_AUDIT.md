# Published-video audit — verified against the API

Read-only. Nothing on YouTube was modified. Re-run 2026-08-03 with
`youtube.readonly` + `yt-analytics.readonly`, replacing the replay-based
version.

Channel: **English Unlimited** — 3 subscribers, 347 lifetime views.

---

## 1. The headline correction: there are SEVEN videos, not two

The previous audit reconstructed two publications from `output/uploaded/` and
said so. That was the complete local record, and **the local record was
missing 5 of 7 live videos**.

| videoId | published | privacy | views | local artifact |
|---|---|---|---|---|
| `zG11azNZ0OI` | 2026-03-24 20:53 | public | 350 | **NO LOCAL RECORD** |
| `ZKE5riXqvx0` | 2026-07-31 20:28 | public | 79 | `steal_someone_s_thunder_20260730_213011` |
| `IQnppo8VeNs` | 2026-07-31 23:05 | public | 137 | `continuous_vs_continual_20260731_164221` |
| `hZ_BwU8eSQQ` | 2026-08-01 06:00 | public | 218 | `r_sound_differences_..._20260731_164100` |
| `hPdSoqjvu3E` | 2026-08-01 21:17 | **private** | 0 | **NO LOCAL RECORD** |
| `IvO969ZeQsM` | 2026-08-01 21:20 | public | 225 | **NO LOCAL RECORD** |
| `xHXkJuWuc1w` | 2026-08-01 22:30 | public | 15 | `run_out_20260731_163946` |

**Could not be matched to a local artifact: 3 of 7.**

- `zG11azNZ0OI` (March) predates the current pipeline. Its title is one of the
  `TITLE_TEMPLATES` literals for `educational`, so it came from this system,
  but nothing local survives.
- `hPdSoqjvu3E` and `IvO969ZeQsM` are the **same video published twice, three
  minutes apart** — identical title, identical 481-char description. The first
  is private, the second public. Almost certainly one failed-looking attempt
  followed by a retry, with the first never cleaned up. Nothing local records
  either.

The channel reports `videoCount: 6` while the uploads playlist returns 7 — the
private one is excluded from the public count.

---

## 2. Was the replay right? YES — byte-exact

Replayed at commit `0b996bc`, the code that was live at upload time (not
today's, which has a wider hashtag pool):

```
IQnppo8VeNs  title=MATCH  desc=MATCH  (297 vs 297 chars)
hZ_BwU8eSQQ  title=MATCH  desc=MATCH  (271 vs 271 chars)
```

The reconstruction was correct on every claim it made about those two,
including the duplicated hashtag block. **What it got wrong was scope, not
content** — it audited the two videos the local record knew about and had no
way to see the other five.

That is the more important lesson: the replay method is sound, and it was
applied to an incomplete universe. Item 1's ledger exists so this cannot
recur.

---

## 3. Defect classes, now measured on live data

### The duplicate hashtag block — confirmed live on 5 of 7

| videoId | first tag appears |
|---|---|
| `zG11azNZ0OI` | **2×** |
| `IQnppo8VeNs` | **2×** |
| `hZ_BwU8eSQQ` | **2×** |
| `hPdSoqjvu3E` | **2×** |
| `IvO969ZeQsM` | **2×** |
| `ZKE5riXqvx0` | 1× |
| `xHXkJuWuc1w` | 1× |

Fixed going forward by the composition-ownership change; these five are live
and need hand-editing.

### A SECOND variant the replay did not predict

Three videos carry the tag list twice in **two different forms** — once as
bare words, once with `#`:

```
xHXkJuWuc1w:
  ¡Aprende inglés de forma divertida! 📚🤓 ¿Listo para el reto? ¡Dale play! 🎥
  VerdaderoOFalso AprendeIngles PhrasalVerbs InglesDivertido LearnEnglish TrueOrFalse   <- bare
  #VerdaderoOFalso #AprendeIngles #PhrasalVerbs #InglesDivertido #LearnEnglish ...      <- with #
```

Mechanism: `resolve_upload_metadata` returned hashtags with `#` **stripped**,
the single-upload path joined those bare names onto the description, and
`VideoMetadata.full_description` then appended them again *with* `#`. So the
bare line is not a hashtag at all — it is plain text that reads as keyword
stuffing.

Both halves are now closed: `compose_description` always emits `#`, and the
uploader no longer appends.

### Titles and orthography — clean

All 7 titles open with `¿` or `¡` where required. No mangled-quote artifact,
no placeholder text. The `#Shorts` suffix is present on 5; the two without it
(`ZKE5riXqvx0`, and the `steal someone's thunder` one) went out before the
suffix logic was reached on that path.

### `ZKE5riXqvx0` has an empty API `tags` field

Its hashtags exist in the description but the separate `tags` array is `[]`.
Every other video has 6–12. That path did not pass `hashtags=` to the uploader.

---

## 4. Audience retention — available, and I was wrong to doubt it

I predicted Analytics would return empty at these view counts. **It returns a
full 100-point curve for both**, so the prediction was wrong and the data is
usable.

```
                        IQnppo8VeNs        hZ_BwU8eSQQ
  views                      134                 55
  avg view duration          23 s               28 s
  avg view percentage      68.2 %             76.5 %
```

Watch-ratio curve (1.0 = an average viewer watching that moment):

```
  elapsed    continuous_vs_continual    r_sound_differences
    1 %              1.34                     1.56
   10 %              1.19                     1.36
   25 %              0.81                     0.80
   50 %              0.64                     0.68
   75 %              0.49                     0.64
  100 %              0.36                     0.52
  retained            27 %                     33 %
```

Reading it plainly, without extrapolating:

- **The hook works.** Both open above 1.0 and hold it to the 10 % mark, which
  means viewers are re-watching the opening.
- **The cliff is between 10 % and 25 %** on both — ratio roughly halves. On a
  fill-blank video that is where the question finishes and the options begin.
- `r_sound_differences` holds the back half markedly better (0.64 vs 0.49 at
  75 %) on fewer views.

Two videos is not a sample. This is a baseline to compare against, not a
finding about content.

---

## 5. Backfill complete

All 7 rows written to `output/published/ledger.jsonl` with real `videoId`,
URL, the **live** title and description, the API tags array, privacy status
and view count at backfill time. The 3 unmatched carry
`artifact = "UNMATCHED::<videoId>"` and `matched_local: false` rather than
being silently dropped.

## 6. What needs a human

1. **Delete or unlist `hPdSoqjvu3E`** — a duplicate private upload of
   `IvO969ZeQsM`.
2. **Hand-edit the 5 duplicated hashtag blocks**, and the 3 that also carry a
   bare-word tag line.
3. Decide whether `zG11azNZ0OI` (March, 350 views — the channel's most-watched)
   should be linked to a regenerated local artifact or left as an orphan.

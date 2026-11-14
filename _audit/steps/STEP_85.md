# STEP 85 (rewritten 14 Nov) — The local API for Panel 2.0. Claude built the front end.

Garcia: «necesito que tú hagas todo lo frontend». So the split is:

- **Claude builds the whole front end in `panel/`.** It is in this commit, and it runs today in demo mode with `cd panel && npm ci && npm run demo`. Inicio and Revisar are done; Claude builds the other pages next.
- **You build the back end only.** That means the engine split, the local API that fulfils `panel/src/api/contract.ts` exactly, the live events, the spend gate, game.py and the launcher.

**Don't edit anything under `panel/src/`.** If the contract needs a change, write it in the report and Claude changes the front end.

Garcia's new rules, which arrived while Claude was building:
1. **«Sale» must be free:** any day and any time — today, tomorrow or later. The usual slots (08:30 / 12:00 / 16:00 / 19:30) are only suggestions.
2. **An «Aprobar» button** that approves without scheduling. The video waits in «Por subir».

§0 brings both to the Streamlit panel **today**. §4 and §5 make them part of the API.

## Rules, as always

- One commit per section with its tests. Push each one.
- Run the Python suite with `VIDEO_RENDER_WORKERS=2` and no pytest parallelism, plus `cd panel && npm test`. Stop on failure.
- No attribution lines.
- **No paid call from you.** Paid routes stay behind the existing locks: `ELEVENLABS_LOCK`, the OpenRouter caps of \$0.25 per Short and \$15 per month, and STEP 79 §00. Only Garcia's click opens them (§3). Tests mock every HTTP layer.
- **The Streamlit panel stays on 8501,** working, until STEP 88. The new panel runs on **8600**.
- Only free, open-source, pinned dependencies. `fastapi`, `uvicorn` and `sse-starlette` (or plain StreamingResponse) are fine.
- Bind `127.0.0.1` only. Never log or return a secret. Snapshot `.tokens` before any write-capable change.
- **Never return invented data.** If the engine doesn't know a value, return `null`; the app shows «sin dato».

## Skills — use these explicitly (Garcia's instruction)

Before §0, say which of these you have. Invoke each one at the step named below. If one is missing, say so in the report and follow its intent by hand.

**Every section:**
- `agent-protocols:planning-and-task-breakdown` — at the start of the STEP.
- `agent-protocols:incremental-implementation` — while building each section.
- `mattpocock-skills:tdd` — write the failing test first.
- `mattpocock-skills:diagnosing-bugs` — whenever a test fails, before changing code.
- `agent-protocols:code-review-and-quality` — on your own diff before each commit.
- `agent-protocols:git-workflow-and-versioning` — for each commit and push.

**This STEP:**
- §1, the engine split: `engineering:architecture`. Write a short ADR.
- §2–§5, the API:
  - `agent-protocols:api-and-interface-design`;
  - `agentic-council:architect-api-design`.
- §3, the spend gate:
  - `agent-protocols:security-and-hardening`;
  - `agentic-council:skeptic-threat-model`.
- §7, performance:
  - `agent-protocols:performance-optimization`;
  - `audit-suite:audit-as-backend-eng`.

## §0 — Today, in the Streamlit Revisar (`src/panel/revisar.py` and `admin.py` near «Sale»)

1. **«Sale» becomes free.**
   - **The controls:**
     - day chips for Hoy, Mañana and the next 5 days, plus a `st.date_input` for any later day;
     - the usual slots as one-tap chips (`st.pills` or `st.segmented_control`), with taken ones marked «ocupado»;
     - a `st.time_input` («Otra hora», step 5 min) for any minute.
   - **The summary line:** «Sale el sábado 14 nov a las 21:15 (hora de Costa Rica)».
   - **One hard rule:** at least 15 minutes ahead (YouTube needs a future `publishAt`). Anything earlier shows the error and disables the button.
   - **Warnings that never block:**
     - closer than 2.5 h to another video: «A 1 h 45 min de «MÁS ANIMALES» (lo normal: 2,5 h)»;
     - a 5th video that day: «Sería el 5.º vídeo de ese día (lo normal: 4)».
   - The exact wording and logic are in `panel/src/lib/schedule.ts` with its tests in `schedule.test.ts`. Port them to Python as `slots.check_time()` and reuse the same test cases.
2. **«✓ Aprobar».** A second button next to «Aprobar y programar». It approves and moves the video to «Por subir» with no time. Nothing is uploaded until Garcia schedules it from Subir.
3. **The scheduler** (`slots.py` / STEP 81 §2) accepts an explicit time chosen by Garcia even when it breaks spacing or the per-day count. Those limits only apply when the engine picks the time itself.
   - Record `scheduled_by: "garcia" | "auto"` in the sidecar.
   - Tests:
     - 21:15 on a day with 4 is accepted with 2 warnings;
     - 16:30 when it's 17:00 is refused;
     - auto-fill still respects the limits.

## §1 — The engine split (`src/panel_core/`)

Move every function the panel needs out of `admin.py` and `src/panel/*` into a UI-free package. That covers:
- queue reading and next best;
- pending, approved and library lists;
- slots and the schedule check;
- the costs snapshot and gate records;
- approve with or without a time, reject with a reason, re-render;
- start generation and job state with **per-step progress** (guion, voz, montaje, sonido, control, 0..1 each);
- the STEP 85b thumbnail paths.

The Streamlit panel imports them from there and behaves exactly as before.

Tests:
- the existing suite passes;
- `import panel_core` does not import streamlit.

Write the ADR at `docs/adr/0xx-panel-2.md`.

## §2 — The read endpoints (`src/panel_api/`, FastAPI)

**Fulfil `panel/src/api/contract.ts` field by field.** Every endpoint is read-only and caches on file mtimes.

| Endpoint | Returns | Notes |
|---|---|---|
| `GET /api/meta` | `Meta` | `counts` (queue, review, upload, comments) must equal what the Streamlit sidebar shows. |
| `GET /api/home` | `Home` | `next` from `next_best()`; `next.thumb` is the script's frame 0 from STEP 85b, as WebP, or `null`. `agenda` comes from slots and the ledger, with views from the latest stats. `views` is the last 28 days from senal, against the 28 before. `formats` is the top 5 medians. `formatsNote` and `sequels` follow the STEP 83 rules. `daySentence` follows STEP 83 §2.1. |
| `GET /api/game` | `Game` | From §6. |
| `GET /api/review` | `ReviewList` | `items` (frame 0 WebP, the 6-frame strip, `videoUrl`, checks with `ok: null` when there's no data), `schedule` (`ScheduleInfo`: tz, offset `-06:00`, slots, `taken` for the next 14 days, `minLeadMin` 15, `spacingH` 2.5, `maxPerDay` 4, `next`) and `platforms`. |
| `GET /api/jobs/{id}` | `Job` | |
| `GET /media/...` | images and MP4s | Only from `output/` (path-checked, no `..`). The MP4 supports HTTP Range so the `<video>` player can seek. Long cache headers on thumbnails. |

**Contract test.** For each GET endpoint, compare your response with `panel/contract-fixtures/<name>.json`. Use the same keys, the same JSON types, and `null` where allowed. Run it in CI.

## §3 — The spend gate (security)

- **The token.** At startup, make a random per-session token. Serve `panel/dist/index.html` with `<meta name="eu-session" content="…">` filled in. Nowhere else exposes the token.
- **Paid routes:** `POST /api/produce` and `POST /api/review/{id}/rerender`, and any later paid route. Each needs:
  - the `X-EU-Session` header equal to the token;
  - `"confirm": true` in the body;
  - `Origin` and `Host` in {`127.0.0.1:8600`, `localhost:8600`, and `127.0.0.1:5173` / `localhost:5173` in dev}.

  Otherwise answer 403 or 400 with a Spanish `{"error": …}`.
- **Free POSTs** (approve, reject) need the same Origin/Host check, but no token.
- **The lock.** The ElevenLabs/OpenRouter lock opens only inside a valid paid request, exactly as the Streamlit click does now. CLI, pytest and tools stay locked.
- **Tests:**
  - no token → 403;
  - wrong token → 403;
  - foreign Origin → 403;
  - no confirm → 400;
  - a valid produce with a mocked engine → 200.

## §4 — The write endpoints

- **`POST /api/produce`:**
  - body `ProduceRequest`, returns `ProduceResponse`;
  - starts the job in the background, and never blocks the request;
  - honours the existing «ya hay un vídeo renderizándose» refusal with a Spanish error.
- **`POST /api/review/{id}/approve`:**
  - body `ApproveRequest`, returns `ApproveResponse`;
  - with `publishAt`, it schedules through the same guarded upload path as Subir (YouTube private plus `publishAt`, and Facebook per STEP 81 §2) at **that exact time**, with the §0 warnings in `warnings`;
  - with `publishAt: null`, it only approves (→ «Por subir»);
  - the edited `title`, `description` and `hashtags` are saved to the sidecar first;
  - if a platform fails, the video stays in «Por subir» and the result says why.
- **`POST /api/review/{id}/reject`:** body `RejectRequest`. The reason goes into the sidecar and the log.
- **`POST /api/review/{id}/rerender`:** paid (§3); otherwise the same as Streamlit's «Volver a renderizar».

## §5 — Live events (`GET /api/events`, Server-Sent Events)

- **Events.** Emit the `ServerEvent` union from the contract: `job.step` (with progress and an optional log line), `job.done` (with the new review count and XP gained), `job.failed` (with a Spanish reason), `counts`, `stats.refreshed`, `game`, `achievement.unlocked`.
- **Heartbeat:** a comment line every 15 s.
- **Where they come from.** The engine reports step progress through a small callback or queue from the render job. Don't poll files from the browser.
- **Test:** a fake job emits the five steps and `job.done` in order.

## §6 — Gamification (`panel_core/game.py`), from real history only

- **XP:**
  - +40 per published video (first platform);
  - +10 per video approved without a re-render;
  - +100 when a video reaches ≥ 2× its format's normal by day 3.
- **Level:** `1 + floor(xp / 1000)`. `levelXp = xp % 1000`, `levelSize = 1000`.
- **Streak:** consecutive Costa Rica calendar days with ≥ 1 publication. Today counts once something is published or scheduled today.
- **Achievements**, each with id, Spanish name, one-line description, emoji, and the date it was unlocked or `null`. The front end's demo has examples of each:
  - first video;
  - 10, 50 and 100 videos;
  - 50 «Cómo se dice»;
  - first 1,000-view video;
  - 10,000 views in a week;
  - 7- and 30-day streaks;
  - a week with no rejections;
  - the first sequel that beats its parent.
- **Unlocking:** when a recompute unlocks one, emit `achievement.unlocked` and `game`.
- **Tests:** a fixture ledger with known XP, level, streak (crossing midnight in Costa Rica), and each achievement's date.

## §7 — Launcher and performance

- **`./run_panel.sh`:**
  - if `panel/dist` is missing or older than `panel/src`, run `cd panel && npm ci && npm run build`;
  - then start uvicorn on 127.0.0.1:8600, serving `/api`, `/media` and the built app, with an SPA fallback to `index.html` and the token injected;
  - print the URL.
- **Budgets,** measured on the Mac and reported:

  | What | Budget |
  |---|---|
  | `GET /api/meta`, p95 warm | ≤ 50 ms |
  | `/api/home` and `/api/review`, p95 warm | ≤ 150 ms |
  | `/api/home`, cold | ≤ 800 ms |
  | `./run_panel.sh` with dist built, to first response | ≤ 2.5 s |
  | API process after 2 h with the panel open | ≤ 300 MB RSS |

## §8 — Proofs ($0)

Run `./run_panel.sh` with real data and open the app. Save to `_audit/stills/STEP85/`:
- screenshots of Inicio and Revisar, by day and by night (use the theme menu);
- the contract test output;
- the security test output;
- the latency table.

No real render: use a mocked job for the `job.step` screenshot.

## Report

Give Claude:
- the commits;
- both suite totals;
- the skills used per section;
- the ADR path;
- every place where the engine couldn't fill a contract field (it returns `null`), and why;
- the real XP, level, streak and unlocked achievements;
- the latency table;
- $ spent, which must be $0;
- anything not verified.

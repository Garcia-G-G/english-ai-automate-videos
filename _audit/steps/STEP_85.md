# STEP 85 — Panel 2.0: a real web app with the «Mezcla» look, day and night by New York time

## What Garcia decided

- The panel leaves Streamlit. Streamlit reruns the whole page on every click, so it can never feel fluid. The new panel is a local web app over the existing Python engine.
- **The look is «Mezcla»** in its two versions, taken from Claude's prototype `_audit/design/panel2/direcciones.html`:
  - **Mezcla · noche** — option 7;
  - **Mezcla · día** — option 8.

  It takes from three of the styles Garcia saw:
  - **Pegatina:** the bouncy entrance and the hover tilt;
  - **Vidrio:** the slow colour blobs behind, and the frosted panels;
  - **Modo juego:** level, XP, streak, achievements, the yellow button that sinks when pressed, the striped bars, Bubi hopping and the pixel-font details.
- **Theme by New York time.** From 19:00 to 06:59 in `America/New_York` the panel is in night mode. From 07:00 to 18:59 it is in day mode.
- **Fluidity and performance are part of the job**, with measured budgets (§7). They are not a polish pass at the end.

Open the prototype in a browser before you start:
- the picker at the top switches between the directions; 7 and 8 are the two Mezcla versions;
- «Producir» shows the motion: steps, confetti, XP, achievement, toast and badge bump;
- «🕖 Automático (Nueva York)» shows the theme rule.

Copy the motion values (durations, easings, springs) and the colour tokens from its CSS (`.s-mixn`, `.s-mixd` and the keyframes). Don't guess them. The screenshots in that folder render with fallback fonts; the HTML loads the real ones.

This is a series:
- **STEP 85** (this one): the foundation, the design system, Inicio, and producing a video end to end.
- **STEP 86:** Revisar, Crear and Cola.
- **STEP 87:** Rendimiento (the STEP 84 charts), Biblioteca, Comentarios and the rest.
- **STEP 88:** the switch-over, retiring Streamlit, and the engine performance pass.

STEP 84 is paused. Don't build its pages in Streamlit; their mocks carry over to STEPs 86–87.

## Rules, as always

- One commit per section with its tests. Push each one.
- Run the Python suite with `VIDEO_RENDER_WORKERS=2` and no pytest parallelism, plus the new `vitest` suite. Stop on failure and report.
- No attribution lines.
- **No paid call from you.** Every paid action (TTS, LLM, image, video) stays behind the existing locks: `ELEVENLABS_LOCK`, the OpenRouter caps of \$0.25 per Short and \$15 per month, and STEP 79 §00. The only thing that may open them is Garcia's click in the panel (§1.4). Tests mock every HTTP layer.
- **The Streamlit panel keeps working,** untouched, on 8501 until STEP 88. The new panel runs on **8600**.
- **Only free, open-source dependencies, pinned to exact versions.** Nothing that phones home. Fonts are bundled through `@fontsource`; no runtime Google Fonts.
- **No logic duplicated in TypeScript.** Every rule (priority, slots, the repetition guard, costs, gates) stays in Python. The app only displays it and calls it.
- **Never show invented data.** A missing value is «sin dato». XP, level, streak and achievements are computed from real history (§5).
- Security:
  - bind to `127.0.0.1` only;
  - never log or return a secret;
  - snapshot `.tokens` before any write-capable change, as always.

## Skills — use these explicitly (Garcia's instruction)

Before §0, say which of these you have. Invoke each one at the step named below. If one is missing, say so in the report and follow its intent by hand.

**Every section:**
- `agent-protocols:planning-and-task-breakdown` — at the start of the STEP.
- `agent-protocols:incremental-implementation` — while building each section.
- `mattpocock-skills:tdd` — write the failing test first, for every rule, endpoint and component state.
- `mattpocock-skills:diagnosing-bugs` — whenever a test or a page fails, before changing code.
- `agent-protocols:code-review-and-quality` — on your own diff before each commit.
- `agent-protocols:git-workflow-and-versioning` — for each commit and push.

**This STEP:**
- §0, architecture: `engineering:architecture` or `agentic-council:architect-codebase-context`. Write a short ADR.
- §1, the API:
  - `agent-protocols:api-and-interface-design`;
  - `agentic-council:architect-api-design`;
  - `agent-protocols:security-and-hardening` — localhost binding, Origin/Host checks, the spend token.
- §2, the app:
  - `agent-protocols:frontend-ui-engineering`;
  - `hzblj-skills:component-architecture`;
  - `hzblj-skills:hooks`;
  - `hzblj-skills:type-safety`.
- §3, the design system:
  - `design:design-system`;
  - `icons8:design-tokens`;
  - `hzblj-skills:ui-surfaces`;
  - `hzblj-skills:ui-typography`;
  - `design:accessibility-review` — AA contrast in both themes.
- §4, motion:
  - `hzblj-skills:ui-motion`;
  - `audit-suite:web-animation-design`;
  - `audit-suite:emil-design-engineering`;
  - `vectorlab-ux-skills:motion`, `vectorlab-ux-skills:transitions` and `vectorlab-ux-skills:reduced-motion`.
- §6, Inicio:
  - `frontend-design:frontend-design`;
  - `audit-suite:make-interfaces-feel-better`;
  - `hzblj-skills:ui-interactions`;
  - `vectorlab-ux-skills:loaders` and `vectorlab-ux-skills:empty-states`.
- §7, performance:
  - `agent-protocols:performance-optimization`;
  - `audit-suite:vercel-react-best-practices`;
  - `audit-suite:audit-as-perf-eng`.
- §8, proofs:
  - `agent-protocols:browser-testing-with-devtools`;
  - `design:design-critique`, on each screenshot against the prototype.

## §0 — Architecture and the engine split

1. **Move the logic out of the UI.** Today the logic the panel needs lives inside `src/admin.py`, which runs Streamlit on import. Move it into a UI-free package, `src/panel_core/`: queue reading, pending/approved/library lists, next best, slots, the costs snapshot, gate records, approve/reject, start generation and job state.
   - `admin.py` imports from there, and behaves exactly as before.
   - Tests: the existing suite passes unchanged, and `import panel_core` does not import streamlit.
2. **Write the ADR** `docs/adr/0xx-panel-2.md`. It covers:
   - why we leave Streamlit;
   - the shape: FastAPI + React, served locally;
   - how paid actions stay locked;
   - the switch-over plan.

## §1 — The local API (`src/panel_api/`, FastAPI + uvicorn)

1. **Endpoints.** They return JSON and are thin wrappers over `panel_core`:
   - `GET /api/home` — everything Inicio shows (§6), in one call;
   - `GET /api/jobs`, `GET /api/jobs/{id}`;
   - `POST /api/produce` — start the next best video, or a given script;
   - `GET /api/game` — XP, level, streak, achievements (§5);
   - `GET /api/meta` — version, balances, the OpenRouter month.
2. **Live updates over Server-Sent Events,** `GET /api/events`. Events:
   - `job.step` — Guion, Voz, Montaje, Sonido and Control, with the percentage;
   - `job.done` and `job.failed`;
   - `review.count`;
   - `stats.refreshed`;
   - `achievement.unlocked`.

   No polling in the app except a 60 s fallback.
3. **Caching.** Read endpoints cache on file mtimes. p95 ≤ 150 ms warm (§7).
4. **The spend gate.** It replaces the Streamlit «panel click» permission.
   - At startup the server makes a random per-session token. It serves it only inside the HTML it serves.
   - Paid routes (`/api/produce` and later re-render, bonus voice and drafts) require that token in a header, **plus** an explicit `"confirm": true` in the body.
   - They check `Origin` and `Host` are `127.0.0.1:8600` or `localhost:8600`. Anything else gets 403.
   - The ElevenLabs/OpenRouter lock opens only inside such a request, exactly as the Streamlit click did.
   - Tests:
     - no token → 403;
     - wrong Origin → 403;
     - no confirm → 400;
     - CLI, pytest and tools stay locked.
5. **One command.** `./run_panel.sh` builds the app if needed, starts uvicorn on 127.0.0.1:8600, which serves the built app and the API, and prints the URL. The dev mode, `npm run dev` with a proxy, is documented in the README.

## §2 — The app (`panel/`: Vite + React + TypeScript)

Match `senal/`'s toolchain versions. Libraries, all free and MIT/ISC, pinned exactly:

| Library | Use |
|---|---|
| `react`, `react-dom` | the UI |
| `@tanstack/react-query` | data, cache and background refresh |
| `react-router` | routes |
| `motion` (Framer Motion) | springs, layout and page transitions |
| `lucide-react` | icons |
| `@fontsource/fredoka`, `@fontsource/manrope`, `@fontsource/silkscreen` | fonts |

Write confetti yourself, or use `canvas-confetti`.

- **Routes:** `/` (Inicio), plus placeholders for `/revisar`, `/crear`, `/cola`, `/rendimiento`, `/biblioteca` and `/comentarios`. Each placeholder links to the same page in the Streamlit panel until its STEP lands.
- **The sidebar** is the prototype's:
  - brand, items with lucide icons and badges;
  - the active item is the yellow pill with its sink shadow;
  - the OpenRouter meter at the bottom.
- **Strict TypeScript.** API types are generated from FastAPI's OpenAPI with `openapi-typescript`; no hand-written duplicates.

## §3 — Design system (`panel/src/design/`)

1. **Tokens** for both themes, copied from the prototype's `.s-mixn` and `.s-mixd`:
   - background, text, muted, line, tile (glass), nav;
   - accent (yellow), good, warn, badge;
   - mark (pink→violet gradient), chart, track, toast.

   Put them in CSS custom properties on `:root[data-theme="night"|"day"]`.
2. **Type:**
   - Fredoka for titles and numbers;
   - Manrope for text;
   - Silkscreen only for the level, the streak and the eyebrow.

   Use tabular numbers everywhere digits line up.
3. **Components**, each with its states (default, hover, active, focus-visible, disabled, loading):
   - `Tile` (glass);
   - `HeroTile` (the sticker: yellow outline at night, ink outline plus offset shadow by day);
   - `GameButton` (the yellow button that sinks 5 px with its shadow when pressed);
   - `Tag`, `Chip`, `Badge` (with bump);
   - `XPBar` (striped, animated);
   - `AchievementBadge`, `Toast`, `Steps`, `Slot` (agenda row, with the pulsing ring on the next one);
   - `BarRow` (striped);
   - `AreaChart` (SVG; port the prototype's);
   - `CountUp`, `Skeleton`, `EmptyState` (Bubi);
   - `Video9x16` (the frame 0 image, never restyled — it is the Tablero look).
4. **Contrast:** AA in both themes, with a test over the token pairs.
5. **A hidden `/componentes` route** renders every component in both themes, for the proofs.

## §4 — Motion system (`panel/src/design/motion.ts`)

1. **Named presets,** taken from the prototype:

   | Preset | Values |
   |---|---|
   | `enter` | the pop: scale .9 → 1.025 → 1, a little rotate, 0.6 s, cubic-bezier(.3,1.4,.5,1); a 80 ms stagger between tiles |
   | `hoverTilt` | rotate −0.4°, y −4 px |
   | `press` | y +5 px, shadow 6 → 1 px |
   | `bump` | badge scale 1.35 |
   | `ring` | the next slot's pulse |
   | `hop` | Bubi |
   | `drift` | the background blobs, 16–23 s |
   | `draw` | the chart line, 1.4 s |
   | `countUp` | 1.1 s ease-out cubic |
   | `confetti` | 34 pieces, 1.3 s |

2. **Page transitions.** The outgoing page fades and slides 8 px in 160 ms; the incoming page uses `enter` with a shorter stagger. The sidebar never re-animates.
3. **Theme change.** It is a 600 ms crossfade of the tokens. The blobs re-colour over the same time. Nothing jumps.
4. **Only `transform` and `opacity` animate,** except the token crossfade.
   - Under `prefers-reduced-motion`: no entrances, no drift, no confetti, no hop; instant state changes.
   - Pause the blob drift when the tab is hidden.
5. **Bubi is alive.** Use the v3 expressions (`simbolo`, `wow`, `bien_hecho`, `lo_lograste`), each as a state:
   - idle hop every ~2.4 s;
   - `wow` while a job runs;
   - `lo_lograste` on job done;
   - `bien_hecho` when an achievement unlocks.

   Bubi is decorative: `aria-hidden`.

## §5 — Gamification, computed from real history (`panel_core/game.py`)

Everything comes from the ledger and the stats, deterministically. Nothing is stored that can't be recomputed.

- **XP:**
  - +40 per published video (first platform);
  - +10 per video approved without a re-render;
  - +100 when a video reaches ≥ 2× its format's normal by day 3.
- **Level:** `1 + floor(total XP / 1000)`. Show XP within the level, «720 / 1000 XP».
- **Streak («racha»):** consecutive days with ≥ 1 publication, by the Costa Rica calendar (the publishing slots' zone). Today counts once something is published or scheduled for today.
- **Achievements**, computed and dated:
  - first video;
  - 10 / 50 / 100 videos;
  - 50 «Cómo se dice»;
  - first video with 1,000 views;
  - 10,000 views in a week;
  - 7- and 30-day streaks;
  - a week with no rejections;
  - first sequel to beat its parent.

  Each achievement has a lucide icon or an emoji, a name and a one-line Spanish description.
- **Unlocks.** When a refresh unlocks one, emit `achievement.unlocked` (SSE). The app shows the toast, the badge pulse, Bubi `bien_hecho` and confetti.
- **Tests:** a fixture ledger with known XP, level, streak (crossing midnight in Costa Rica), and each achievement's date.

## §6 — Inicio (the prototype, option 7/8, with real data)

Top to bottom:

1. **The greeting.**
   - The eyebrow, in Silkscreen: «Nivel N · día D de racha».
   - The title: «Buenos días / Buenas tardes / Buenas noches, Garcia», by Costa Rica time.
   - The day's sentence, as in STEP 83.
   - At the right, a chip with the theme state: «☀︎ Día hasta las 19:00 (NY)» or «☾ Noche hasta las 7:00 (NY)», plus the stats chip.
2. **The XP strip:**
   - the level pill;
   - the striped bar;
   - «XP / 1000 XP»;
   - «Racha N días»;
   - the last 3 achievements unlocked.

   Clicking it opens a sheet with all achievements, locked ones in grey with their condition.
3. **The hero:**
   - frame 0 (the cached thumbnail);
   - «Siguiente vídeo · sale a las HH:MM»;
   - the title with the topic marked;
   - the tags (from the priority explanation);
   - the English words;
   - four facts (duration, cost, render time, repeated words — «sin dato» rules from STEP 83);
   - **«▶ Producir · +40 XP»** (`GameButton`).

   **Producing**, all live over SSE:
   - the facts row is replaced by the five step bars;
   - the button reads «En marcha…»;
   - a toast says «En marcha: <topic> · listo en ~N min»;
   - each step fills as the engine reports it;
   - **on `job.done`:** the button reads «✓ Listo · en Revisar» for 2.5 s; the Revisar badge bumps to its new count; confetti bursts from the button; XP animates if it changed; a toast appears.
   - **On failure:** the red toast gives the reason in Spanish and the button is restored. Nothing else animates.
4. **«Agenda de hoy»:** the 4 slots, with done, scheduled and free states. The next free slot gets the pulsing ring.
5. **«Vistas · 4 semanas»:**
   - the count-up number;
   - the «×N vs las 4 anteriores» pill (red ▼ if down);
   - the drawn area chart, with the axis row under it in HTML (not text inside a stretched SVG);
   - three mini numbers.
6. **«¿Qué formato rinde?»:** the top 5 striped bars, growing in on entrance, in the format colours from STEP 84 §2.3.
7. **Empty, loading and error states** for each tile:
   - a skeleton only if the data takes > 300 ms;
   - Bubi's empty state when the queue is empty;
   - a red one-line error with «Reintentar».

## §7 — Fluidity and performance budgets (measured, in the report)

**Fluidity:**
- **Instant navigation:** no full reloads, prefetch a route's data on hover or focus of its nav item, and keep the previous data visible while refetching.
- **Optimistic UI** where safe: badges and counts update at once, and roll back with a toast if the server refuses.
- **No layout shift.** Tiles reserve their size; the hero doesn't jump when the steps replace the facts.

**Budgets:** measure them with a production build on the Mac, using the Chrome DevTools performance trace or Playwright tracing. Report the before and after for each.

| What | Budget |
|---|---|
| Cold start of `./run_panel.sh` to first paint | ≤ 2.5 s |
| Inicio first contentful paint | ≤ 600 ms |
| Inicio fully loaded | ≤ 1.0 s |
| Read endpoints, p95 warm | ≤ 150 ms |
| `/api/home`, cold | ≤ 800 ms |
| Initial JS (gzip), routes code-split | ≤ 220 KB |
| Interaction to next paint on any click | ≤ 100 ms |
| Animations at 1440×900 | 60 fps, no long tasks > 50 ms during the entrance, confetti or theme crossfade |

- **If the frosted glass costs frames:** if `backdrop-filter` drops below 60 fps on Garcia's Mac, lower the blur radius before removing it. Report the numbers.
- **Memory:** the panel tab stays under 150 MB after 30 minutes open, counting the blob drift and the SSE connection.

## §8 — Theme by New York time (in §3's code, its own commit)

1. **The rule:** `hour(America/New_York) >= 19 || hour < 7` → night; otherwise day. Use `Intl.DateTimeFormat(..., { timeZone: "America/New_York", hourCycle: "h23" })` so daylight saving is handled.
   - Re-check every 60 s, and on `visibilitychange`.
   - Switch with §4.3's crossfade.
2. **The override in Ajustes** (a later STEP; for now a small menu on the theme chip): «Automático (Nueva York)» by default, «Siempre día» or «Siempre noche». Keep it in `localStorage`, wrapped in try/catch, with automatic as the fallback.
3. **Tests:**
   - 18:59 → day; 19:00 → night; 06:59 → night; 07:00 → day;
   - the two daylight-saving switch days of 2026 and 2027;
   - a machine set to Costa Rica time (UTC−6) gets the same answer as one in New York.

## §9 — Proofs ($0)

Start your own `./run_panel.sh` on 8600 with real data. Save to `_audit/stills/STEP85/`:
- **Screenshots:**
  - Inicio in day and in night, at 1440×900, device scale 2;
  - `/componentes` in both themes;
  - the achievement sheet.
- **A short screen recording** (GIF or MP4, ≤ 15 s) of:
  - the entrance;
  - a hover;
  - the theme crossfade, forced by the override;
  - «Producir» against a **mocked** job (the API in test mode emits fake `job.step` events). No real render, no spend.
- **The performance table and the traces' summary.**
- **The side-by-sides** `inicio_dia_vs_prototipo.png` and `inicio_noche_vs_prototipo.png`, against the prototype's options 8 and 7.

## Report

Give Claude:
- the commits;
- both suite totals;
- the skills used per section;
- the ADR path;
- the endpoints;
- the security tests;
- the XP, level, streak and achievements computed from the real ledger, with the numbers;
- the performance table;
- the proof paths;
- every difference from the prototype, and why;
- $ spent, which must be $0;
- anything not verified.

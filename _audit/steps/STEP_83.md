# STEP 83 — The panel, redesigned: «Papel» palette, a new Inicio and a one-click Revisar

Garcia: «quiero que se barra el diseño actual y se mejore x1000». STEP 82 did this for the videos. This STEP does it for the panel (`src/admin.py`, Streamlit). Garcia approved Claude's mockups and chose the **Papel** palette.

The reference is in `_audit/design/panel/`:
- `panel_inicio.png` — the new Inicio;
- `panel_revisar.png` — the new Revisar;
- `paletas_comparadas.png` — the three palettes Claude offered. Garcia chose **A · Papel**.
- `mock/` — the HTML and CSS that drew them. `mock/base.css` + `mock/theme-papel.css` hold every colour, radius, border and shadow. Open `mock/inicio.html` in a browser and read the CSS; don't guess measures from the PNG.

Match the mockups. Where this text and the mock disagree, the mock wins. Where the mock shows a number, the panel shows the real one. The mock's agenda, counters and gate values are illustrative.

## Rules, as always

- One commit per section with its tests. Push each one.
- Run the full suite with `VIDEO_RENDER_WORKERS=2` and no pytest parallelism. Stop on failure and report.
- No attribution lines.
- **No paid call from you.** TTS, LLM, image and video calls only happen from Garcia's clicks, under the existing locks and caps. Tests mock every HTTP layer.
- **Don't touch Garcia's running panel on port 8501.** For proofs, start your own server on a spare port and stop it afterwards.
- **Commit only your own files.** The working tree already has changes the panel made: `config.yaml`, and scripts moved out of `content/queue/`. Leave them out of your commits and list them in the report.
- **Never show invented data.** If a value isn't available, show «sin dato» in grey. Never show a green tick or a number you didn't read from disk or the stats.
- Every label is in Spanish. Money uses `\$` inside `st.markdown` (STEP 80 §0).
- Keep every existing page and action. If something moves, say where it went in the report.

## Skills — use these explicitly (Garcia's instruction)

Before §0, check which of these skills you have, and say in your first reply which ones are present. Invoke each skill at the step named below; don't work from memory of what it says. If a named skill is not installed, say so in the report and follow its intent by hand. Do not silently skip it.

**Every section:**
- `agent-protocols:planning-and-task-breakdown` — at the start of the STEP, to break the sections into tasks with acceptance checks.
- `agent-protocols:incremental-implementation` — while building each section, in small verified steps.
- `mattpocock-skills:tdd` (or `agent-protocols:test-driven-development`) — write the failing test first for every rule this STEP adds: counts, colours, «sin dato», slot logic and badges.
- `mattpocock-skills:diagnosing-bugs` (or `agent-protocols:debugging-and-error-recovery`) — whenever a test or a page fails, before changing code.
- `agent-protocols:code-review-and-quality` — on your own diff before each commit.
- `agent-protocols:git-workflow-and-versioning` — for each commit and push.

**STEP 83 specifically:**
- §0, tokens and theme:
  - `icons8:design-tokens` or `agentic-council:artisan-design-system-architecture` — one source of truth for the palette;
  - `vectorlab-ux-skills:colour-palette`;
  - `design:accessibility-review` — WCAG AA for every text and background pair in the tokens.
- §1–§3, layout and components:
  - `hzblj-skills:ui-surfaces` and `vectorlab-ux-skills:surfaces` — cards, borders, offset shadows, radii;
  - `vectorlab-ux-skills:spacing`;
  - `hzblj-skills:ui-typography` and `vectorlab-ux-skills:typography` — Fredoka for headings, Manrope for text, tabular numbers;
  - `hzblj-skills:ui-interactions` and `vectorlab-ux-skills:icon-buttons` — buttons, hover and disabled states.
- §1–§3, copy:
  - `design:ux-copy`;
  - `vectorlab-ux-skills:labels`, `vectorlab-ux-skills:verbs`, `vectorlab-ux-skills:empty-states`, `vectorlab-ux-skills:errors` and `vectorlab-ux-skills:loaders` — every empty queue, error and loading state gets a short Spanish line.
- §2, the bars against «lo normal»: `dataviz`, if installed; otherwise `agentic-council:strategist-analytics-design`.
- §4, the other pages: `audit-suite:make-interfaces-feel-better` and `vectorlab-ux-skills:anti-slop`.
- §5, speed: `agent-protocols:performance-optimization` — measure before and after.
- §6, proofs: `design:design-critique` (or `ui-design-review:ui-review`), on your own screenshots against the mock, before handing them to Claude.

## §0 — Tokens and theme: Papel

1. **The tokens.** One file, `src/panel/tokens.py` (or `config.yaml` → `panel.theme`; pick one and say which). It holds the Papel values:

   | Token | Value | Use |
   |---|---|---|
   | page | `#F5F1EA` | page background |
   | sidebar, card | `#FFFFFF` | sidebar background; cards |
   | ink | `#191720` | text, card outlines, offset shadows |
   | muted | `#6B6672` | secondary text |
   | line | `#E3DCCF` | thin borders, dividers |
   | blue | `#1F6FD1` | main actions, normal bars |
   | blue-soft / blue-ink | `#E1ECFB` / `#164C93` | blue tags |
   | yellow | `#F6D35B` | highlighter and post-it only, never as text colour |
   | yellow-soft / yellow-ink | `#FCF0C4` / `#6E5300` | yellow tags |
   | coral | `#FF6F4F` | decorative only |
   | badge | `#C9401F` | alert badges, white text |
   | coral-soft / coral-ink | `#FFE1D8` / `#A0391F` | coral tags |
   | green | `#12854F` | approve button, «por encima» bars |
   | green-soft / green-ink | `#DAF1E4` / `#1F6B42` | green tags |
   | red | `#D2433A` | «por debajo», reject |
   | red-soft / red-ink | `#FADCD8` / `#8E2B22` | red tags |

   Claude checked these pairs at ≥ 4.5:1:
   - white on blue 4.94;
   - white on green 4.67;
   - white on badge 4.96;
   - muted on page 4.95.

   Add a test that checks every text/background pair the CSS uses.
2. **`.streamlit/config.toml`.** Set:

   ```toml
   primaryColor = "#1F6FD1"
   backgroundColor = "#F5F1EA"
   secondaryBackgroundColor = "#FFFFFF"
   textColor = "#191720"
   ```

   Keep `base = "light"`.
3. **The CSS block** at the top of `admin.py` is rebuilt from the tokens. Port the mock's components: `.card`, `.sticker`, `.btn`, `.tag`, `.chip`, the sidebar `.nav` and `.nav.on`, and the badges.
   - Style Streamlit's own buttons through keyed containers (`st.container(key=...)` → `.st-key-...`), so real `st.button`s look like the mock's buttons. Don't fake them with HTML.
   - Fonts:
     - load Fredoka and Manrope from `assets/fonts/` through Streamlit static serving if your Streamlit version supports it;
     - otherwise keep the Google Fonts import, with the local system font as fallback.

## §1 — Sidebar

Copy the mock:
- **Brand.** `assets/branding/english-unlimited/simbolo_512.png`, «English Unlimited» with «Unlimited» highlighted, and «Estudio de vídeos» under it.
- **Three groups:**
  - **PRODUCIR:** Inicio, Crear, Cola, Revisar, Subir, Lecciones;
  - **CANAL:** Rendimiento, Comentarios, Biblioteca;
  - **AJUSTES:** Temas, Programar, Ajustes, Registros.

  Keep every page that exists today.
- **The active page** is an ink pill with a blue offset shadow.
- **Badges.** Each badge is hidden when its count is 0.
  - Cola: the number of queued scripts, in a soft badge.
  - Revisar: the number pending, in an alert badge.
  - Comentarios: unanswered comments, in an alert badge. Count them from the cached list STEP 81 §3 keeps; make no API call on a rerun.
- **At the bottom:**
  - the OpenRouter meter: «\$X de \$15» with a bar, and «Por vídeo \$media · tope \$0.25»;
  - the version line, which already exists.

## §2 — Inicio

Build the mock's Inicio, top to bottom, with real data. Reuse the existing functions (`next_best()`, `channel_stats.latest()`, `sequel_suggestions`, `slots.next_slots` / `fill_plan`, `daily_mix`, the ledger readers, `queue_guard`). Name the functions you used in the report.

1. **Greeting.**
   - «Buenos días / Buenas tardes / Buenas noches, <name>», by the hour in America/Costa_Rica. Put the name in `config.yaml` → `panel.owner_name: "Garcia"`, with «Garcia» highlighted.
   - Under it, the date and one sentence built from today's slots, for example «Hoy salen 4 vídeos y ya hay 3 en su sitio. Falta uno para las 19:30.» When all 4 slots are filled, it says «Hoy está todo listo».
   - At the right, a chip: «Estadísticas al día · hace N h», with a green dot. The dot is amber after 24 h, with «Actualizar» beside it.
2. **The flow strip.** Four cells, each clickable to its page:
   - **Producir:** the free slots today with no video. The cell is highlighted when it is > 0, and its line names the next free slot.
   - **Por revisar.**
   - **Por subir.**
   - **Guiones en cola:** its line says «para N días», at 4 a day.
3. **The hero, «Siguiente vídeo».** A sticker card (ink outline and offset shadow).
   - **The preview** on the left is frame 0 of that script, drawn by the Tablero kit with no audio. Make no paid call.
     - Cache it at 270×480 in `output/thumbs/scripts/<id>.png`, keyed on the script's mtime.
     - Types without a Tablero frame 0 show a card in their family's gradient, with the emoji and the topic.
     - Do this inside `st.cache_data`; a cold Inicio must still meet §5.
   - **The eyebrow:** «Siguiente vídeo · sale <slot>».
   - **The title:** the real title, with the topic highlighted.
   - **«Por qué este»** as 2–3 tags, from the priority explanation:
     - the sequel and its parent's views;
     - the format;
     - the topic tier.
   - **The English words** as chips.
   - **Four facts:**
     - estimated duration;
     - estimated cost, from the existing estimator;
     - render time, the median of the last 10 jobs of that type («sin dato» if there are fewer than 3);
     - repeated words, from the repetition guard.
   - **Buttons:**
     - «▶ Producir ahora» — the existing action, the same lock and cap;
     - «Elegir otro de la cola» — opens Cola.
   - **Empty queue:** «La cola está vacía. Añade guiones en Temas.», with a button to Temas.
4. **«Agenda de hoy»**, at the right. A vertical timeline of today's 4 slots.
   - Each slot has one state:
     - **published** (green dot): the title and the views from the latest stats;
     - **scheduled** (ring): «Programado en YouTube y Facebook», listing the platforms that are true;
     - **free** (yellow dot, dashed box): «Hueco libre · Lo llena: <script>».
   - Under the timeline: «Mañana: N huecos · ya hay guion para M».
5. **«Cómo van tus últimos vídeos»** — the last 7 days.
   - **The totals:** views, videos and average views.
   - **Then the 5 most recent videos**, each with a bar against «lo normal» for its format, which is the format median `channel_stats` already computes.
     - The dashed line marks the normal. The bar scale caps at 2× the normal.
     - **Colour:**
       - green when the video is ≥ 1.2× normal;
       - red when it is < 0.5× normal **and** at least 1 day old;
       - otherwise blue.
     - The right column shows the views and «N× lo normal» or «N % · día D».
   - **The legend**, and «Ver todo en Rendimiento →».
6. **«Secuelas por escribir»:**
   - The `sequel_suggestions` cards, each with an «Escribir» button. It is the existing STEP 81 §1.4 draft action: the cheap model, Garcia's click only, through the repetition guard.
   - **The post-it.** Show it only when a rule fires; otherwise hide it. Two rules:
     - **Weak videos:** videos aged ≥ 1 day with < 25 % of their format's normal. List up to 3 by topic, and say their tier, as in the mock.
     - **No weak videos, but one at ≥ 2× normal this week:** name it, as a positive note.

     Bubi `bien_hecho` sits on its corner.
7. **What Inicio shows today moves down** into a closed expander, «Detalles». That covers the census lines, the history and anything else not listed above. Nothing is deleted.

## §3 — Revisar

Build the mock's Revisar.

1. **Header:** «Revisar», and «N vídeos esperan tu visto bueno. Al aprobar, se programan solos en el siguiente hueco.», with a pager «‹ 1 de N ›».
2. **The left column** shows the video.
   - **Frame 0, large,** with the badge «Fotograma 0 · lo que se ve en el feed». Clicking ▶ swaps in the playable video; reuse `lazy_video`.
   - **Under it, a 6-frame strip** at 0 %, 25 %, 50 %, 75 %, the outro and the end. Draw it with ffmpeg (free) once per MP4 and cache it next to the sidecar.
3. **The verdict card** is a sticker.
   - **The header:** the format, the design variant and the item count; then the title; then «Pasa el control de calidad: N de M» or the reason it doesn't.
   - **Six checks**, each from the sidecar or gate record:

     | Check | Source |
     |---|---|
     | volume | LUFS |
     | voice and text in sync | the largest offset |
     | Spanish vowels | STEP 81 §5 |
     | always some movement | the longest still stretch |
     | new words | the repetition guard |
     | clean title and text | STEP 80 §0 |

     A missing value shows «sin dato» in grey, never a tick.
4. **The editor card:**
   - the title with its count out of 100, the description and the hashtags, using the existing `review_metadata_editor`;
   - the platform toggles (YouTube, Facebook, TikTok «a mano»);
   - the «Sale» box: the next free slot, with «cambiar» to pick another free slot.
5. **Three actions:**
   - **«✓ Aprobar y programar»** (green):
     - it approves the video;
     - it schedules it on the platforms ticked, at the slot shown, through the **same guarded upload path** as Subir: YouTube private with `publishAt`, Facebook as STEP 81 §2;
     - if a platform fails, the video stays in «Por subir» with the reason, and the page says so in Spanish.
   - **«✕ Rechazar»:** it asks for a reason (audio / imagen / texto / otro, plus a free line), then runs the existing `reject_video`. The reason is saved in the sidecar.
   - **«↻ Volver a renderizar»:** it shows the estimated cost first, and runs only after a second click. It uses the existing re-render path, under the locks and caps.

   Beside them: «\$X — lo que costó este vídeo», from the cost log.
6. **«Después:»** — the next video waiting, with its frame 0 and its check result.
7. **Empty state:** «Nada que revisar. Produce el siguiente en Inicio.», with a button.

## §4 — Every other page gets the same look

Crear, Cola, Subir, Lecciones, Rendimiento, Comentarios, Biblioteca, Temas, Programar, Ajustes and Registros:
- the same header: an h1 and one sentence of what the page is for;
- the tokens, cards, tags and buttons from §0;
- tables stay as `st.dataframe`, themed.

No logic changes on these pages. Fix any label still in English.

## §5 — Speed

Keep STEP 80's targets for every page: ≤ 1.0 s warm and ≤ 2.5 s cold. Inicio now reads more, so:
- cache with `st.cache_data`, keyed on file mtimes;
- draw frame 0 thumbnails once.

Report the before and after table for every page.

## §6 — Proofs ($0)

Start your own panel on a spare port with the real data.
- **Screenshots.** Take each page at 1440×900, plus a full-page Inicio and Revisar at device scale 2.
  - Use any free local headless browser: Playwright, or Chrome `--headless --screenshot`. Install nothing paid.
  - Revisar needs a video waiting. If none is pending, copy one already-approved MP4 and its sidecar into a temporary pending folder for the screenshot, then remove it. Don't move Garcia's files.
- **Where they go:** `_audit/stills/STEP83/`.
- **Two side-by-side sheets:** `inicio_vs_mock.png` and `revisar_vs_mock.png`.

Then stop the server.

## Report

Give Claude:
- the commits;
- the suite totals;
- the skills found and used, per section;
- the speed table, before and after;
- the proof paths;
- every place where you differed from the mock, and why;
- what moved into «Detalles» or other pages;
- the working-tree changes you left alone;
- $ spent, which must be $0;
- anything not verified.

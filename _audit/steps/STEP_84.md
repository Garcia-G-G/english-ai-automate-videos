# STEP 84 — Every page of the panel looks like the mock, and the stats become charts

Garcia, after STEP 83:

> hicimos un diseño que le dio respiro al landing pero las demás cosas siguen siendo horribles, parecen del siglo pasado. Necesito que las estadísticas sean más gráficas (con números) … necesito que todo tenga un diseño más impresionante.

Claude reviewed your STEP 83 proofs (`_audit/stills/STEP83/`). Inicio and Revisar moved in the right direction, but every other page is still default Streamlit:
- grey inputs and radio buttons;
- English labels («Add to Queue», «Quick Batch», «Delete», «Search by name…», «Showing 1–9 of 79 videos», «Total Videos», «Total Size»);
- Rendimiento is only tables.

This STEP fixes that.

The new mockups are in `_audit/design/panel/`, alongside Inicio and Revisar:
- `panel_rendimiento.png`
- `panel_cola.png`
- `panel_crear.png`
- `panel_biblioteca.png`
- `panel_componentes.png` — how every Streamlit control must look.

The HTML for each is in `mock/`. **`mock/charts/build_rend.py` draws every chart of Rendimiento as plain SVG from `mock/charts/rend.json`.** Port that code; don't redraw the charts from the PNG. The rule from STEP 83 still holds: where this text and the mock disagree, the mock wins. Every number comes from real data; the mocks' agenda, job and A/B values are only illustrative.

## Rules, as always

- One commit per section with its tests. Push each one.
- Run the full suite with `VIDEO_RENDER_WORKERS=2` and no pytest parallelism. Stop on failure and report.
- No attribution lines.
- **No paid call from you.** Tests mock every HTTP layer. YouTube Data and Analytics reads are free quota, and only happen in the existing refresh.
- Don't touch Garcia's panel on 8501. For proofs, use your own server on a spare port.
- Commit only your own files.
- **Never show invented data.** A missing value is «sin dato» in grey.
- **No new paid dependency.** Altair/Vega-Lite ships with Streamlit and is allowed. Plain SVG strings through `st.html` are preferred, because they match the mock exactly.
- **Every insight sentence is computed from the data with a rule.** None is hard-coded text. If a rule doesn't fire, the sentence is hidden.

## Skills — use these explicitly (Garcia's instruction)

Before §0, say which of these you have. Invoke each one at the step named below. If one is missing, say so in the report and follow its intent by hand.

**Every section:**
- `agent-protocols:planning-and-task-breakdown` — at the start of the STEP.
- `agent-protocols:incremental-implementation` — while building each section.
- `mattpocock-skills:tdd` — write the failing test first, for every computed number and rule.
- `mattpocock-skills:diagnosing-bugs` — whenever a test or a page fails, before changing code.
- `agent-protocols:code-review-and-quality` — on your own diff before each commit.
- `agent-protocols:git-workflow-and-versioning` — for each commit and push.

**This STEP:**
- §0 and §1, fidelity and controls:
  - `frontend-design:frontend-design`;
  - `ui-design-review:ui-polish`;
  - `vectorlab-ux-skills:forms`;
  - `vectorlab-ux-skills:surfaces`;
  - `hzblj-skills:ui-interactions`.
- §2, the charts:
  - `dataviz` — read it before writing the first line of chart code;
  - `vectorlab-ux-skills:typography` — tabular numbers.
- §3–§5, the pages:
  - `hzblj-skills:ui-surfaces`;
  - `vectorlab-ux-skills:empty-states`;
  - `vectorlab-ux-skills:loaders`;
  - `design:ux-copy`.
- §6, the remaining pages:
  - `uxkin:no-ui-slop`;
  - `vectorlab-ux-skills:anti-slop`.
- §7, speed: `agent-protocols:performance-optimization`.
- §8, proofs:
  - `design:design-critique` (or `ui-design-review:ui-review`), on every screenshot against its mock;
  - `design:accessibility-review` — contrast of every chart label.

## §0 — Fix what STEP 83 left behind

1. **Fonts.** Your screenshots render in Streamlit's default Source Sans, not Fredoka and Manrope. That is the biggest single reason the panel still looks old.
   - Serve `assets/fonts/` as static files:
     - set `server.enableStaticServing = true` and copy the fonts or symlink them into `static/`, then use `@font-face` with `app/static/...`;
     - or use `[[theme.fontFaces]]` in `.streamlit/config.toml` if your Streamlit supports it.
   - Set Manrope as the theme font and Fredoka for headings.
   - **Test:** the computed `font-family` of an `h1` and of a widget label, read from the page by your headless browser.
2. **Cola's numbers disagree.** The sidebar says 491, and the page says «Queue (0 waiting) · Queue is empty». Fix it in §3.
3. **Inicio and Revisar are narrower and smaller than the mock** (see `inicio_vs_mock.png`). Use the mock's sizes:
   - main column max-width 1200 px with 40 px padding;
   - card padding 22–26 px;
   - h1 38 px;
   - hero title 30 px;
   - preview 196 px wide.
4. **Every English label left in the panel becomes Spanish.** Grep the page code for English UI strings and list them in the report.

## §1 — Every Streamlit control dressed (`panel_componentes.png`)

One CSS block, driven by the tokens, styles every native control on every page:

| Control | How it looks |
|---|---|
| `text_input`, `text_area`, `number_input`, `selectbox`, `multiselect` | fields with 1.5 px line borders, radius 12 and the field background; focus is a 2 px blue border plus a 4 px blue-soft ring; labels are small uppercase muted |
| `number_input` | its − / + steppers are small sand squares |
| `st.radio` used as a choice | becomes `st.segmented_control` (or `st.pills`) styled as the sand segmented control |
| checkboxes that are on/off settings | become `st.toggle`, green when on |
| `st.tabs` | a 3 px blue underline on the active tab |
| `st.expander` | a bordered card with its chevron on the right |
| `st.info` / `success` / `warning` / `error` | the four tinted alerts from the sheet |
| short confirmations | `st.toast`, dark, with the topic in yellow |
| `st.dataframe` | the table style: uppercase muted headers, row lines, numbers right-aligned in Fredoka. Where a table is short (≤ 15 rows), render it as an HTML table in that style instead. |
| empty states | the dashed card with Bubi `bien_hecho`, a title and one line |
| loading | the skeleton bars |

Add a hidden page `?page=componentes` that renders all of them, for the proofs.

## §2 — Rendimiento: charts with numbers (`panel_rendimiento.png`)

Port `mock/charts/build_rend.py` into `src/panel/charts.py`. It contains pure functions: data in, an SVG string out. Unit-test each one. Then build the page top to bottom.

1. **Header.** The segmented control «7 días · 28 días · Todo» changes the period of the scoreboard. Beside it, the «Actualizado · hace N h» chip.
2. **The scoreboard**, an ink card with a blue offset shadow:
   - the big number is the views in the period;
   - the yellow pill compares them with the previous period of the same length, «▲ ×N» or «▲ +N %». It is red with ▼ when the period is down;
   - four mini cards: total views, subscribers gained (+ this week), likes, shares;
   - at the right, the daily-views area chart: a yellow line with a gradient fill, the peak labelled, the last point as a white dot, and blue ticks under the axis for the uploads of each day.
   - **Daily views data:** use the `senal` reader (`output/senal/senal.json`, YouTube Analytics `day` dimension). Run it in the same automatic 20 h refresh as the stats (STEP 81 §1.1). If Analytics isn't available, derive daily views from the differences between consecutive `output/stats/youtube_*.json` snapshots, and say so under the chart.
3. **«¿Qué formato rinde?»** One row per format with ≥ 2 videos aged 3 days or more. Each row has:
   - its name, the number of videos, its views and its subscribers;
   - a bar of median views, in the format's colour, with the number inside;
   - «vs CSD» as a percentage;
   - average % viewed, as a small ring.

   The insight box shows the top format's share of the daily mix, from `daily_mix`.

   Format colours:

   | Format | Colour |
   |---|---|
   | Cómo se dice | `#1F6FD1` |
   | Test | `#FF6F4F` |
   | Frases | `#12854F` |
   | Vocabulario | `#2BB5A8` |
   | Dilo en inglés | `#8A5CD6` |
   | Series | `#E9A100` |
   | grammar and others | `#A59C90` |

   Put the colours in the tokens.
4. **«¿De dónde vienen?»** A donut of traffic sources from senal: Shorts feed / search / outside YouTube, with a legend in %. The note under it is rule-based: if the Shorts feed is > 80 %, show the sentence in the mock.
5. **«Tablero vs cuaderno».** The STEP 82 §4 A/B: «N de 6» per variant, counting videos aged ≥ 3 days, as two progress bars. When both reach 6, show the verdict («Tablero +N %» or the red loss flag from STEP 82).
6. **«Un “Cómo se dice”, día a día».**
   - **The chart:** columns for days 1–15, the median daily views of `how_do_you_say` videos aged ≥ 15 days. The first column is blue; the rest are light blue.
   - **The big figure:** «N % de sus vistas llegan el primer día».
7. **«¿A qué hora le va mejor?»**
   - **The chart:** median views by publish hour, in America/Costa_Rica, for videos aged ≥ 3 days.
     - Hours with < 5 videos are drawn in light grey.
     - The best hour with ≥ 5 videos is green and labelled.
     - Dashed lines mark the 4 publishing slots.
   - **The big figure:** the best hour.
   - **Do not move the slots automatically.** If the best hour is ≥ 1.5× the median of the slot hours and has ≥ 10 videos, add a line: «Podrías probar un hueco a las HH:00 (en Programar)».
8. **The scatter.**
   - **The axes:** each dot is a video aged ≥ 3 days; x = average % viewed (cap the axis at 140 %, and clamp values above it to the edge), y = views.
   - **The dots:** coloured by format, with `how_do_you_say` larger, plus the dashed line at 100 % and its label.
   - **Hover:** a `<title>` with the video's title and numbers.
9. **Top 10 of all time:** rank, emoji, short topic, a bar and views. The first bar is yellow. The note is rule-based: «Los 10 son …» only if all 10 share a format.
10. **What the page shows today moves into a closed expander, «Tablas»,** at the bottom: the format table, top 10, bottom 10 and views by category. The Facebook `read_insights` error becomes a warning alert with the STEP 81 §6 how-to, not raw text.

## §3 — Cola (`panel_cola.png`)

1. **Header:** «N guiones esperan turno. Salen solos en este orden, 4 al día.» N is the same number as the sidebar badge, from `queue_guard().queued_scripts()`.
2. **«Combustible»: five gauges.**
   - The five groups:
     - Cómo se dice (with sequels);
     - Frases and vida real;
     - Series «RETO»;
     - Test de nivel;
     - Gramática y otros.
   - Each shows the scripts left, and the days they last at the current `daily_mix` rate.
   - **Thresholds:**
     - < 14 days: the sticker style (ink outline, offset shadow) with the coral tag «Se acaba pronto · escribe más»;
     - > 60 days: green «De sobra»;
     - grammar: «Al final de la cola».
   - The bar fills to days/30, capped at 100 %.
3. **«Así se llenan los huecos»:** the next 8 scripts in production order. Each row has:
   - the position;
   - frame 0 (reuse STEP 83's cached thumbnails);
   - the title and the format;
   - tags (sequel and parent views, tier, «otro hueco»);
   - a priority bar with «prioridad = formato × tema × frescura» in numbers;
   - the slot it fills.

   The first row is highlighted yellow. «Ver los N →» opens the full list, paginated by 50.
4. **«3 + 1»:** the day's mix as one stacked bar, with its legend.
5. **«Fuera de la cola»:** two dashed trays with the counts of `_rewrite/` and `_skipped/`. Each opens its `README.md`.
6. **Header buttons:**
   - **«＋ Añadir guiones»** opens an `st.dialog`. It holds the old batch tools (quick batch, custom type + count), translated. They are the same functions, under the same rules.
   - **«⇅ Reordenar»** lets Garcia pin one script to the top. That is the only manual reorder.

## §4 — Crear (`panel_crear.png`)

1. **«1 · Formato»:** a grid of format cards, 3 per row, each with:
   - its gradient tile and emoji;
   - its name and a one-line description;
   - **«rinde»:** the format's median views (`channel_stats`);
   - **«cuesta»:** the median cost per video of that format from `output/costs/`, or «sin dato».

   The selected card has an ink outline, a blue offset shadow and a blue tick. Formats below 25 % of the top median are shown dimmed, but stay selectable.
2. **«2 · Tema»**, a sticker card:
   - the segmented control «Al azar · Categoría · Tema concreto»;
   - the category pills with their best views in small type;
   - the primary button «▶ Crear vídeo»;
   - under it: «~duración · ~\$coste · listo en ~N min · voz por <provider>».

   The existing «Opciones» stay in a closed expander under the pills.
3. **«En marcha»:** while a job runs, show:
   - its frame 0;
   - its title and its time («empezó hace N s · faltan ~N s», from the median of past jobs);
   - five step bars: Guion, Voz, Montaje, Sonido, Control. Read them from the job's state; if the job state doesn't expose steps, add that to `jobs.py`;
   - the last 3 log lines in plain Spanish.

   The finished and failed jobs stay in Inicio, as today.

## §5 — Biblioteca (`panel_biblioteca.png`)

1. **Header,** then three stat pills: videos on disk, GB used, total views.
2. **Filters:**
   - chips for Todos, Cómo se dice, Frases, Tests, Series and Otros, each with its count;
   - a search box at the right, matching the title and the English words;
   - a sort option: «Recientes · Más vistos».
3. **The grid:** 5 cards per row, 20 per page. Each card has:
   - the real frame 0 of the MP4, cached as a thumbnail, 9:16 with radius 12;
   - a status badge at the bottom left (Publicado, Programado, En revisión or Rechazado) and the duration at the bottom right;
   - the title;
   - the views with a mini spark of days 1–3 from senal, or «—» when it's not published;
   - when it was published or is scheduled;
   - **«▶ Ver»**, which opens the video in an `st.dialog`;
   - **«⋯»**: Descargar, Ver en YouTube, and Borrar. Borrar asks for confirmation and uses the existing delete.
4. **Empty search:** the empty state, «Nada con “…”».

## §6 — The other pages

Subir, Comentarios, Temas, Programar, Ajustes, Registros and Lecciones get §1's controls plus one visual element each:

- **Programar:** a week grid (7 days × the 4 slots), with each slot's frame 0 or «libre».
- **Comentarios:** one card per comment, with the initial of the author in a circle, the video's frame 0, the comment, and the suggested reply in an editable field with «Responder».
- **Subir:** a card per platform with its state (conectado / falta permiso / a mano) and the videos waiting.
- **Temas:** category tiles coloured by tier (A, sequel, C), with their best views.
- **Ajustes:** grouped cards with toggles.
- **Registros:** a vertical timeline.

No logic changes.

## §7 — Speed

Use STEP 80's targets on every page: ≤ 1.0 s warm, ≤ 2.5 s cold. The SVG charts are cached with `st.cache_data`, keyed on the stats file's mtime and the period. Report the before and after table.

## §8 — Proofs ($0)

Screenshot every page at 1440×900, and the five mocked pages full-page at device scale 2. Save them to `_audit/stills/STEP84/`.

Add one side-by-side sheet per mocked page (`<page>_vs_mock.png`) and the component page. Run `design:design-critique` on each sheet and fix what it finds before reporting.

## Report

Give Claude:
- the commits;
- the suite totals;
- the skills used per section;
- the font test result;
- the English strings you translated;
- the speed table;
- the proof paths;
- every difference from the mocks, and why;
- what moved into expanders or dialogs;
- $ spent, which must be $0;
- anything not verified.

# STEP 57 — The panel, second layer: Spanish, human, and fast to scan

## What the owner asked (2026-10-14)
"A redesign layer for the web, and give the page's performance a breather too."

## Already done (8fb52e6) — build on it, don't redo it
Brand theme in `.streamlit/config.toml` (one light theme, so the Mac's appearance setting
no longer decides), the custom CSS rewritten on brand tokens (sand, white cards, ink,
English blue, yellow only as highlighter, Fredoka/Manrope), Spanish sidebar with Material
icons, Spanish page titles. Before it, in light mode every label was dark grey on navy.
Screenshots: `tools/ui/shoot_pages.py` (real browser, light and `--dark`).

## Findings from a page-by-page critique (screenshots of every page, both OS themes)
| # | Finding | Severity | Fix |
|---|---|---|---|
| 1 | Half the UI is still English: Configuration, Video Type, Topic Selection, Random/Select Category/Specific Topic, Options, Generation Status, Recent (Last 5), Connected Platforms, NOT CONFIGURED, publishes as…, "No approved videos ready…" | High | One Spanish copy pass over every page; keep code identifiers out of labels. |
| 2 | Raw type ids shown to the owner: `educational`, `how_do_you_say`, `(quiz)` | High | Use `type_label()` everywhere a type is shown (select boxes, recent list, library). |
| 3 | Developer bookkeeping on Inicio: «0 en la lista · 0 contados en disco por separado ✓», «(0/0) releídos de los sidecars», folder paths `output/video/`, the intro sentence about artifacts | Medium | Keep the counts as the big number; move census lines and paths into one «Detalles técnicos» expander per section. Show a mismatch only when there IS one (red line). |
| 4 | Cost line is one sentence with inline-code pills | Medium | Three metric tiles: «Hoy», «Este mes» (with the $25 ceiling as a progress bar), «Media por video». |
| 5 | Recent jobs as ✅ + title + `(type)` expanders | Medium | A compact list: status pill (Hecho / Falló / En curso), Spanish type label, time, cost. |
| 6 | Lecciones (Manim) opens with the «Entorno» block expanded: install commands, key fields, paths | High | Collapse it to one status line («Todo listo» or what is missing); the page starts with the work: pick lesson → generate audio → render → upload (STEP 56 panel). Keys move to Ajustes. |
| 7 | Upload page: emoji platform cards, Shorts only | Medium | Two tabs: «Shorts» and «Lecciones largas» (STEP 56). Platform status as pills with a «Conectar» action. |
| 8 | 11 pages in two groups, equal weight | Low | Group by how often he uses them: **Producción** Inicio, Crear, Lecciones, Revisar, Subir · **Archivo** Biblioteca, Temas · **Sistema** Cola, Programar, Ajustes, Registros. Keys unchanged. |
| 9 | Emoji in content (status ✅, 💸, 🎵 ▶️ 📷) | Low | Material icons or plain text; emoji only inside user content (titles of videos). |
| 10 | Sidebar buttons spaced ~53 px apart | Low | Tighten to ~40 px; keep ≥ 36 px targets. |

Accessibility: after 8fb52e6 body text is ink on sand (≈15:1); keep muted text at #6D665B
or darker (≥ 4.5:1 on sand); never yellow text.

## Performance (measure in the browser with tools/ui/shoot_pages.py, before and after)
Measured 2026-10-14 in a clean copy: most pages 3–5 s to "not running" in a real browser
(includes Streamlit's own ~2 s), **Crear 21.6 s on the first load**: the queue audit
re-judges every queued script when the code signature changed, and the page waits for it.
1. Run the audit in a background thread at server start (`st.cache_resource` or
   dashboard_state), and let Crear draw immediately with «comprobando la cola…»; the guard
   still runs `fresh=True` before handing out a script.
2. Subir: render the platform cards and the list first; videos and download buttons stay
   lazy (de83198). Count the widgets per page and report them (Subir had 71 buttons).
3. Lecciones: environment checks (`manim --version`, ffmpeg, key presence) cached once per
   process, not per click.
4. Report per page: first load and rerun, before/after, light theme.

## Proof
Before/after screenshots of every page (light) in `_audit/stills/ui/`, the timing table,
tests green. No behaviour change: page keys, buttons and flows do the same thing.

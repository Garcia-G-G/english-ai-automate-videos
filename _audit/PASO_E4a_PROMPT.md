# E4a — el Inicio deja de contar y empieza a mostrar trabajo

**Un solo paso.** No es E2, ni E3, ni el resto de E4. Una página.

---

## El diagnóstico

El operador dice que el dashboard se siente **"abstracto"**. Es distinto de "indie", y es más útil.

El Inicio actual muestra: Total Videos · Pending · Approved · Uploaded · Active Jobs · **Storage MB** · "By Type 40%" · badges de plataformas · Recent Activity.

**Todo son agregados sobre el sistema.** Ninguno es un artefacto sobre el que puedas actuar. Por eso se siente abstracto: te dice *cuántos hay*, no *qué hacer* ni *qué pasó*.

Los datos para lo contrario ya están todos en disco.

---

## PROMPT

````
You are in ~/Downloads/english-ai-videos. HEAD is df3e4df.

ONE PAGE. Not E2, not E3, not the rest of E4. The operator asked to go step
by step and this is the step.

THE PROBLEM

He calls the dashboard "abstract". He is right, and the word is precise. The
Inicio page shows Total Videos, Pending, Approved, Uploaded, Active Jobs,
Storage MB, "By Type 40%", platform badges. Every one is an AGGREGATE ABOUT
THE SYSTEM. None of them is an artifact he can act on.

THE RULE FOR THIS PAGE

Every block names artifacts and their next action. If a block cannot say
"these N specific videos, and here is what to do with them", it does not
belong on Inicio.

Storage MB, Total Videos, Video Types and the By Type percentages go. Nobody
acts on them.

WHAT TO BUILD — the real state, verified on disk right now

  11  batch artifacts in output/video/ not yet promoted  -> "Promover"
   8  awaiting review in output/pending/                 -> "Revisar"
       of which 3 carry gate PASS and 7 have NO gate record (they predate D0)
   2  approved, not uploaded                             -> "Subir"
  17  rows in the publication ledger                     -> link to YouTube

Each row: the artifact's name, its type, a thumbnail, and the one button that
moves it forward. Videos with no gate record show "sin registro" — NOT a green
tick. Absence stays visible; that is the whole lesson of D0.

Anything in flight keeps its live progress block. Anything that failed says
so with its reason, and links to its log file (job["log_path"] is already on
the row).

THUMBNAILS
  There is no thumbnail machinery. Do not put st.video in a list — a player
  per artifact makes the page heavy. Extract one frame per artifact with
  ffmpeg, cache it next to the mp4, and reuse it. Generate on demand, once.

COST
  One line: what today cost, and the running total against the ceiling in
  config. Read output/costs/*.jsonl. Not the full Costes panel — that is D3.
  One line.

PROOF

  P1. Screenshot of the new Inicio.
  P2. Every count on the page must match an INDEPENDENT count from disk —
      compute it separately and show both. The numbers above are today's; if
      yours differ, say why before shipping.
  P3. Confirm the 7 artifacts with no gate record render as "sin registro"
      and not as passing.
  P4. Full test suite. Report the count.

OUT OF SCOPE
  - E2, E3, E5, and the navigation regrouping. One page.
  - The Costes panel (D3) and the Registros page (D4).
  - Removing the emoji navigation — that is E5.
  - Deleting anything under output/.
````

---

## Lo que espero que salga

Que los 7 "sin registro" sean los pendientes viejos y que la página quede honesta pero fea en esa columna. Bien. Es preferible a un ✅ que no significa nada — y se vacía sola según se revisen.

# Paso D — el dashboard deja de tirar lo que el pipeline calcula

**Leído contra `HEAD f112b2f`.** Base: `_audit/DASHBOARD_AUDIT.md`.

Decisiones tomadas: **D1 + D2 + D3 + D4**, y el Scheduler por la **opción A** (quitar los controles falsos, conservar "Generate Batch Now").

---

## Dos cosas que descubrí al planear esto y que cambian el diseño

### El botón "Clear All History" destruye la evidencia

`admin.py:2434` borra `jobs["history"]` entero. Si el veredicto del gate y el fondo viven **solo** en la fila del job, ese botón los borra para videos que siguen esperando en `pending/`.

Por eso el registro va al **JSON del artefacto** (`admin.py:365-376`, el `meta_path` que Review ya lee), y en la fila del job solo como conveniencia. El artefacto y su veredicto viven o mueren juntos.

### La clave de unión con el coste ya existe

El ledger graba `video_id: "hang_in_there_20260820_192325"` y el artefacto es `hang_in_there_20260820_192325.mp4`. Es `unique_name` en los dos sitios. **No hay que inventar ninguna correspondencia** — se filtra `output/costs/*.jsonl` por `video_id`.

---

## PROMPT — Paso D

````
You are in ~/Downloads/english-ai-videos. HEAD is f112b2f. F2 is landed and
verified.

THE FINDING

The dashboard is not missing features. The pipeline computes things and the
screen throws them away. Five instances, all verified in the live ledger:

  1. finalize_video returns gate/blocking_flags/outro_appended. admin.py:358-360
     puts them in `result`. _worker() at :448 calls the function WITHOUT
     capturing the return. `result` dies there.

  2. A gate REJECT does not raise (pipeline.py:610-614). admin.py:379 calls
     complete_job(success=True) regardless. output/generation_jobs.json has a
     real case: topic "on the house", status "completed", current_step
     "Gate: REJECT". It landed in output/pending/ with a green tick, no outro,
     no Learning Routes CTA, next to the ones that passed. The Review page
     shows script + metadata + video and NOT the verdict.

  3. update_job(job_id, background=payload) is written by f112b2f — whose own
     commit message says it is "so the dashboard can show which background a
     video got". grep 'get("background")' src/admin.py returns ZERO.

  4. 488 entries in output/costs/ totalling $3.1223. No page shows a dollar.

  5. _worker() records log_path on the job row (:443). The Logs page never
     opens the file. grep "\.log" inside that page: zero.

This is the repo's dominant failure applied to the UI. Fix the shape, not
just the symptoms.

TWO DESIGN CONSTRAINTS I FOUND WHILE PLANNING — do not design around them

  A. "Clear All History" (admin.py:2434) wipes jobs["history"]. If the gate
     verdict and background live ONLY on the job row, that button destroys
     the record for videos still sitting in pending/.

     So the record goes in the ARTIFACT's json — the meta_path already
     written at admin.py:365-376, which Review already reads. The job row
     gets a copy for convenience only. Artifact and verdict live or die
     together.

  B. The cost join key already exists. The ledger records
     video_id: "hang_in_there_20260820_192325"; the artifact is
     hang_in_there_20260820_192325.mp4. Both are `unique_name`. Filter
     output/costs/*.jsonl by video_id. Do NOT invent a mapping.

TASK — one commit each, push after each

  D0. THE RECORD (no UI yet).
      run_pipeline_with_tracking writes into meta_path, alongside what it
      already writes: gate, blocking_flags, outro_appended, outro_variant,
      and the background payload the resolver reports. Copy the same onto the
      job row.

      Keep `result` populated for programmatic callers, but it must no longer
      be the ONLY home for this — that is what got us here.

      Do NOT change complete_job's success flag for a gate REJECT. "failed"
      means the pipeline crashed; a rejected video is a successful render of a
      bad artifact, and merging them would corrupt the failed count (today 23
      of 51). The verdict is a separate field, not a status.

      Do NOT move the rejected file. Where artifacts live is a separate
      decision and I have not made it.

  D1. REVIEW SHOWS THE VERDICT.
      For each pending video, read its meta json and show, above the player:
        - gate PASS / REJECT / NO_REPORT, unmissable
        - the blocking_flags on a REJECT, in words
        - whether the outro is on it (and which variant)
      A REJECT gets a red banner and its Approve button goes behind an
      explicit confirm. It must be impossible to approve a rejected video by
      reflex.

      Dashboard "Recent Activity" (:1349-1365) currently draws ✅ from
      status == "completed", so a gate REJECT shows green. Distinguish it.

  D2. BACKGROUND AND COST PER VIDEO.
      In Review and in the Logs expander, show for each video:
        - background: generated or palette, the gate ratio, and what the image
          cost — including the case that cost money and was refused
          (the ledger has one: palette/REJECT $0.041)
        - that video's total cost, from the ledger, by video_id

  D3. COST PANEL.
      A new page. Put the reading logic in a small src/cost_report.py with
      tests; keep the Streamlit page thin. Show: total, by api_type, by day,
      by video, and progress against a ceiling (default 15.0, configurable in
      config.yaml — do not hardcode it in the page).

      VISIBILITY ONLY. No spend enforcement, no daily cap, no blocking. That
      is step 5 and I have not asked for it.

      While you are in there, ANSWER THIS, do not fix it silently:
      openai_chat totals $0.0037 across 38 videos — $0.0001 per script
      generation, which is not credible. Is script generation being recorded
      at all? There is logged debt saying cost_tracker used to drop
      openai_chat. Report what you find as a finding. If it needs a fix, tell
      me and I will scope it.

  D4. THE LOGS PAGE OPENS THE LOG.
      job["log_path"] is already on the row. Read it in the expander — tail
      the last N lines, with a control to see more. Handle: file missing,
      file large, path from a different machine. A 3am failure must be
      readable here.

  D5. THE SCHEDULER STOPS LYING.
      Remove Start/Stop and the interval control. Remove the now-dead
      scheduler_enabled / scheduler_config session state (:1215-1222,
      :2136-2145) — do not leave them defined and unused, that is the same
      failure we are fixing.

      KEEP "Generate Batch Now" — it calls start_generation and works.
      Retitle the page for what it actually is.

      Do NOT build a real scheduler. That is 5a.

PROOF

  P1. Force a gate REJECT through the DASHBOARD path. Show:
      - the artifact's meta json carrying gate + blocking_flags
      - a screenshot of Review with the red banner and the guarded button
      A description is not proof for a UI change.

  P2. Reconciliation, and this is the one that matters: the cost panel's
      total must equal $3.1223 for the current ledger — computed
      independently, not by calling your own code. If it differs, the
      difference IS the finding; report it before adjusting anything.

  P3. A PASS video: screenshot of Review showing gate PASS, the outro
      variant, the background (generated/palette + ratio + cost), and that
      video's total cost.

  P4. Logs: screenshot of an expander with real log lines from log_path, for
      one of the 23 failed jobs.

  P5. grep proof that scheduler_enabled and scheduler_config no longer exist
      anywhere in the repo.

  P6. Full test suite. Report the count. Nothing that passed may fail.

COST
  One test render (~$0.12) plus whatever P1 needs. Nothing else.

OUT OF SCOPE
  - Visual redesign. The dashboard looks fine; the problem is what it does
    not say.
  - Moving or auto-quarantining rejected artifacts.
  - Spend enforcement.
  - The real scheduler (5a).
  - Ken Burns / motion.
  - Text layout, vocabulary/pronunciation.

HOW TO WORK

D0 first, and show me one meta json before building any UI on top of it. If
pending videos turn out to lack a meta json — Review reads video["meta"] and
guards it with `if video["meta"] and ...`, which suggests some do not have one
— STOP and tell me. The whole join depends on it and I would rather know
before four pages are built on a field that is sometimes absent.

If this overruns, land D0 + D1 + D5 and say you are stopping. The verdict
reaching Review is the one thing on this list that has already cost me a bad
publish; the rest is visibility.
````

---

## Dónde espero que falle

En el `meta` de Review. `admin.py:1531` hace `if video["meta"] and "script_data" in video["meta"]` — esa guarda existe porque **hay videos sin meta**. Si los de `pending/` son de esos, D1 y D2 se construyen sobre un campo que a veces no está, y hay que decidir antes qué se enseña cuando falta: "sin registro" es honesto, ✅ verde es la mentira que estamos arreglando.

Por eso el prompt corta ahí y pide ver un meta json antes de tocar la UI.

## Lo que esto no arregla

El 45 % de jobs fallidos (23 de 51). D4 hace que la causa sea **legible**; no la arregla. Cuando el log se pueda leer, ese número es el siguiente sitio donde mirar.

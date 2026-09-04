# Paso 5a — Publicación automática de YouTube

**Prompts para Claude Code.** Leído contra el código real en `HEAD 30477ca`, no contra el `AUDIT.md` de julio.

---

## Lo que encontré al releer el código, y que cambia el paso

### 1. Hay un TERCER camino de subida, y es exactamente el que 5a automatizaría

`main.py:137 upload_video()`, alcanzable hoy con `python main.py --batch 2 --upload`. Eso ya **es** 2/día desatendido menos el reloj.

Y ese camino:

| | admin.py (single) | admin.py (bulk) | **main.py --upload** |
|---|---|---|---|
| resuelve metadata con `resolve_upload_metadata` | sí | sí | **no** — `generate_metadata` + `adapt_for_platform` a pelo |
| escribe en el ledger | sí (`_record_upload`) | sí | **NO** |
| respeta ediciones del operador | sí | sí | n/a (headless) |
| errores | `st.error` | `st.error` | `logger.error` dentro de un `except Exception` que traga todo |

Los dos caminos de `admin.py` se unificaron en el commit `0b996bc`. **Este nunca estuvo en el alcance.** Es la misma divergencia del Paso 0 —dos entradas, comportamiento distinto— reaparecida en el sitio donde más duele: el único camino sin operador delante.

**Consecuencia directa:** construir 5a sobre `main.py --upload` tal cual reproduce el bug que el ledger existe para arreglar. Publicarías 2/día y nada en el repo podría nombrar ninguno de esos videos.

### 2. Los helpers del ledger no los llama nadie

`publication_log.py` expone `read_ledger`, `find_by_artifact`, `find_by_upload_id` y `unrecorded_platforms`. Grep en todo el repo: **cero llamadas fuera de `tests/`**.

`unrecorded_platforms(artifact, platforms)` es literalmente el primitivo de idempotencia, ya escrito y ya probado. No lo usa nadie.

### 3. La ventana de duplicado es concreta y tiene nombre

La secuencia en los tres caminos es: subir → ¿éxito? → registrar. Entre esos dos pasos el video ya está vivo. Si el registro falla, `PublicationRecordError` sube, y el estado en disco es indistinguible de "nunca se subió". El siguiente intento sube otra vez. Eso es `hPdSoqjvu3E` / `IvO969ZeQsM`.

Y hay un primitivo del protocolo sin usar: YouTube arranca una sesión reanudable y devuelve su URI en la cabecera `Location` (`uploader.py:728`). **Esa URI se descarta en todos los caminos de fallo** (`:725`, `:730`, `:768`, `:770`). Reanudar esa misma sesión no crea un segundo video; abrir una nueva sí.

---

## PROMPT 1 — Unify the third upload path

````
You are in ~/Downloads/english-ai-videos at HEAD 30477ca, 276 tests passing.

CONTEXT YOU NEED BEFORE TOUCHING ANYTHING

Commit 0b996bc unified the two upload paths in admin.py behind
resolve_upload_metadata, so the record and the request could not describe
different text. There is a THIRD path that was never in that scope:

  main.py:137  upload_video(video_path, video_type, script_data, platforms)
               reached by:  python main.py --batch N --upload
               called from: main.py:272 (run_pipeline)

It calls generate_metadata + adapt_for_platform directly (main.py:159-172),
builds a VideoMetadata, and calls manager.upload(). It NEVER calls
record_publication. Confirmed by grep: publication_log has zero callers
outside tests/.

This is the path that unattended publishing would run. Built on as-is, 5a
publishes 2 videos a day that nothing in this repo can name — the exact defect
the ledger was written to fix, reintroduced at the one place with no operator
watching.

TASK

  a. Make main.py's upload path record every publication in the ledger, with
     the POST-adaptation strings actually sent — same contract
     publication_log.record_publication documents in its docstring. Reuse
     admin._record_upload's logic; do not write a second recorder. If it is
     Streamlit-coupled, extract the non-UI part rather than copying it.

  b. Decide whether main.py should also go through resolve_upload_metadata.
     It takes st.session_state, which does not exist headless. Read it first
     (admin.py:481). Either give it a headless mode with an explicit
     "no operator edits" argument, or state clearly why the two resolvers must
     stay separate. I want the reasoning, not just the change.

  c. main.py:200-203 wraps the whole function in `except Exception` that logs
     and returns. In batch mode that means an upload failure is a log line and
     nothing else — no file moved, no record, no non-zero exit. Fix the
     swallowing here; the batch-level failure policy is PROMPT 3, so do not
     build the reporting machinery yet. Just stop losing the error.

PROOF
  - A table of the three upload paths (admin single, admin bulk, main.py)
    across: metadata resolver used, ledger written, error visible where.
    Before and after.
  - A test that runs main.py's upload path with the API stubbed and asserts a
    ledger row exists afterwards with the post-adaptation title.

OUT OF SCOPE
  - Idempotency. That is PROMPT 2 and it needs this path recording first.
  - Scheduling.
  - TikTok and Instagram behaviour changes.
  - Do NOT start 6a.

GIT: one commit, push after.
````

---

## PROMPT 2 — Idempotency

**Por qué va segundo:** una guarda de idempotencia que consulte el ledger no sirve de nada mientras haya un camino que publica sin escribir en él. El Prompt 1 cierra esa fuga; este pone la guarda.

````
Same repo. PROMPT 1 is done: all three upload paths now write to the ledger.

THE DEFECT

hPdSoqjvu3E and IvO969ZeQsM are the same video, published 3 minutes apart,
first private then public — a retry that left the first one live. At 2/day
unattended that stops being an accident and becomes routine.

The window is structural, not a race in one function. Every path does:

    result = manager.upload(...)      # the video is now LIVE
    if result.success:
        record_publication(...)       # may fail; may never be reached

Between those two statements the video exists on YouTube and nothing on disk
says so. A retry cannot tell that state apart from "never uploaded".

TWO PRIMITIVES ALREADY EXIST AND ARE UNUSED

  1. publication_log.unrecorded_platforms(artifact, platforms) — the guard,
     already written and already tested. Zero callers repo-wide.

  2. YouTube's resumable session URI. uploader.py:728 reads it from the init
     response's Location header into `upload_url`, and every failure path
     (:725, :730, :768, :770) discards it. Resuming that same URI does not
     create a second video; starting a new session does. Read Google's
     resumable upload docs on querying an interrupted session
     (PUT with Content-Range: bytes */<size>) before designing anything.

TASK

  0. FIRST, one cheap question that gates nothing but should be answered while
     you are in this code. _build_fallback_title re-randomises per platform;
     it is recorded in docs/recorded-debt.md as unreachable because every
     recent script carries video_title. That is a property of the DATA, not the
     code.

     Does the pydantic schema from Step 1 make video_title REQUIRED for the
     types that --batch renders? Step 1 documented a mismatch exactly there —
     the true_false prompt demands video_title and real output did not carry
     it. If it is required, the debt can stay asleep. If it is optional, it
     fires the first time GPT omits it, unattended. One line either way.

  a. Persist an ATTEMPT before a single byte is uploaded, not only a success
     after. Decide the shape — an attempt row in the same ledger with a status
     field, or a separate attempts file — and justify it against the
     append-only reasoning in publication_log's module docstring.

     The attempt record must carry whatever is needed to answer, on the next
     run: "did this already publish, and if the answer is maybe, how do I find
     out?" For YouTube that includes the resumable session URI.

  b. Guard every upload call site with it. unrecorded_platforms is the obvious
     starting point; say whether it is sufficient or whether the attempt state
     needs its own query.

  c. When an attempt exists but no success was recorded, do NOT blindly retry
     and do NOT blindly skip. Query the platform: for YouTube, the resumable
     session URI tells you whether the upload completed, and get_upload_status
     (uploader.py:772) can confirm a video id. Reconcile, then decide.

  d. SECOND VECTOR, added after PROMPT 1's report. main.py never moves the
     uploaded file the way move_to_uploaded does for the dashboard — it was
     never implemented on that path, not lost to the swallowing.

     Consequence: an already-published video stays sitting where the dashboard
     lists it as pending, so the operator can upload it again by hand. That
     duplicate route goes through a human and the ledger guard in (b) does not
     see it unless the dashboard consults the ledger before listing.

     Decide whether the fix is moving the file, having the pending list consult
     the ledger, or both. Say which and why. A guard that only covers the
     automated path leaves the manual one open, and the manual one is how the
     first duplicate happened.

PROOF — three cases, all as tests with the HTTP layer stubbed
  T1. Same artifact uploaded twice in a row -> exactly one publication.
  T2. Upload succeeds, recording raises PublicationRecordError, process dies.
      Next run must NOT publish a second copy. This is the case that produced
      the live duplicate; if only one test survives review, make it this one.
  T3. Upload genuinely failed (init 500, no session started) -> the retry DOES
      publish. An idempotency guard that blocks legitimate retries is worse
      than the duplicate, because it fails silently and forever.

  Negative control: disable the guard and show T1 and T2 fail.

REPORT
  Which key you chose (artifact name, content hash, client token, session URI)
  and why. Name the case your choice does NOT cover — every one of these has
  one. I would rather see the hole documented than discover it at 2/day.

OUT OF SCOPE
  - Scheduling.
  - Instagram and TikTok idempotency beyond making the same guard apply to
    them. TikTok is still blocked on external audit and publishes private-only;
    do not invest there.
  - Do NOT start 6a.

GIT: one commit, push after.
````

---

## PROMPT 3 — Unattended failure behaviour

**El cambio de contexto que hace esto necesario:** R1 subió `fill_blank` de 1 a 9 llamadas TTS por video. Con un operador delante, un fallo es un mensaje rojo en pantalla. Sin operador, un fallo es una línea en un log que nadie lee, y el video no existe.

````
Same repo. PROMPTS 1 and 2 are done.

WHAT CHANGED THE STAKES

R1 took fill_blank from one combined options TTS call to nine calls per video.
More per-call failure surface, and now nobody is watching when it fires.

CURRENT BEHAVIOUR — establish it before changing it

  uploader.UploadManager.upload_all (:1092) catches per-platform exceptions and
  returns UploadResult(success=False), so one platform failing does not abort
  the others. That part is already correct — confirm it, do not rewrite it.

  main.py:200-203 wraps everything in `except Exception: logger.error(...)`.
  admin.py surfaces failures via st.error, which does not exist headless.

  output/rejected/ exists (admin.py:61 REJECTED_DIR) and is used by the QA
  gate. There is no equivalent for UPLOAD failures.

TASK

  a. Report the current behaviour first, as a table: for each failure class —
     TTS call fails mid-video, render fails, QA gate rejects, auth fails,
     upload init fails, upload interrupted mid-chunk, recording fails — what
     happens today to (1) the batch, (2) the artifact on disk, (3) what an
     operator sees the next morning.

     Do this BEFORE writing code and show it to me. Some of these are probably
     already fine and I do not want them touched.

  b. Then, for the ones that are not fine: one failure must never abort a
     batch, the artifact must land somewhere findable with a machine-readable
     reason, and the outcome must be visible without reading logs.

  c. A batch summary written to disk. One file per run. This is what I read
     instead of scrollback, and PROMPT 2 left it three specific jobs:

     SKIPPED IS ITS OWN CATEGORY, not a silent success. PROMPT 2's guard keys
     on (artifact name, platform), and its documented hole is: re-render a
     topic under the same name and the guard refuses to publish the new file
     forever, because a skip produces no signal. Do NOT re-litigate the key —
     it is the right one. Make the skip LOUD instead: every skip in the summary
     with the reason and the videoId it thinks is already live. That downgrades
     the hole from invisible to merely annoying, which is all it needs.

     THE AMBIGUOUS CASES MUST REACH ME. PROMPT 2 holds on a 404'd session URI
     and logs CRITICAL. PROMPT 1 leaves live-but-unrecorded at CRITICAL too.
     Headless, CRITICAL in a log is as good as nothing. Both must be in the
     summary, at the top, in a section that is empty on a clean run.

     So the categories are: attempted / published / skipped (reason) / failed
     (reason) / NEEDS A HUMAN (reason + what to check on the channel).

  d. TEST ISOLATION — small, and it is about the one file with no recovery
     story. An early PROMPT 2 test run wrote 13 fixture rows into the real
     output/published/attempts.jsonl. Caught and cleaned, and the real ledger
     was untouched — this time.

     The ledger records irreversible events and is append-only by design, so a
     poisoned row cannot be rewritten away, only appended around. It is in the
     same category as .tokens/: no recovery story.

     Make it structurally impossible rather than remembered: tests must not be
     able to write to the real LEDGER_PATH or attempts path. A conftest fixture
     that redirects them, a runtime refusal when running under pytest, or both.
     Say which and why.

     PROOF: a test that tries to write to the real path and is refused.

PROOF
  A batch run of 3 videos where the middle one fails, showing: the other two
  published, the failed one findable with its reason, and the summary correct.
  Use a stubbed failure, not a real API error.

OUT OF SCOPE
  - Retry policy beyond what PROMPT 2 established.
  - Alerting, email, notifications. A file on disk is enough.
  - Do NOT start 6a.

GIT: one commit, push after.
````

---

## PROMPT 4 — El camino headless se salta el final del pipeline

**Esto era el Prompt 4 de scheduling. Ya no.** El informe del Prompt 3 encontró que `finalize_video` no lo llama nadie: `--batch --upload` publica **sin pasar por el gate y sin outro**. Los Pasos 2 y 3 construyeron el gate y lo pusieron en BLOCKING; el 4a puso el CTA de Learning Routes. Ninguna de las dos cosas alcanza el camino que 5a automatiza.

La inversión completa: **el gate protege el camino que tiene un operador delante, y no protege el que no lo tiene.** Y el canal existe para captar hacia Learning Routes — un video sin outro no cumple el propósito por el que se genera.

Poner un reloj encima de esto publicaría 2/día sin validar y sin CTA.

````
Same repo. PROMPTS 1-3 are done. 338 tests passing.

WHAT YOU FOUND AND CORRECTLY DID NOT ACT ON

finalize_video has zero callers. The QA gate does not run on the --batch path,
and neither does the outro. `python main.py --batch N --upload` publishes
ungated video with no Learning Routes CTA.

Step 2 built that gate. Step 3 flipped it to BLOCKING behind an explicit
decision. Step 4a added the outro, which is the only reason this channel
exists — it is the acquisition path for Learning Routes. None of it reaches
the path that 5a automates.

You were right not to wire it silently. Wire it now, deliberately.

TASK

  a. FIRST, ESTABLISH — do not assume, and do not let me assume either.
     If finalize_video has zero callers, then the dashboard path gets the gate
     and the outro some OTHER way, because videos published on 08-01 visibly
     carried the outro. So:

       - Where does the dashboard path actually apply the QA gate?
       - Where does it actually apply the outro?
       - What is finalize_video then — dead code, or a wired-up-elsewhere
         helper that main.py should be calling?

     Report this before changing anything. If the answer is "inline in
     admin.py", that is a FOURTH divergence and unifying it is the task. If the
     answer is "pipeline.py", then main.py just needs to call the same thing
     and this is small.

  b. Then make the headless path run the same finalisation as the dashboard
     path: gate, then outro, in whatever order the existing code establishes.
     src/pipeline.py:420 carries a comment saying the order matters and why —
     read it and preserve that reasoning rather than re-deriving it.

  c. A gated batch needs a rejected path. output/rejected/ already means "the
     QA gate said no" and is the correct destination — distinct from the
     output/failed/ tree you created in PROMPT 3 for pipeline failures. A
     rejection must appear in the batch summary under its own category, not
     as "failed".

COST NOTE
  The gate on the batch path adds work per video. Report the per-video wall
  clock before and after. If it materially changes what 2/day costs in time,
  say so with the number.

PROOF
  - The (a) table: where gate and outro live for each of the two paths, before.
  - A batch of 3 where one video fails the gate: the other two published WITH
    the outro, the rejected one in output/rejected/ with its report, and the
    summary showing published / rejected as separate categories.
  - One rendered video from the batch path, so I can see the CTA is there.

OUT OF SCOPE
  - Changing any gate threshold. The gate is calibrated; this is about running
    it, not tuning it.
  - Scheduling. That is PROMPT 5 and it must not start until this lands.
  - Do NOT start 6a.

GIT: one commit per task, push after each.
````

---

## PROMPT 5 — Scheduling

**Va el último y no se adelanta.** Un reloj encima de un camino que puede duplicar, que traga errores y que no registra lo que publica no es automatización: es el mismo fallo repetido dos veces al día sin nadie mirando.

````
Same repo. PROMPTS 1-4 are done and pushed.

GOAL: 2 videos/day, unattended.

TASK 0 — MEASURE FIRST, AND STOP. Do not write a scheduler in this step.

  The gate rejects 116 of 206 corpus artifacts (56%). That is the four-era
  baseline, already recorded as debt. What is NOT measured is the pass rate of
  CURRENT-era output, and that number decides whether 2/day is even meaningful:
  a gate that rejects half of what the generator makes means publishing 1/day
  and growing a rejected pile nobody reads.

  Run a REAL batch — real GPT, real ElevenLabs, real render, gate on, upload
  OFF. Six videos, spread across the types --batch actually produces.

  Report:
    - pass / reject per video, with the blocking flags for each rejection
    - the pass rate, stated as "N of 6" and not extrapolated to a percentage
    - for each rejection: is it a real defect in the video, or a gate threshold
      that current-era output legitimately trips? Look at the rejected videos.
      Do not answer this from the flags alone.
    - actual cost of the batch in API spend

  Then STOP and show me. If the pass rate is high, scheduling is a small step.
  If it is low, the next step is not a scheduler — it is deciding whether the
  gate or the generator is wrong, and I want to make that call, not have it
  absorbed into a scheduling commit.

  Keep the six rendered videos. Whatever passes, I am publishing by hand — I
  need a fresh fill_blank and a fresh educational live anyway, and this batch
  produces both.

TASK — ONLY after I have seen TASK 0

  a. Pick the mechanism and justify it against this specific machine — this
     runs on a laptop that sleeps, not a server. cron, launchd, a long-running
     Python scheduler, systemd timer. A schedule that silently does not fire
     because the lid was closed is the failure mode to design against, so say
     how yours is detectable.

  b. A kill switch that does NOT require editing code. A file whose presence
     stops the next run is fine. It must be checked at the start of every run,
     and the run must say in the summary that it was skipped and why.

  c. Decide and state the publishing cadence explicitly: which times, which
     video types, what happens when the queue is empty, what happens when the
     previous run has not finished.

  d. First run in DRY-RUN by default. It must be a deliberate act to make it
     publish for real. Tell me the exact command that flips it.

PROOF
  - Two consecutive dry runs, with the summary from PROMPT 3 for each.
  - The kill switch demonstrated: present -> skips and says so; absent -> runs.
  - The overlap case demonstrated: what happens if a run starts while the
    previous one is still going.

OUT OF SCOPE
  - TikTok. Still blocked on external audit: unaudited clients publish
    private-only, so automating it produces videos nobody can see.
  - Instagram.
  - Do NOT start 6a.

GIT: one commit, push after.
````

---

## PROMPT 6 — Pequeño, aparte, en cualquier momento

````
Second fixture leak, same class as the attempts-file one: PROMPT 2's test run
left output/uploaded/test_a_raising_platform_does_n0/ behind. The conftest
guard from PROMPT 3 covers the ledger paths only; OUTPUT_DIR is not covered.

Extend the same two-layer protection to OUTPUT_DIR: tests must not be able to
write into the real output tree. Same reasoning as before — make it
structural, not remembered.

PROOF: a test that tries to write into the real OUTPUT_DIR and is refused.
````

---


````
Give _audit/RETENTION_BASELINE.md and _audit/PUBLISHED_AUDIT.md the same
_capture treatment the QA baselines got in commit 3898ee7: the detection
parameters, the commit, the date, and what the numbers can and cannot be
compared against.

Concrete reason: RETENTION_BASELINE.md records 2.46 s / 22 % dead air for a
video where the current measurement routine says 3.353 s / 30.2 % on the same
audio. That is a different silencedetect window, not a change in the file. The
document does not say so, so the next reader will conclude something regressed.

Annotate it inside the files. No code changes.
````

---

## Dónde está el corte

**El Prompt 1 solo, y para.** Quiero ver la tabla de los tres caminos antes de que exista una guarda de idempotencia, porque la guarda consulta el ledger y el ledger todavía tiene una fuga.

## Qué espero que salga

Que la decisión de (b) en el Prompt 1 —si `main.py` debe pasar por `resolve_upload_metadata`— no sea obvia. `resolve_upload_metadata` toma `st.session_state`, que headless no existe. La respuesta correcta puede ser "no, y aquí está por qué", y prefiero ese razonamiento a un cambio que fuerza la unificación por simetría.

Y que en el Prompt 2, la elección de clave de idempotencia **no cubra algún caso**. Todas tienen un agujero. El pedido explícito de nombrarlo está ahí para que salga en el informe y no en producción.

## Pregunta suelta, barata, antes del Prompt 2

`_build_fallback_title` re-aleatoriza por plataforma. Está registrado como deuda y la justificación es que hoy no es alcanzable: los 12 guiones más recientes llevan `video_title` y los 160 que no son de antes de abril.

**Pero "hoy no es alcanzable" es una propiedad de los datos, no del código.** La pregunta que lo convierte en garantía: ¿el schema pydantic del Paso 1 hace `video_title` OBLIGATORIO para los tipos que `--batch` renderiza? El propio Paso 1 documentó una discrepancia justo ahí — el prompt de `true_false` exige `video_title` y la salida real no lo lleva.

Si es obligatorio, el caso es inalcanzable por construcción y la deuda puede quedarse dormida. Si es opcional, dispara la primera vez que GPT lo omita — y bajo 5a eso pasa sin nadie delante.

---

## El riesgo real de este paso

No es técnico. Es que 5a multiplica por dos al día cualquier cosa que esté mal. Los tres primeros prompts existen para que lo que se multiplique sea el video, no el defecto.

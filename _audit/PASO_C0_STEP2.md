# C0 · Paso 2 — un contrato, no un validador más blando

**Diagnóstico confirmado y ampliado.** Adelante con el arreglo.

---

## Lo que confirmo

`media_validation.py:78` exige `words` **y** `segments` no vacíos, para todos los tipos. Medido sobre los sidecars reales en disco:

| tipo | muestras | `words` | `segments` |
|---|---|---|---|
| `quiz` | 13 | 0..37 | 0..20 |
| `true_false` | 19 | 0..24 | 0..8 |
| `vocabulary` | 7 | **0..0** | 7..8 |
| `quiz_openai` | 1 | 51..51 | **0..0** |

**Falla en las dos direcciones.** `vocabulary` siempre se cae por `words`; `quiz_openai` por `segments`. No es un defecto de quiz: `validate_timing` bloquea la producción de todos los tipos.

Y es la prueba definitiva de que este camino no se ejecutó nunca. Se habría caído en el primer intento.

## Y el contrato correcto ya estaba escrito

`qa_gate.py:79-83`, en prosa, con su razonamiento:

```
#   quiz / true_false / fill_blank / vocabulary -> segment_times
#   educational / pronunciation                 -> word timeline
#   neither                                     -> REJECT
REQUIRES_SEGMENT_TIMES = V3_TYPES
REQUIRES_WORD_TIMELINE = TURBO_TYPES
```

`media_validation` no lo relajó: **lo reimplementó, más estricto y sin tipo**. Segunda implementación de una decisión que ya tenía una, y discrepan.

> Es la firma de este repo otra vez, en su otra cara. Normalmente es *código correcto que nunca recibe lo que necesita*; aquí es **una decisión correcta que se vuelve a tomar en otro sitio, peor**. El resultado es el mismo: el camino de producción no funciona.

**Por eso el arreglo no es aflojar el validador.** Aflojarlo deja dos contratos, y el siguiente que los toque volverá a elegir mal. Hay que dejar uno.

---

## PROMPT — C0 Paso 2

````
Step 1 accepted. Your diagnosis is right; I widened it and the wider version
changes the fix.

WHAT I VERIFIED

validate_timing requires words AND segments non-empty, for every type.
Measured across the real sidecars on disk:

    quiz          13 samples   words 0..37   segments 0..20
    true_false    19 samples   words 0..24   segments 0..8
    vocabulary     7 samples   words 0..0    segments 7..8
    quiz_openai    1 sample    words 51      segments 0

It fails in BOTH directions — vocabulary always on words, quiz_openai on
segments. This is not a quiz defect. validate_timing blocks production for
every type, which is the complete explanation for "end-to-end creation is
broken", and proof this path had never been run.

THE FIX IS NOT A LOOSER VALIDATOR

qa_gate.py:79-83 already carries the contract, in prose, with its reasoning:

    quiz / true_false / fill_blank / vocabulary -> segment_times
    educational / pronunciation                 -> word timeline
    neither                                     -> REJECT
    REQUIRES_SEGMENT_TIMES = V3_TYPES
    REQUIRES_WORD_TIMELINE = TURBO_TYPES

media_validation did not relax that rule — it RE-IMPLEMENTED it, stricter and
without the type. Two implementations of one decision, disagreeing.

Loosening the validator leaves both in place, and the next person to touch
them picks the wrong one again. Land ONE contract.

TASK

  a. ONE SOURCE FOR "WHAT TIMING THIS TYPE NEEDS".
     validate_timing takes the video type and consults the same constants
     qa_gate uses. Do not copy the sets into media_validation; import them,
     or lift them into a module both import. If that creates a bad
     dependency direction, say so and propose where they should live — but
     the answer must be one definition, not two agreeing ones.

     Keep every other check in validate_timing exactly as it is: positive
     duration, an audio stream, metadata-vs-probe agreement, monotonic
     bounds, text present. Those are good and none of them is duplicated
     elsewhere.

  b. THE FAILURE MUST ANNOUNCE ITSELF.
     CreationService._production_failure records the error and returns
     normally, so run_creation succeeds, the batch loop's except never
     fires, and the report printed "1 attempted, 0 rendered, 0 failed".

     A blocked artifact is a failure and must be counted as one. Decide
     whether the service raises or the loop inspects the returned state, and
     say which you chose and why. Either way: a run that produces no video
     must not print a line that reads like a clean run.

     This repo has been burned by a batch report that lied before. It is in
     the roadmap as a fixed defect; this is a new instance in a new layer.

  c. THE SPEND MUST BE RECORDED WHEN IT FAILS.
     $0.0734 of real calls went out. The artifact recorded $0.0008. Nothing
     reached output/costs/ — no costs_2026-09-02.jsonl exists, because
     tracker.save() only runs on the success path.

     That is backwards: iterating on a broken pipeline is exactly when spend
     accumulates fastest and invisibly, and there is a monthly ceiling that
     is now under-counting. Persist the ledger on the failure path too.

PROOF

  P1. `--batch 1 --type quiz` renders. Show the artifact directory, the mp4,
      its duration, a frame, the final frame (outro), and the gate verdict.
  P2. One video of a WORD-timeline type (educational or pronunciation) also
      renders. Both sides of the contract, or the contract is not proven.
  P3. Force a production failure and show: the batch report counting it as
      failed, and the cost ledger holding the spend. Both, from one run.
  P4. The real cost of everything in P1-P3, from output/costs/.
  P5. Full test suite, and a test pinning the type→timeline contract so a
      third implementation cannot appear quietly.

REUSE WHAT IS PAID FOR
  output/artifacts/art_20260902_173159_7c953d19/ already holds a valid
  script and narration. Use it where you can rather than re-buying it.
  Paying is fine when the proof needs it — say what you spent.

STILL OUT OF SCOPE
  - Step 3 (the read adapter). It comes after this renders.
  - Task 8, E2/E3/E5, D1/D2/D4, F3(d), the Bilibili voice IDs.

If (a) turns out to need the constants in a third module and that ripples
further than it looks, land (a) alone and say so.
````

---

## Lo que espero que salga

Que `fill_blank` y `pronunciation` no tengan ninguna muestra en disco y haya que renderizarlos para saber qué traen. Son los dos tipos que no aparecen en mi tabla. Si alguno no encaja en ninguna de las dos columnas del contrato, el contrato de `qa_gate` también está incompleto — y eso es un hallazgo, no un obstáculo.

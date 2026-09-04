# C0 — de `--batch` a un video publicado

**Va antes que todo lo demás.** `HEAD a5ccfa0` + trabajo sin commitear.
Reemplaza la versión anterior de este fichero.

---

## Qué significa "funciona", y por qué la definición es el trabajo

El dueño reporta que `--batch` no funciona y que la creación de punta a punta está rota.

**No pude reproducirlo.** Este puente corre Python 3.10 sin las dependencias del proyecto; su máquina corre 3.9.6. El error que yo veo es mío. Claude Code corre donde corre el proyecto y tiene que dar el traceback real antes de que nadie escriba un arreglo.

Pero el fallo de fondo no es un traceback. Es que **"funciona" nunca se definió de forma que no se pueda fingir.**

Este repo tiene 1130 tests en verde y una capa de creación que no ha producido un video jamás: `output/artifacts/` no existe. Los tests no tocan ffmpeg, ni la API, ni el disco. *"Todo pasa"* y *"nunca ha funcionado"* son compatibles aquí, y lo son ahora mismo.

Así que C0 lleva su definición de terminado dentro, y está construida para que ningún test la satisfaga.

---

## La bifurcación del árbol — decidida, con su razonamiento

El Studio escribe en `output/artifacts/<id>/`. El dashboard lee `output/{video,pending,approved,uploaded}`. **Un `--batch` que funcione perfectamente deja hoy un video que nadie puede ver ni publicar.**

Decisión del dueño: *fin a fin llega hasta que se pueda publicar.* Eso obliga a resolverlo.

Las dos salidas evidentes, y una tercera que es la que propongo:

| | |
|---|---|
| **(a)** El Studio escribe en el árbol por etapas | Bajo riesgo hoy. Conserva *el directorio es el estado*, que es de donde vienen la mitad de los dolores de este repo: un fichero movido a mano miente, un re-render lo devuelve, y por eso el ledger tuvo que convertirse en la autoridad. |
| **(b)** El dashboard aprende a leer `output/artifacts/` | Mejor arquitectura. Pero reescrito así, de golpe, toca Review, Upload, Library, el promote de E1, `move_to_uploaded` y `quarantine`. |
| **(c) ← propongo** | **Un adaptador de lectura.** El artefacto es canónico y no se mueve ni se copia nunca. Las cuatro funciones que hoy listan directorios (`get_pending_videos`, `get_approved_videos`, `get_library_videos`, `get_uploaded_videos`) pasan a pedirle la lista a un adaptador que devuelve **la misma forma de diccionario que las páginas ya consumen**. Ninguna página cambia. |

**Por qué (c):** cambia cuatro lectores en vez de la interfaz entera, no duplica ficheros, sustituye *directorio-es-estado* por *lifecycle-es-estado* donde el Studio ya tiene una máquina de estados, y el adaptador puede servir **las dos fuentes a la vez** — los artefactos nuevos desde `output/artifacts/`, los 30 que ya están en el árbol viejo desde donde están. Nada existente se rompe y no hay migración de golpe.

**Y una ventaja que no es obvia:** (c) **no** enruta la creación del dashboard por `CreationService`. Eso mantiene dormida la mina del doble outro — `finalize_video` no es idempotente y `admin.py:367` lo sigue llamando directo. Unificar la creación es Task 8, y ahí es donde hay que desactivarla. C0 entrega "publicable" sin tocar esa mina.

**Si Claude Code cree que (c) está mal, que lo diga antes de escribir código.** El razonamiento está arriba entero para que se pueda atacar.

---

## PROMPT — C0

````
You are in ~/Downloads/english-ai-videos, on the machine where this project
actually runs. HEAD a5ccfa0 plus uncommitted work.

Paying to test is fine — the owner said so explicitly. Do not contort
anything to avoid a charge. Spend what the proof needs and report the real
figure.

THE PROBLEM

--batch does not work and end-to-end creation is broken. I could not
reproduce it: I reach this repo through a bridge whose Python lacks the
project's dependencies. You can.

But the deeper problem is that "works" was never defined in a way that
cannot be faked. This repo has 1130 green tests and a creation layer that
has never produced a video — output/artifacts/ does not exist. The tests
touch no ffmpeg, no API, no disk. "All green" and "never worked" are
compatible here, and right now they are both true.

So this task carries its definition of done, and it is built so no test
satisfies it.

STEP 1 — REPRODUCE. REPORT. DO NOT FIX.

Run `python3 main.py --batch 1 --type quiz`. Paste the FULL traceback and
say in one sentence what is broken. Stop there and show me.

The owner has been handed a guess instead of a diagnosis before in this
project. The error text goes on the record first.

STEP 2 — MAKE IT RENDER

Fix what Step 1 found.

Known and separate, fix it here because it is three lines: main.py:719-723
calls run_creation() without passing dry_run, so `--batch N --dry-run`
performs N REAL renders and charges for them. The flag lies. Forward it.
Do NOT build an elaborate dry run — the owner declined that. The flag must
simply do what it says.

STEP 3 — MAKE IT REACHABLE

A rendered artifact the operator cannot see is not a working pipeline. The
Studio writes output/artifacts/<id>/; the dashboard reads
output/{video,pending,approved,uploaded}.

Build a READ ADAPTER. The artifact stays canonical and is never moved or
copied. These four functions ask the adapter instead of globbing
directories:

    get_pending_videos()   get_approved_videos()
    get_library_videos()   get_uploaded_videos()

They keep returning exactly the dict shape the pages already consume, so no
page changes. The adapter serves BOTH sources: new artifacts from
output/artifacts/ by lifecycle state, and the ~30 existing files in the old
tree from where they are. No migration, no big bang.

Preserve, exactly:
  - get_approved_videos() consults publication_log. That is what stops a
    second publish of something already live. It is not optional and its
    docstring says why.
  - Absence of a gate verdict renders as "sin registro", never a tick.
  - A gate REJECT is a field, not a failed status.

Do NOT route the dashboard's creation through CreationService. That is
Task 8. finalize_video is not idempotent and admin.py:367 still calls it
directly; converging the paths without defusing that gives every video two
outros. C0 delivers "publishable" without touching that.

DEFINITION OF DONE — every line is a thing you show me, not a claim

  1. `--batch 1 --type quiz` completes.
  2. output/artifacts/<id>/ exists and holds the canonical record.
     Its first appearance is the proof this path has ever run.
  3. The mp4 plays. Report: duration, that it carries audio, that the outro
     is on the end, that the watermark is present. Extract a frame and a
     final frame and show both.
  4. The gate verdict is recorded on the artifact.
  5. The cost is in the tracker. Report the real number.
  6. It appears in the dashboard's Review, with its gate badge. Screenshot.
  7. It can be approved and uploaded, and the ledger gets a row with
     privacy public for youtube. Show the ledger row.
  8. Uploading it a second time is refused by the idempotency guard, and
     writes nothing. Show the refusal and the unchanged ledger.

  9. Full test suite. Report the count.

Items 6, 7 and 8 are the ones that make this end-to-end rather than
"a file exists". If you land 1-5 and stop, say so plainly — that is a
partial result and I would rather have it named than dressed up.

OUT OF SCOPE
  - Task 8. Do not start it.
  - E2/E3/E5, D1/D2/D4, F3(d).
  - The Bilibili voice IDs — owner's, and config not code.
  - Committing the tree; the owner is dealing with the index.lock.

HOW TO WORK

Step 1 alone, then stop. A month of work has never produced a video through
this path and I want the real error on the record before a fix exists.

If you think the read adapter in Step 3 is the wrong shape, say so before
writing it. The reasoning is in _audit/PASO_C0_PROMPT.md and it is there to
be attacked, not obeyed.
````

---

## Dónde espero que falle

En el punto 6. El adaptador tiene que decidir **qué estado del lifecycle equivale a "pendiente de revisar"**, y esa correspondencia no existe escrita en ningún sitio — hay una máquina de estados en `lifecycle.py` y cuatro directorios, y nadie los ha alineado nunca. Si la correspondencia no sale limpia, ese es el hallazgo, y es mejor verlo ahí que descubrirlo en Task 8 con la creación ya enrutada.

## Lo que este paso deja sin tocar, a propósito

La mina del doble outro sigue armada. `finalize_video` no deja marca y tiene dos llamadores en dos rutas distintas. Hoy no se pisan; se pisan en Task 8. Está escrito aquí para que quien abra Task 8 no lo descubra mirando un video con dos finales.

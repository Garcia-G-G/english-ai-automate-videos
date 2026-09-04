# C0 — revisión del primer video del camino Studio

**Verificado contra el repo, no contra el informe.** `art_20260902_213027_1319e696`.

## Lo que confirmo

| | |
|---|---|
| Los dos artefactos | `ready_for_review`, con `final.mp4` real (3.6 MB quiz · 10.3 MB educational) |
| Un solo contrato | `src/timing_contract.py` existe; `qa_gate.py:70` importa y re-exporta; `media_validation.py:10` importa `required_timeline`. Sin segunda definición |
| Ledger del fallo | `costs_2026-09-02.jsonl`, 86 filas, **$0.4445** |
| Coste en el artefacto | $0.0702 (quiz) y $0.0995 (educational) — ya no $0.0008 |

El razonamiento sobre `ProductionFailure` es correcto y me alegra que los 26 tests lo tumbaran: *"la excepción de una etapa delegada llega al llamador sin disfraz"* es una garantía de diagnóstico real, y anotar el gasto sobre la excepción original conserva las dos cosas. La asimetría con la mitad editorial está bien resuelta.

---

## Dos cosas que el frame enseña y el informe no

### 1 · El watermark está encima del texto de la lección

En `t=33s`, `learningroutes.com` se dibuja **sobre la tercera línea** de la tarjeta de explicación. No al lado: encima.

Es la **misma colisión de presupuesto watermark/tarjeta** que cerramos en 6a para la tarjeta de educational. Ha vuelto, en la tarjeta de explicación de quiz.

Y no es un defecto aparte del que reportaste: el desbordamiento de 52px es *la causa*. La tarjeta no cabe, su texto baja, y aterriza en la banda donde vive la marca.

**Y el gate lo dio por bueno.** `final_qa: PASS` sobre un fotograma donde la marca tapa la lección.

> **Ceguera del techo, cuarta instancia.** El gate mide contraste de texto contra fondo. No mide texto contra texto. Un elemento tapando a otro puntúa perfecto.

### 2 · El camino Studio no recibe los fondos generados

`legacy_pipeline.py:244`, con su propio comentario:

```python
# The legacy topic tier writes to global output/backgrounds and has no
# destination argument.  Omitting topic/category keeps all new media
# inside this artifact while retaining explicit/profile resolution.
selected_background = self._resolve_background(
    audience_profile,
    artifact.request.background,
)
```

**`topic` y `category` se omiten a propósito.** Y el resolver unificado de F2 los necesita: sin ellos nunca alcanza el tramo 3 —generar, pasar la puerta, devolver `photo:<path>`— y cae a paleta.

Comprobado: el artefacto no registra fondo, no contiene `photo:`, y no se ha generado ninguna imagen desde el 21 de agosto. El frame lo confirma — degradado morado, no imagen.

**Octava instancia de la divergencia.** Los pasos F, F2 y F3 —el catálogo muerto, el resolver unificado, los fondos vivos y variados, el scrim compuesto— llegan al camino viejo y **no llegan al que va a ser canónico**.

La razón del comentario es legítima: el generador escribe en un `output/backgrounds/` global y no acepta destino, lo que rompería que el artefacto sea autocontenido. Es una restricción real. **Lo que falta es que el coste esté dicho:** el comentario explica lo que se gana y no nombra lo que se pierde. Y lo que se pierde son tres pasos de trabajo.

El arreglo no es pasar `topic` y ya: es darle destino al generador para que escriba dentro del artefacto. Es pequeño y hay que hacerlo antes de que el Studio sea la ruta por defecto, no después.

---

## Menor, pero con filo

Tres `.mp4` de **cero bytes**, dos de ellos en `output/approved/`:

```
0  Aug 31 21:08  output/approved/quiz/hang_in_there_20260831_150730.mp4
0  Aug 31 21:08  output/approved/vocabulary/small_talk_expectations_20260831_150733.mp4
```

`approved/` es la cola de subida. Un fichero vacío ahí no solo rompe la miniatura en cada carga: **está en la lista de lo que se puede publicar.** Merece que el listado descarte por tamaño, o que alguien mire por qué el render del 31 dejó ficheros vacíos sin marcar el job como fallido — que es el mismo defecto de "el fallo no se anuncia" que acabas de cerrar en la capa Studio, un piso más abajo.

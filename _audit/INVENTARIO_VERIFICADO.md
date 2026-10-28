# Inventario verificado contra el output real

2026-09-04 · HEAD `4f6ff36` · medido sobre los archivos que produjo tu máquina,
no sobre el código.

---

## El hallazgo que explica todo lo demás

**Hay tres puertas de producción y los arreglos solo entraron por una.**

| | Studio / `--batch` (`output/artifacts/`) | Dashboard (`generation_jobs.json`) |
|---|---|---|
| Fondos de clip | **sí** — 3-4 `pexels_*.mp4` por artifact | **0 de 50 jobs**, nunca |
| `pronunciation` desde su propio archivo | **sí** — `REcord (noun)`, `full vs fool`, `advertisement` | **0 de 19 guiones** |
| Gasto en fondos | $0.00 | **$0.902** acumulado |

No estamos retrocediendo. Los arreglos son reales y **la puerta que tú usas no
los alcanza**.

### Fondos — la línea exacta

```python
# pipeline.py:194 — tier 3, el metraje propio del video
if topic and dest_dir:
    resolved = _clip_background(topic, category, dest_dir, duration, entry, on_record)
```

```python
# studio/legacy_pipeline.py:298 — la puerta de batch
self._resolve_background(profile, background, topic=..., category=...,
                         dest_dir=artifact_dir / "clips",      # ← lo pasa
                         duration=float(tts_metadata[...]))
```

```python
# admin.py:346 — la puerta del dashboard
pipeline.resolve_background(profile, background,
                            topic=topic_name, category=category,
                            on_record=_record_background)      # ← sin dest_dir
```

Sin `dest_dir` el tier 3 no se evalúa siquiera. Cae al tier 4, la imagen
generada de $0.041. El job de hoy lo registró tal cual:

```json
"background": {"source": "generated",
               "image": ".../output/backgrounds/giving_compliments.png",
               "cost_usd": 0.041}
```

Es la misma forma que F2 — "el fondo por video solo llega por `--batch`" — que
dimos por cerrado. Se cerró la divergencia; la puerta siguió sin pasar el
argumento.

**Arreglo:** `admin.py` necesita un `dest_dir` por job (p. ej. `output/clips/<job_id>/`)
y el `duration` del audio. No es una línea como te dije — son unas cuatro y una
decisión de dónde viven los clips del dashboard. Me corrijo.

### Tipo ↔ categoría — la misma puerta

19 guiones de `pronunciation` en `output/scripts/`. **Ninguno** salió de
`content/topics/pronunciation.json`. Salieron de `social` (5), `false_friends` (3),
`business` (2), `cultural` (2), `phrasal_verbs` (2), `idioms`, `slang`,
`common_mistakes`, `kids_colors`, `kids_numbers`.

Los artifacts del 3 de septiembre en adelante sí traen `cat=pronunciation`.
Mismo patrón: arreglado en batch, no en el dashboard.

---

## Lo que eso produjo hoy

`output/scripts/pronunciation/job_interviews_describing_experience_20260904_121336.json`

```
_meta.category : "business"        topic_id: "bz022"
word           : "Job Interviews: Describing experience"
common_mistake : "Pronunciar 'Job' como 'Yob'"
phonetic       : "YOB IN-ter-vyuwz: di-SKRAI-bing iks-PEER-i-ens"
```

`phonetic` es lo que se pinta en verde bajo **"Correcto:"**. Empieza con `YOB`,
que es exactamente lo que el propio guion nombra como el error.

**El video enseña el error como la respuesta correcta.** De todo lo de esta
lista, esto es lo único que no es un defecto de forma: es una lección falsa, y
está en `output/pending/` listo para subir.

---

## Vocabulary — 9 de 12 filas se salen. Medido.

Columnas reales: izquierda 400px, derecha 480px. Fuente fija 42px, fuente real
`Inter-Bold.ttf`, texto real del guion de hoy:

```
 1. ES  481px  (+81)    EN  659px  (+179)   Excelente presentación
 2. ES  787px (+387)    EN  820px  (+340)   Has demostrado una habilidad notable
 3. ES  323px   ok      EN  495px   (+15)   Te queda genial
 4. ES  475px  (+75)    EN  527px   (+47)   Eres muy bueno en eso
 5. ES  260px   ok      EN  220px    ok     Buen trabajo
 6. ES  806px (+406)    EN  679px  (+199)   Eso es un gran trabajo en este proyecto
 7. ES  487px  (+87)    EN  350px    ok     Impresionante esfuerzo
 8. ES  415px  (+15)    EN  323px    ok     Me encanta tu estilo
 9. ES  392px   ok      EN  415px    ok     Eres muy talentoso
10. ES  685px (+285)    EN  668px  (+188)   Tienes un gran sentido del humor
11. ES  483px  (+83)    EN  443px    ok     Tu trabajo es inspirador
12. ES  278px   ok      EN  319px    ok     Eres increíble
```

Fila 5 y la izquierda de la 3 son las únicas que caben — y son exactamente las
que se ven bien en tu captura.

### Por qué, en dos fallas encadenadas

```python
# vocabulary.py:359
lf, _, _, _ = fit_text_font(es_text, _ROW_FONT, 28, left_col_w)
draw_text_solid(draw, es_text, ...)                              # :365
```

1. `fit_text_font` **sin `max_height` devuelve siempre la fuente máxima**.
   `utils.py:548` es `if max_height is None or box.advance_height <= max_height: return box`
   — sale en la primera iteración. Nunca encoge. Siempre 42px.
2. Y el resultado se descarta igual: `lf, _, _, _` tira las `lines` ya cortadas,
   y dibuja el string **sin cortar**.

La medición se calcula bien y se tira a la basura. Es la firma del repo otra vez.

---

## Pronunciation no tiene layout. Tiene coordenadas.

Diez constantes fijas (`PRON_TITLE_Y=250`, `PRON_TRANSLATION_Y=430`,
`PRON_QUESTION_Y=530`, …). Ninguna mide lo de arriba. Medido con el dato de hoy:

```
word (37 chars → fuente 88)   3 líneas   ocupa 250..574
translation (fuente 48)       2 líneas   dibujado en 430   → SOLAPE 118px
pregunta (fuente 56)          1 línea    dibujado en 530   → SOLAPE  44px
```

En cuanto algo envuelve, crece hacia abajo y aterriza sobre el siguiente.

---

## Agrupación — 8 de 26 grupos no cierran oración

`output/audio/educational/count_to_five_20260904_121130.json`, 103 palabras,
26 grupos con el `SubtitleProcessor` real:

```
 1. Hoy aprenderemos                              CORTA A MEDIAS
 2. a count to five,                              CORTA EN COMA
 4. Empezamos con one,                            CORTA EN COMA
12. Por ejemplo, si tienes cinco manzanas, dirías  CORTA A MEDIAS
14. También puedes usarlo al jugar, como           CORTA A MEDIAS
17. Recuerda: five                                 CORTA A MEDIAS
18. es el último número, así que intenta siempre   CORTA A MEDIAS
20. Ahora, repite conmigo:                         CORTA EN COMA
```

3 terminan en coma, 5 cortan a mitad de frase. `max_words_per_group = 8` sigue
intacto en `subtitle_processor.py:140`.

---

## Duración — lo único que pasa limpio

```
count_to_five            56s
job_interviews           53s
giving_compliments       89s
on_the_house             48s   ← 2s bajo el piso de 50
```

3 de 4 en banda.

---

## Orden propuesto

1. **`dest_dir` + `duration` en `admin.py`.** Devuelve fondos de video en el
   dashboard y baja el costo de $0.041 a $0.00 por video.
2. **Tipo ↔ categoría en la puerta del dashboard.** Un `pronunciation` solo
   puede recibir un tema de `pronunciation.json`; si no hay, no se genera.
   Esto es lo que produce lecciones falsas.
3. **Vocabulary:** usar las `lines` que `fit_text_font` ya devuelve y pasarle
   un `max_height` para que la fuente encoja de verdad.
4. **Pronunciation:** apilar midiendo, no por constantes.
5. **Agrupar por oración + L1 en educational.**

## Nota de método

Todo lo de arriba sale de archivos que produjo tu máquina. La lección de esta
ronda es que **verificar que el código existe no es verificar que se ejecuta**:
los clips están bien escritos, tienen tests, y no habían corrido ni una sola vez
por la puerta que usas.

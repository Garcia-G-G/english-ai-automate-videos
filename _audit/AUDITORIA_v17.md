# Auditoría de lo hecho entre el 24-08 y el 02-09

**Contra `HEAD a5ccfa0`, rama `6a-layout`.** Todo comprobado ejecutando, no leyendo el handoff.

Bilibili queda registrado como **opción de creación de videos en chino, pedida por el dueño**. Se audita como función, no como deriva.

---

## Lo bueno, primero

54 commits · 91 ficheros · **+17.758 / −575**. Reparto: 23 `feat`, 19 `fix`, 5 `refactor`, 4 `test`.

**La mayor parte de esas inserciones son tests.** 50 ficheros, 448 funciones de test. El Studio solo aporta ~2.644 líneas de código contra ~5.100 de prueba. Ese ratio es el mejor que ha tenido este repo, y conviene decirlo antes de lo demás.

Y el trabajo CJK está bien hecho: la fuente **lanza `MissingCJKFont`** en vez de dibujar cajas vacías, y el corte de línea nuevo se valida contra 76 casos que corren el algoritmo original como oráculo. Ninguna de las dos cosas es un parche.

---

## 1 · El camino Studio no se ha ejecutado ni una vez

`ArtifactStore` (`artifacts.py:57`) hace:

```python
self.root.mkdir(parents=True, exist_ok=True)
directory.mkdir(exist_ok=False)
```

La raíz se crea en la primera escritura. Y:

```
output/artifacts existe: False
```

**Cero artefactos. Cero creaciones. Nunca.**

Y no es que el proyecto esté parado: hay renders del **31 de agosto** en `output/approved/` y uno del **2 de septiembre** en `output/rejected/`. Todos por el dashboard, es decir, por el camino viejo.

`main.py:589` ya delega en `service.create(request)`, y `generate_and_run` —la puerta del `--batch`— es hoy un envoltorio sobre `run_creation`. O sea: **el CLI está reescrito para pasar por Studio y no se ha corrido desde que se reescribió.**

> **Séptima instancia del fallo dominante, y la primera a escala de arquitectura.**
> Las seis anteriores costaban una función: `finalize_video` sin llamadores, el fondo generado en una sola ruta, el veredicto del gate que no llegaba a Review. Ésta cuesta **2.644 líneas cableadas y frías**.
>
> Los tests pasan. Los tests no tocan ffmpeg, ni la API, ni el disco real. **"1130 tests en verde" y "nunca ha producido un video" son compatibles**, y aquí lo son.

**Lo que hay que hacer no es más código: es correr `--batch` una vez.** Un video, ~$0.15. Lo que salga de ahí es el trabajo real, y hasta que se corra, todo lo que se construya encima se apila sobre algo no verificado.

---

## 2 · El doble outro: mina armada, no defecto vivo

Comprobados los dos llamadores:

| | |
|---|---|
| `src/admin.py:367` | `pipeline.finalize_video(...)` — camino dashboard |
| `src/studio/legacy_pipeline.py:222` | `self._finalize_video(...)` — camino Studio |

**Hoy son rutas distintas y no se pisan.** Ningún video lleva dos outros ahora mismo.

Se vuelve real en el momento exacto en que Task 8 enrute el dashboard por `CreationService` sin quitar la llamada de `admin.py`. El handoff lo describe bien; solo matizo que es un riesgo futuro y no un daño presente — la diferencia importa para priorizar.

`finalize_video` no deja marca de que ya añadió el outro y hace `os.replace()` sobre el mismo nombre, así que **el defecto sería invisible salvo mirando el video**.

---

## 3 · Bilibili: está más cerca de lo que el handoff sugiere

Fui a buscar una cuarta capa que asumiera latín — la generación de guion — **y no existe ese problema**: Bilibili tiene su propio autor (`BilibiliScriptAuthor`, `bilibili.py:85`, con su propio `SYSTEM_INSTRUCTION`) y su propio módulo de producción. El `script_generator.py` en español no se toca. Eso está bien resuelto.

Y una corrección al handoff: **`zh-Hans` sí está registrado en el segmentador** (`tts_segmenter.py:81`, `LanguagePolicy("zh-Hans", "zh")`). No es una capa pendiente.

Estado real, ordenado por lo que cuesta arreglarlo:

| | estado | qué es |
|---|---|---|
| Guion en chino | ✅ | autor propio |
| Fuente CJK | ✅ | Noto, y falla ruidoso |
| Corte de línea | ✅ | por carácter, con kinsoku |
| Política de idioma | ✅ | `zh-Hans` registrado |
| **Voces** | ❌ | **dos variables de entorno.** `BILIBILI_ADULTS_ELEVENLABS_VOICE_ID` y `BILIBILI_CHILDREN_ELEVENLABS_VOICE_ID`. Tienes ElevenLabs. Esto no es código. |
| Timing de palabra | ❌ | `.split()` en `subtitle_processor.py` y `tts_openai.py`. Afecta al karaoke |
| Ruta de subida | ❌ | no existe uploader, ni plataforma en config, ni en el ledger |

**El experimento más barato del proyecto ahora mismo:** fija las dos voces y renderiza **un** video chino de un tipo que no dependa del karaoke. ~$0.15.

Eso convierte *"Bilibili está bloqueado por tres capas"* en una lista medida de lo que se rompe de verdad. Ahora mismo nadie sabe cuáles de los seis tipos funcionan en chino, porque nunca se ha intentado — y el karaoke toca `quiz`, `true_false` y `educational`, pero eso lo sé por lectura, no por ejecución.

---

## 4 · Lo que no se auditó y hay que decir

- **No verifiqué los 1130 tests corriéndolos.** Conté 448 funciones en 50 ficheros; 1130 casos con parametrización es plausible pero no lo comprobé.
- **No revisé el contenido del rewrite de `admin.py`** línea a línea — 786 líneas cambiadas sin commitear. Verifiqué que el Inicio hace lo que se especificó (`"Sin promover"`, `"Esperando revisión"`, `GATE_MISSING_LABEL = "sin registro"`), no que el resto del fichero siga entero.
- **No hay medición de si el layout chino se ve bien.** Los 76 casos oráculo prueban que el latín no cambió. Que el chino se vea bien es una prueba visual que nadie ha hecho, porque no hay video chino.

---

## Los tres siguientes pasos, en orden

1. **`rm .git/index.lock`, commitear, `git push -u origin 6a-layout`.** 54 commits y 980 líneas viven en una sola carpeta.
2. **Correr `--batch` una vez.** Es la prueba que le falta a un mes de trabajo. Si `output/artifacts/` sigue sin existir después, algo no está enrutado como creemos.
3. **Fijar las dos voces de Bilibili y renderizar un video chino.** El resultado —funcione o falle— es la primera información real sobre esa función.

Los tres cuestan menos de una hora y menos de un dólar. Ninguno es código nuevo.

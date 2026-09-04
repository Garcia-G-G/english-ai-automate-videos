# El dashboard — auditoría antes de tocarlo

**Leído contra `HEAD f112b2f`.** 2440 líneas, todo en `src/admin.py`. Nueve páginas.

Primero: **F2 aterrizó**. Tres commits (`8ce74e9`, `d58bbd4`, `f112b2f`) y el log lo confirma:

```
20260820_job-9840f39c.log
  22:35:19 [pipeline] Background: photo:.../output/backgrounds/dress_codes.png
  22:35:20 [video]    Background: generated image .../dress_codes.png
```

Un `job-*.log` con `photo:`. Es P2, cumplido.

---

## El patrón que encontré, otra vez

No es que al dashboard le falten funciones. Es que **el pipeline ya calcula cosas que la pantalla tira a la basura**. Cinco veces. Es exactamente el fallo dominante del repo, aplicado a la UI.

---

### 1 · El veredicto del gate no llega a la pantalla donde apruebas

`pipeline.py:610-614` — un rechazo **no lanza**, devuelve y sigue:

```python
if v["verdict"] != "PASS":
    return {"video": ..., "gate": "REJECT",
            "blocking_flags": v["blocking_flags"], "outro_appended": False}
```

`admin.py:379` — el job se cierra en verde **pase lo que pase**:

```python
complete_job(job_id, success=True, video_path=str(video_path))
```

**Ya ha pasado.** En tu `output/generation_jobs.json`:

| topic | status | current_step |
|---|---|---|
| `on the house` (fill_blank) | `completed` ✅ | `Gate: REJECT` |

Ese video aterrizó en `output/pending/`, con ✅ en Recent Activity, **sin outro y sin el CTA de Learning Routes**, al lado de los que sí pasaron. La página Review (`:1510-1589`) enseña el script, la metadata y el video — **ni gate, ni blocking_flags, ni si lleva outro**.

Lo rechazaste tú, a ojo (está en `output/rejected/`). La pantalla nunca te lo dijo.

Es la misma familia que el `✗` rojo sobre la respuesta correcta: la información que te contradice existe y no se muestra.

### 2 · `blocking_flags` y `outro_appended`: calculados y tirados

`admin.py:358-360` los mete en `result`. Y `_worker()` en `:448`:

```python
run_pipeline_with_tracking(job_id, video_type, category, topic_name, **kwargs)
```

**Sin recoger el retorno.** `result` muere ahí. El gate te dice *por qué* rechazó y nadie lo guarda.

### 3 · `job["background"]` se escribió ayer y no lo lee nadie

El mensaje de `f112b2f`, textual:

> *"so the dashboard can show which background a video got and whether the gate passed"*

`grep 'get("background")' src/admin.py` → **0 resultados.**

Y el dato es bueno. Está en tu ledger ahora mismo:

```
bg = generated / PASS   $0.041
bg = palette   / REJECT $0.041   ← pagaste la imagen y se descartó
```

Un fondo que la puerta de contraste refusó, cobrado igual, y no hay pantalla que lo diga. **Séptima instancia del fallo dominante, con un día de vida.**

### 4 · $3.1223 gastados, cero dinero en pantalla

488 entradas en `output/costs/`. Ninguna página muestra un número de dinero.

| api_type | gasto |
|---|---|
| `elevenlabs_tts` | **$2.7845** (89 %) |
| `openai_image` | $0.3280 |
| `openai_whisper` | $0.0060 |
| `openai_chat` | $0.0037 |

38 videos con coste · **$0.0822 de media** · techo que fijaste: **$15**.

Dos cosas que salen de esta tabla y que yo tenía mal:

- **El coste no lo mandan las imágenes, lo manda ElevenLabs.** 89 % contra 10 %. Yo venía hablando del precio por imagen; el término dominante es la voz y nunca lo miré.
- **`openai_chat` = $0.0037 en 38 videos** son $0.0001 por generación de guion. Eso no es creíble. La deuda registrada *"cost_tracker perdía openai_chat"* puede no estar cerrada del todo. **No lo afirmo — lo marco para comprobar.**

*(Corrección de dato: el ledger dice `model: gpt-image-2`, no `gpt-image-1.5` como yo escribí en el ROADMAP. Lo arreglo ahí.)*

### 5 · La página "Logs" no abre los logs

`_worker()` en `:443` graba la ruta del fichero **en la fila del job**:

```python
log_path = attach_run_log(f"job-{job_id}")
update_job(job_id, log_path=str(log_path))
```

La página Logs (`:2367-2440`) pinta el dict del job y **nunca abre el fichero**. `grep "\.log"` dentro de esa página: 0.

El `FileHandler` que añadimos en `4a0b1a4` existe precisamente para poder leer un fallo de las 3 de la mañana. La única página llamada "Logs" no lo enseña.

Y el número que sí importa y no está en ningún sitio útil: **23 de 51 jobs fallaron. 45 %.**

---

## Y una cosa que la pantalla dice y no es verdad

### 6 · El Scheduler miente

`scheduler_enabled` se escribe en `:2139` y `:2144`, y se lee en `:2136` — el `if` que pinta **"Scheduler is ACTIVE"**. Eso es todo. Grep en el repo entero: **cero consumidores fuera de la propia página.**

Le das a Start, la pantalla dice ACTIVE, y no pasa nada. Nunca. `interval_minutes` se guarda y no lo lee nadie. Lo único real de esa página es **"Generate Batch Now"**, que sí llama a `start_generation` en bucle.

Esto no es una pantalla incompleta: es una pantalla que **afirma una capacidad que el sistema no tiene**. Y el scheduler de verdad es el pendiente de 5a.

---

## El orden que propongo

| | qué | por qué primero |
|---|---|---|
| **D1** | Gate + outro + blocking_flags visibles en Review y en el job | Es lo único de esta lista que ya te ha costado publicar mal |
| **D2** | Fondo y coste por video en Review y en Logs | El dato existe, se paga, y se tira |
| **D3** | Panel de coste: total, por día, por video, contra el techo de $15 | Gasto recurrente sin medidor |
| **D4** | La página Logs abre `log_path` | El fichero existe y la página que lleva su nombre no lo abre |
| **D5** | Scheduler: decisión tuya (abajo) | |

D1 y D2 son la misma edición en las mismas dos páginas. D3 y D4 son independientes.

**Lo que NO propongo:** rediseñar el look. Se ve bien. El problema no es cómo se ve, es lo que no dice.

---

## La decisión que necesito

El Scheduler tiene dos salidas y no es mía:

**A · Quitarle los controles falsos.** Se queda "Generate Batch Now" (que funciona) y se va el Start/Stop/interval. Media hora. La pantalla deja de mentir hoy.

**B · Construir el scheduler de verdad.** Es el pendiente de 5a — el objetivo declarado del proyecto, 2/día desatendido. Días, no horas, y necesita el número que aún no tenemos: la tasa de rechazo del gate en la generación actual.

**Mi recomendación es A ahora y B como paso propio.** Motivo: hoy la pantalla afirma algo falso, y eso se arregla en media hora sin bloquear nada. Meter B aquí convierte "actualizar el landing" en el paso 5a completo, y entonces ni una cosa ni la otra avanza.

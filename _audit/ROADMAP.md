# ROADMAP — english-ai-videos (v17)

**Actualizado:** 2026-09-02 · **Rama:** `6a-layout` · **HEAD:** `a5ccfa0`
**Reescrito desde cero.** La arqueología (patrones, errores, mediciones) queda en la v16 y en `AUDIT.md`; este documento es lo que hay que hacer.

Todos los números de aquí están comprobados contra el repo hoy, no copiados.

---

## Estado

| | |
|---|---|
| Tests | 1130 |
| Commits por delante de `origin/main` | **54, y la rama no tiene upstream** |
| Sin commitear | 6 ficheros, 980 líneas, + un `.git/index.lock` bloqueando |
| Cola | 11 sin promover · 0 pendientes · 3 aprobados · 17 subidos · 109 rechazados |
| Ledger | 21 filas publicadas |
| Gasto histórico | **$4.4869** (mar $0.34 · jul $0.82 · ago $3.33) · techo $25/mes |
| **Techo por video** | **$0.30** — decidido 2026-09-02. Hoy: quiz $0.070 · educational $0.0995 |
| `output/artifacts/` | **no existe** |

---

## 1 · Tres bloqueantes. Nada más empieza hasta que estos caigan

### B0 · El trabajo de un mes vive en un solo sitio

```
$ git rev-parse --abbrev-ref @{u}
fatal: no upstream configured for branch '6a-layout'
```

54 commits nunca empujados a ningún sitio, 980 líneas sin commitear encima, y un `.git/index.lock` vacío del 2 de septiembre a las 17:12 que impide `git add` y `git commit`.

**El lock lo tiene que borrar Garcia a mano** (`rm .git/index.lock`) — el puente de esta sesión no puede eliminar ficheros.

Orden: borrar el lock → commitear → `git push -u origin 6a-layout` → PR contra `main` → merge por GitHub, sin force-push y sin merge local (el árbol tiene cambios del dueño en `_audit/**`).

### B1 · Doble finalización, armada y esperando

`finalize_video()` **no es idempotente**: añade el outro y hace `os.replace()` sobre el mismo nombre, sin marcador de que ya hay uno. Tiene **dos llamadores**: `src/admin.py:367` y `src/studio/legacy_pipeline.py:222`.

Task 8 enruta el dashboard por `CreationService`. Si se hace sin quitar la llamada de `admin.py`, **cada video sale con dos outros y pasa el gate dos veces**.

No es una hipótesis: es la configuración actual del código más el paso siguiente ya planificado.

### B2 · La capa Studio escribe donde nadie lee

El Studio (25 commits, ~2300 líneas + 5100 de tests) está cableado: `main.py` crea por `CreationService`, `profiles.py` resuelve por él, los cinco renderers piden su copy a `resolve_presentation()`.

Escribe en `output/artifacts/<id>/`. El dashboard lee `output/{video,pending,approved,uploaded}`.

**`output/artifacts/` no existe. El camino nuevo no se ha ejecutado nunca de punta a punta.**

Y como la publicación es aprobada por el dueño (§3), y el dashboard es la superficie de aprobación: **nada de lo que produzca el CLI se puede publicar.**

> Es el fallo dominante del repo — *código correcto que nunca recibe lo que necesita* — por primera vez a escala de arquitectura y no de función. Las seis instancias anteriores costaban una función; ésta cuesta una capa entera.

**La bifurcación, y es de Garcia:** o el Studio adopta el árbol de directorios por etapa, o el dashboard aprende a leer `output/artifacts/`. No la decido yo, pero no se puede seguir construyendo encima sin decidirla.

---

## 2 · La contradicción del objetivo — hay que resolverla, no es trabajo

El roadmap lleva desde la v1 con la misma definición de terminado:

> **"Dos videos publicados en un día sin que toques nada."**

Y `main.py --upload` ahora **renderiza y se niega**, vía `refuse_unattended_upload()`, con razón registrada: `hPdSoqjvu3E` se publicó dos veces desde una subida a mano contra una cola que no sabía que ya estaba vivo. Un `--batch N --upload` desatendido es ese mismo error automatizado.

La decisión de negarse es correcta. **Pero deja el objetivo declarado del proyecto inalcanzable por diseño, y nadie actualizó el objetivo.**

Tres salidas, y Garcia elige:

| | |
|---|---|
| **A** | Cambiar la definición: *2/día generados y encolados, con una aprobación humana antes de publicar.* Lo más honesto con lo que hay hoy. |
| **B** | Construir el camino desatendido seguro: el guard de idempotencia y el ledger existen precisamente para eso. Es trabajo real y es el 5a que sigue pendiente. |
| **C** | Dejarlo como está y aceptar que el objetivo escrito no es el objetivo real. |

**No recomiendo C.** Un DoD que nadie piensa cumplir contamina toda decisión de prioridad que se tome mirándolo.

---

## 3 · Decisiones cerradas — no se re-litigan

- **La publicación desatendida se niega a propósito.** `upload_video()` sigue vivo con su guard, su escritura al ledger y su resolución de metadata: es para el camino aprobado, no es código muerto. `tests/test_upload_policy.py` lo fija.
- **La ausencia de veredicto del gate no es un aprobado.** Se muestra *"sin registro"*. Nunca un tic verde, nunca un hueco.
- **Un REJECT del gate no es un job fallido.** "Failed" es que el pipeline lanzó. Un video refusado es un render correcto de un artefacto malo: lleva su veredicto como campo, no como estado.
- **El layout español está medido, no adivinado.** No tocar el camino latino de `line_break()` ni la fuente base: 76 casos en `tests/test_cjk_text.py` corren el algoritmo original como oráculo.
- **Hasta $0.30 por video.** El techo mensual sigue en $25. A 2/día son ~$18/mes, así que cabe. El presupuesto **no** es el bloqueante de casi nada de lo que queda abierto: el watermark encima del texto, los fondos que no llegan al Studio, los mp4 vacíos, E2/E3/E5 — ninguno cuesta dinero.
- **Privacidad por plataforma, en un solo sitio.** YouTube público, TikTok `SELF_ONLY` mientras el cliente no esté auditado.

---

## 4 · El orden de trabajo

### Ahora

| | | |
|---|---|---|
| **B0** | Commitear, upstream, push, PR | bloquea todo |
| **B1** | Quitar la llamada a `finalize_video` de `admin.py` | antes de Task 8 |
| **B2** | Decidir la bifurcación del árbol, y ejecutarla | bloquea publicar lo del CLI |
| **G** | Elegir A o B para el objetivo | decisión, no trabajo |

### Lo que se prometió y no se hizo

Esto lo pidió Garcia cuatro veces entre el 21 y el 24 de agosto. Los prompts están escritos en `_audit/` y sin empezar.

| | qué | estado |
|---|---|---|
| **E4a** | Inicio por trabajo, no por agregados | ✅ hecho, **sin commitear** |
| **E3** | Página de Fondos | ❌ `PASO_E_PROMPT.md` |
| **E2** | Una sola puerta de creación (hoy hay cuatro) | ❌ `PASO_E_PROMPT.md` |
| **E5** | Quitar lo "indie": emojis de navegación, CSS consistente | ❌ `PASO_E_PROMPT.md` |
| **D1** | Gate, flags y outro visibles en **Review** | ❌ `PASO_D_PROMPT.md` |
| **D2** | Fondo y coste por video en Review y Logs | ❌ |
| **D4** | La página Logs abre `log_path` | ❌ |
| **F3 (d)** | Selección de fondo sin repetir + scrim del watermark | ❌ `PASO_F3_ADENDA.md` |

**E3 es la que más pesa:** los fondos tienen gate propio, scrim, espacio de 5120 combinaciones y $0.041 por video, y **ninguna pantalla**.

**F3 (d) arrastra un defecto vivo:** el watermark es texto blanco en el tercio inferior, ese tercio ahora es claro por diseño, y `text_contrast` no mide el watermark. Tercera instancia de ceguera del techo, y la fabricamos nosotros.

### Calidad de lo que ve la audiencia — sin tocar desde julio

| | |
|---|---|
| **T** | `vocabulary` (tarjeta 61% vacía) y `pronunciation` (10 constantes Y absolutas, 8.4% de tinta en la banda) |
| **C** | Más categorías y temas |

Es lo único de toda la lista que ve alguien que no sea Garcia.

### Bilibili — pedido, a medias

| capa | estado |
|---|---|
| Fuente CJK | ✅ resuelve Noto, lanza `MissingCJKFont` en vez de dibujar tofu |
| Corte de línea | ✅ por carácter con kinsoku, respeta tramos en inglés |
| **Timing de palabra** | ❌ `subtitle_processor.py` y `tts_openai.py` hacen `.split()` — karaoke solo en español |
| Voces | ❌ `BILIBILI_*_VOICE_ID` sin fijar; falla cerrado, que es lo correcto |
| Ruta de subida | ❌ no existe uploader, ni plataforma en `config.yaml`, ni en el ledger |

**No puede producir un video hoy.** Con el timing de palabra y las voces sí puede producirlo; publicarlo es otro trabajo.

### Aparcado, con motivo

- **6c** · motor de layout y colisiones — `exp_y` + `slide_offset` llevan el presupuesto a −6px
- **Mascota** · dibujada e instalada, apagada hasta que 6c le dé sitio
- **TikTok** · no publica en público sin auditoría externa
- **Scheduler** · sus controles falsos ya se quitaron; el real depende de G

---

## 4b · Duración — medido 2026-09-03, sobre 138 pares audio/video

Decisión del dueño: **todos los videos entre 50 s y 1:20**. Hoy **27 de 138 (20 %)** están en banda.

`video = habla + silencio declarado + outro`. El outro son **4.000 s** exactos en las tres variantes, y solo 41 de 138 lo llevan — el corpus legacy es anterior. El silencio declarado vive DENTRO de la narración, así que `video − narración` **nunca lo enseña**: por eso mi primera medición de overhead salió 2.2× alta.

| tipo | n | palabras/s | silencio | overhead | mediana | en banda |
|---|---|---|---|---|---|---|
| educational | 45 | 2.59 | 5.5 | 9.5 | **45.9 s** | 19/45 |
| fill_blank | 28 | 2.04 | 4.5 | 8.5 | 37.8 s | 6/28 |
| quiz | 34 | 1.95 | 6.3 | 10.3 | 39.4 s | 2/34 |
| pronunciation | 12 | 2.28 | 3.1 | 7.1 | 19.7 s | 0/12 |
| true_false | 13 | 1.75 | 4.5 | 8.5 | 26.9 s | 0/13 |
| vocabulary | 6 | 1.36 | 3.8 | 7.8 | 24.3 s | 0/6 |

`objetivo_palabras = (duración_objetivo − overhead) × tasa`

> **`full_script` no es lo que se habla.** En quiz son 140 palabras contra 53 en los segmentos — factor 2.6. Las tasas de arriba salen de los segmentos o del array de Whisper, nunca de `full_script`. Un objetivo de palabras atado a `full_script` estaría enganchado a texto que no se dice.

**Corrección a un número que se venía citando como hecho:** el aire muerto de `educational` es **12.8 % de mediana** (rango 0.5–27.5 % sobre 45 artefactos). El **30 %** que R1 midió está cerca del peor caso, no del típico. Si alguna vez justifica un cambio, que lo justifique la mediana.

**Corrección mía:** dije que `educational` "ya está en rango y solo necesita techo". Salió de 6 muestras. Con 45 su mediana está **por debajo** del suelo y es el tipo con más dispersión (22.0–86.0 s). Necesita los dos bordes.

---

## 5 · Deuda registrada

- `tts_elevenlabs.py:568` — `script.get('correct','A')`, un default que fabrica una respuesta
- La familia `1.3` — 10 sitios en `educational.py`
- La criba de paletas (36 quedan / 24 fuera) sigue sin aplicarse a `enabled_backgrounds`
- 109 artefactos en `output/rejected/`, 1.2 GB, de siete meses
- `output/{scripts,audio,video,final}` — directorio con ese nombre literal, vacío, del 8 de enero
- `output/published/` (ledger) y `output/uploaded/` (mp4) — dos conceptos, nombres que invitan a fusionarlos por error. Renombrar el primero a `output/ledger/` toca los paths por defecto de `publication_log.py`
- `openai_chat` no se registra en el ledger de costes: $0.00 en todos los videos recientes

---

## 6 · Las reglas que este proyecto se ha ganado

Se conservan porque cada una costó un error real. La v16 tiene las mediciones.

> **El fallo dominante de este repo no es código roto: es código correcto que nunca recibe lo que necesita.** Siete instancias, la última es la capa Studio entera.

> **Un paso no está hecho cuando la pieza funciona, sino cuando el camino de producción la llama.** Para cualquier ✅: qué lo invoca, y la prueba de que se ejecutó en la salida real.

> **La puerta mide lo contrario del objetivo.** El gate de contraste sube cuando el fondo desaparece. Lo medido gana siempre a lo declarado, así que hay que vigilar qué se mide.

> **Contar el espacio, no las muestras.** 14 imágenes con 4 prompts son 4 imágenes con ruido.

> **Medir en la etapa que envía.** No en la que es cómoda de instrumentar.

> **Medir dos veces antes de usar un número como hallazgo.** Tres conclusiones de este proyecto murieron al contacto con la segunda medición.

> **La resolución de la medida puede fabricar el fenómeno.** Antes de explicar una forma, comprobar que la forma no es del instrumento.

> **Un default solo puede renderizar MENOS, nunca algo falso.** La ausencia puede esconder un panel; nunca puede fabricar una respuesta.

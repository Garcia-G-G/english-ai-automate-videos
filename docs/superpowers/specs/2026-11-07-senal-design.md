# Señal: diseño

Fecha: 2026-11-07. Estado: borrador para que el dueño lo apruebe. Nada de esto está construido todavía.
Los bocetos de `.superpowers/brainstorm/` (senal-3d, senal-5, senal-5b) fueron desechables; de ellos
se toma la idea, no el código.

## 1. Para qué existe

El canal vive de Shorts. De los datos reales (YouTube Analytics, 2 al 4 de nov):

- ~91 % de las vistas llegan desde el feed de Shorts y ~7 % desde la búsqueda.
- Un video típico junta ~150 vistas el día 1, ~250 al día 2 y después se queda plano.
  **El feed decide en 48 horas.**
- Hay excepciones que no siguen esa curva (por ejemplo «CASA»: 25 % de sus vistas desde búsqueda).

Hoy el panel de Streamlit muestra números en tablas. El dueño quiere otra cosa:

- Ver de un vistazo **cómo le va a cada video en cada plataforma donde se subió** (un video solo
  cuenta en las plataformas donde de verdad está).
- Que el **motor detecte solo** cuando un video se sale de lo normal («una montaña que de repente
  sube») y que se vea **por qué**: de dónde llegan las vistas, si lo comparten, si la gente se queda.
- Que sea **impresionante y propio**. Las referencias son bruno-simon.com, lusion.co, linear.app,
  press.stripe.com e igloo.inc.
- **Sin texto** en esta vista y con control total: girar, acercarse, recorrer los videos y elegir
  la plataforma.

El éxito es que el dueño abra Señal por la mañana, vea en segundos si algún video está despegando
y entienda por qué, sin leer un número.

## 2. Objetivos, no-objetivos y anti-objetivos

**Objetivos**
1. Un paisaje 3D donde cada video reciente es una cordillera y su altura son las vistas por día.
2. Un motor (Python, con pruebas) que calcula qué video rinde por encima de lo esperado para su edad
   y cuáles son las razones, y lo entrega en un JSON.
3. Una vista que lleva la cámara sola al video destacado y muestra el porqué con movimiento y luz.
4. Interacción sin errores: lo que se ilumina es lo que se abre; la cámara nunca pelea con la mano.
5. Datos frescos cada día sin que el dueño haga nada más que abrir el panel.

**No-objetivos (por ahora)**
- Leer Facebook, TikTok o Instagram. Hoy solo YouTube es legible (Facebook necesita el permiso
  `read_insights`; TikTok no tiene videos; Instagram no está enlazado). El diseño los admite: cuando
  una plataforma tenga datos aparece; mientras no, no se muestra.
- Reemplazar el panel de Streamlit. Señal es una página aparte que se abre desde el panel.
- Predecir el futuro con modelos de aprendizaje automático. El motor compara contra la curva típica
  del propio canal; eso basta con ~140 videos.
- Móvil. Se diseña para el Mac del dueño; en pantallas chicas solo debe verse sin romperse.

**Anti-objetivos (fallaría aunque funcione)**
- Burbujas, tarjetas, tablas, pestañas o gráficas 2D estáticas: el dueño ya las rechazó.
- Líneas sin significado. Cada línea, punto y brillo codifica un dato concreto (sección 5).
- Texto en la escena en reposo.
- Clic que abre un video distinto del iluminado, cámara que salta o pelea con el arrastre,
  partículas que salen de lugares sin sentido, cifras que no cambian al elegir otro video.
- Que se vea «básico»: sin postproceso, sin dirección de cámara, con materiales planos.
- Cualquier gasto: leer YouTube Analytics es gratis y no se llama a ningún servicio de pago.

## 3. Restricciones

- Repo `english-ai-videos`, rama `6a-layout`. Python 3.12 en `.venv`. Node 26 y npm instalados.
- Los datos salen de `src/channel_stats.py` (token con `_youtube_token()`, endpoint
  `YOUTUBE_ANALYTICS`, entorno con `env_setup.ensure_env_loaded`). Analytics va ~2 días atrasado.
- Reglas del repo: nada de llaves, `.env`, IDs de voz ni rutas de la casa en commits; las pruebas no
  tocan contenido real (`content/`, `output/`, logs); no editar el árbol mientras hay un render.
- Código, comentarios y commits en inglés; la conversación con el dueño en español.

## 4. Arquitectura

```
YouTube Analytics ──► src/senal.py (motor)  ──►  output/senal/senal.json
                         │  pruebas: tests/test_senal.py
                         ▼
             senal/ (app web, Vite)  ──build──►  senal/dist/
                         ▲
   panel Streamlit: botón «Abrir Señal» → sirve senal/dist + senal.json en localhost
```

**Motor (`src/senal.py`)**, extiende lo que ya hace `channel_stats.py`, sin duplicar sus llamadas:
- Lee por video: vistas por día (`dimensions=day`, filtro por video), origen del tráfico
  (`insightTrafficSourceType`), % visto, segundos vistos, compartidos y suscriptores ganados.
- Lee del canal: vistas y suscriptores por día, y el origen del tráfico total.
- Calcula la curva típica y las puntuaciones (sección 6) y escribe `output/senal/senal.json`.
- Se refresca solo: al abrir Señal desde el panel, si el JSON tiene más de 24 h se regenera antes de
  abrir (mismo patrón que el botón de refresco de `channel_stats`). *Decisión mía:* no se agrega un
  programador del sistema (launchd); el dueño abre el panel a diario.
- **Retraso de Analytics** (*decisión mía*): como Analytics va ~2 días atrás y el feed decide en 48 h,
  los días que Analytics aún no trae se completan con la diferencia entre lecturas del contador en
  vivo de la Data API (`viewCount`, que `fetch_youtube` ya lee). Cada snapshot diario guarda ese
  contador; el día estimado se marca `"est": true` y se dibuja más tenue y con un leve parpadeo hasta
  que Analytics lo confirma. Sin esto, las cordilleras del frente estarían vacías.

**App web (`senal/`)**, independiente de Streamlit:
- Vite + TypeScript, `three` (versión estable actual), `postprocessing` de pmndrs para bloom,
  viñeta y grano de película, y GSAP para todas las animaciones de cámara y transiciones.
  *Decisión mía:* three.js directo, sin React Three Fiber; es una sola escena y no hace falta.
- Lee `senal.json` con `fetch`. Valida la forma del JSON y, si falla, muestra el estado de error.
- Se sirve en `localhost` (un servidor estático de la biblioteca estándar de Python, iniciado por el
  panel). *Lo decide el constructor:* el puerto y si el build se hace en `run_admin.sh` o a mano.

**Contrato del JSON** (versión 1; el constructor puede añadir campos, no quitarlos):
```json
{
  "version": 1, "read_at": "2026-11-07T08:00:00", "data_until": "2026-11-05",
  "platforms": ["youtube"],
  "channel": {"typical_daily": {"how_do_you_say": [0, 153, 98, ...], "quiz": [...], "all": [...]},
              "typical_cum": {"how_do_you_say": [0, 153, 251, ...], "...": [...]},
              "sources": {"SHORTS": 0.91, ...},
              "median": {"retention": 74.0, "shares_per_1k": 1.2, "subs_per_1k": 0.4}},
  "videos": [{
    "id": "…", "platform": "youtube", "format": "how_do_you_say",
    "published": "2026-11-01", "age_days": 6,
    "daily": [0, 153, 98, 12, …], "est_from": 4, "views": 1000, "retention": 58.0,
    "sources": {"SHORTS": 0.70, "YT_SEARCH": 0.25, "EXT": 0.05},
    "shares": 4, "subs": 3,
    "score": 2.4, "state": "breakout", "why": ["search", "retention"]
  }],
  "star": {"youtube": "…id del video destacado o null…"}
}
```
`daily` tiene como máximo 15 valores (días 0 a 14); desde el índice `est_from` son estimados.

## 5. Gramática visual (qué significa cada cosa)

El escenario es un paisaje nocturno visto en perspectiva, como un mapa topográfico iluminado.

| Elemento | Significa |
|---|---|
| Eje de profundidad | Los videos, del más nuevo (al frente) al más viejo (al fondo). Videos publicados en los últimos 14 días; 28 o 60 días con el control de periodo (solo cambia cuántas cordilleras hay). |
| Eje horizontal | Días desde que se publicó cada video, siempre de 0 a 14 (*decisión mía*: el feed decide pronto; lo que pasa después del día 14 no se dibuja). Todos arrancan alineados: así se comparan a la misma edad. |
| Plataforma | Una a la vez (*decisión mía*): el control de plataforma filtra el paisaje y cada plataforma tiene su propio destacado. Un video subido a dos plataformas aparece en las dos vistas. |
| Altura de la cordillera | Vistas por día de ese video (escala con raíz para que los chicos no desaparezcan). |
| **Cordillera fantasma** | La curva típica **diaria** del formato de ese video (`typical_daily`), dibujada detrás de él como una línea tenue, en la misma escala que la cordillera real. Donde la cordillera real supera a su fantasma, el video rinde más de lo esperado: es lo que da sentido a las líneas. |
| Trazo de la cordillera | Una línea luminosa fina. Debajo, una cortina de líneas verticales finas (una por muestra) hasta el suelo. Así el paisaje es de líneas, no de superficies. |
| Brillo de la cortina | Cuánto del video ve la gente (% visto): más brillante, más se queda. |
| Corrientes de partículas | El origen de las vistas. Fluyen **a lo largo de la cordillera** desde su base hasta la cima, con un color por origen: feed de Shorts (azul `#3987e5`), búsqueda (verde agua `#199e70`), externo (naranja `#d95926`). La proporción de partículas sigue la proporción real. |
| Chispas doradas | Compartidos: suben desde la cima, una ráfaga por cada compartido (con tope). |
| Puntos blancos que quedan flotando | Suscriptores ganados con ese video. |
| Pulso en el suelo | El video destacado por el motor: un anillo que late bajo su cima. |
| Cordilleras apagadas | Videos que el motor considera «dentro de lo normal»: se ven, pero en segundo plano. |

Paleta de escena (*decisión mía*, a afinar en la fase de dirección de arte): fondo azul tinta muy
profundo `#05070f` con niebla de distancia, líneas en blanco frío `#dfe6ff` a baja opacidad, y los
tres colores de origen ya validados para daltonismo. Nada de verde ácido ni crema.

Tipografía: no hay texto en reposo. Si hace falta en el modo de cifras (sección 7), una sola familia,
*decisión mía*: «Inter Display» o similar, cifras tabulares, nunca en mayúsculas.

## 6. El motor: qué es «viral» y qué es «por qué»

**Curva típica** (*decisión mía* sobre el grupo de comparación): se calcula por formato (quiz,
how_do_you_say, …) con los videos de ese formato publicados en los últimos 90 días; si un formato
tiene menos de 8, se usa la de todo el canal (`all`). Para cada edad `d` (0–14 días) hay dos curvas:
la mediana de vistas **acumuladas** a esa edad (`typical_cum`, para puntuar) y la mediana de vistas
**de ese día** (`typical_daily`, para dibujar el fantasma). En ambas se excluye al video que se evalúa.

**Puntuación:** `score = vistas acumuladas del video a su edad / curva típica a esa edad`.

**Estados** (*decisión mía*, umbrales en una constante para ajustarlos con datos):
- `breakout`: `score ≥ 2.0` y al menos 300 vistas.
- `second_wind`: después del día 2 sus vistas diarias vuelven a subir por encima del día 2 (el feed lo
  volvió a empujar), aunque el `score` total sea menor.
- `normal`: el resto. `cold`: `score ≤ 0.5` pasado el día 2.
- Si aplica más de uno, gana en este orden: `breakout`, `second_wind`, `cold`, `normal`.

**Destacado (`star`):** el video con mayor `score` entre los `breakout`/`second_wind` de los últimos
14 días; si no hay ninguno, `null` y la escena abre en vista general.

**Por qué (`why`):** se comparan cuatro factores contra la mediana del canal y se guardan los que la
superan por más de 1.5×, ordenados de mayor a menor:
- `search` / `external`: su parte de vistas desde búsqueda o desde fuera es mayor que la del canal.
- `retention`: su % visto es mayor.
- `shares`: compartidos por cada 1.000 vistas.
- `subs`: suscriptores por cada 1.000 vistas.

En la escena, el primer factor de `why` es el que se exagera al llegar la cámara (por ejemplo, si es
`search`, la corriente verde agua se ensancha y acelera; si es `retention`, la cortina se enciende).

Todo esto se prueba con `pytest` sobre datos sintéticos (curvas inventadas con resultado conocido),
sin red y sin tocar `output/` real.

## 7. Interacción y cámara

**Apertura (una sola secuencia orquestada, ~3 s):** el suelo aparece, las cordilleras crecen desde
cero de la más vieja a la más nueva, y si hay `star` la cámara vuela hacia ella y se activa su porqué.
Con «reducir movimiento» del sistema se salta directo al estado final.

**Controles (todo con ratón y con teclado):**
- Arrastrar: girar alrededor del punto que se mira. Rueda: acercarse. Doble clic en el suelo: volver
  a la vista general.
- Pasar el ratón sobre una cordillera: se ilumina **esa** cordillera (selección por proximidad a la
  línea de la cima en pantalla, no por el triángulo que haya debajo). Clic: la cámara vuela a ella y
  muestra su porqué. Lo iluminado y lo abierto siempre salen de la misma función de selección.
- Flechas izquierda/derecha: video anterior/siguiente. `Esc`: vista general. `Espacio`: ir al
  destacado.
- Mientras la cámara vuela, el arrastre del usuario cancela el vuelo y toma el control (nunca pelean).

**Controles en pantalla (sin palabras):** una barra mínima abajo con íconos: plataformas (solo las que
tienen datos), periodo (14/28/60 días como marcas, no como texto), volver al destacado, y un botón para
el **modo cifras**.

**Modo cifras** (*decisión mía*, para no perder la información sin romper la regla de no texto):
apagado por defecto; al activarlo (o al mantener `Alt`) aparecen, junto al video elegido, sus vistas,
% visto y la edad, con tipografía cuidada. Al soltar desaparecen.

**Accesibilidad:** una tabla oculta para lectores de pantalla con los mismos datos, foco visible en
la barra, y el estado `prefers-reduced-motion` respetado.

## 8. Estados que también se diseñan

- **Cargando:** el suelo con una línea que barre; nunca una pantalla negra.
- **Sin datos o JSON inválido:** el paisaje vacío y un único mensaje que dice qué pasó y qué hacer
  («No pude leer YouTube: vuelve a conectar la cuenta en el panel»). Única excepción a «sin texto».
- **Datos viejos (>48 h):** el horizonte pierde color; en modo cifras se ve la fecha.
- **Sin destacado:** vista general, todas las cordilleras con el mismo peso.

## 9. Calidad y rendimiento

- 60 fps en el Mac del dueño con 60 videos visibles; la escena se pausa cuando la pestaña no se ve.
- Sin errores en la consola. Cada fase se prueba en Chrome real con capturas antes de enseñarla.
- Cero llamadas de red salvo `senal.json` y las fuentes.

## 10. Cómo se construye (fases)

Cada fase termina con algo que se puede abrir y ver; el dueño revisa en las fases marcadas.

1. **Motor y datos:** `src/senal.py`, pruebas, `senal.json` real generado.
2. **Dirección de arte (revisión del dueño):** 2 o 3 cuadros fijos renderizados con la escena real
   (paleta, niebla, grosor de líneas, bloom) para elegir el aspecto antes de animar nada.
3. **Escena base:** paisaje, cordilleras, fantasmas, cortinas, cámara con GSAP, selección correcta.
4. **El porqué:** corrientes, chispas, suscriptores, pulso del destacado, apertura orquestada
   (revisión del dueño).
5. **Controles, teclado, modo cifras, estados vacíos y de error, accesibilidad.**
6. **Integración:** botón en el panel, refresco diario, servidor local (revisión final del dueño).
7. **Opcional, si el dueño lo pide:** sonido ambiental suave, apagado por defecto.

## 11. Lo que queda al constructor

- Estructura interna de `senal/` y de los módulos TypeScript.
- Shaders concretos, cantidades exactas de partículas, curvas de easing y duraciones.
- Puerto del servidor local y cómo se lanza el build.
- Ajuste fino de umbrales del motor, siempre en una constante con su prueba.

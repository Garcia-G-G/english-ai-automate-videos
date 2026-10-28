# STEP 80 §3 — a faster panel

Measured with `tools/panel_timing.py` (Streamlit's AppTest runs each page's own script; «cold» is a
fresh session's first run, «warm» the median of three reruns — what a click costs). All pages are
measured in one process, so after Inicio the other pages' «cold» shares the warm imports; a real
first open of any page costs about what Inicio's cold does. Target: ≤ 1.0 s warm, ≤ 2.5 s cold.

| page | before cold (s) | before warm (s) | after cold (s) | after warm (s) |
|---|---|---|---|---|
| Inicio | 3.19 | 1.2 | 1.78 | 0.49 |
| Crear | 0.99 | 0.68 | 0.37 | 0.3 |
| Cola | 0.65 | 0.64 | 0.29 | 0.3 |
| Revisar | 0.62 | 0.7 | 0.26 | 0.29 |
| Subir | 0.87 | 0.79 | 0.42 | 0.37 |
| Biblioteca | 0.72 | 0.83 | 0.26 | 0.3 |
| Temas | 0.74 | 0.72 | 0.29 | 0.28 |
| Programar | 0.72 | 0.74 | 0.39 | 0.28 |
| Ajustes | 1.94 | 1.41 | 0.34 | 0.31 |
| Registros | 0.92 | 0.85 | 0.29 | 0.3 |
| Rendimiento | 0.83 | 0.87 | 0.31 | 0.34 |

**What the profile showed and what changed**
- **Every page** paid 0.37–0.41 s per click for `voice_credits.remaining()`: a failed balance read
  (the ElevenLabs key answers 401) was never cached, so it went to the network on every rerun. A
  failure is cached for the same 60 s now.
- **Ajustes** computed the cleanup plan (a walk of the output tree: 0.4 s warm, 1.7 s cold) on every
  visit. It now waits for «Calcular qué se puede limpiar».
- The other data reads (pending, approved, ledger, census, costs) measured 0.000–0.009 s: no change
  needed. The queue pick for «Siguiente mejor» is 0.12 s.

**«Crear» stops repeating «Inicio»**: its «Recent (Last 5)» history (the same failures Inicio lists)
is gone; it keeps only the progress of what is running, so a click shows it landed, and a line
pointing to Inicio.

**Spanish labels**: «Configuración», «Tipo de vídeo» with each type's own name («Elige la
correcta», «Cómo se dice»…, from `video_types` `dashboard`), «Tema» (Al azar / Elegir categoría / Tema
concreto), «Categoría», «Opciones», «Perfil de audiencia», «Usar un guion de la cola», «Prueba (sin voz
ni render)», «En marcha»; the type filters on Revisar and Biblioteca and the Registros filter.
Settings tabs and some older captions elsewhere are still in English.

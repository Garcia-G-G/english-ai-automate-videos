# Limpieza de lo que quedó público — 29 sep 2026

El push de `6a-layout` publicó 68 commits en un repositorio **público**
(`Garcia-G-G/english-ai-automate-videos`). No había ninguna clave, ni `.env`, ni
token: se comprobó buscando los patrones de OpenAI, ElevenLabs, Google, Slack y
GitHub en todo el árbol. Pero quedaron públicas cuatro cosas. Esto es lo que se
hizo con cada una.

## Hecho en el código

| qué | dónde estaba | ahora |
|---|---|---|
| ID de la voz del canal | 4 archivos de `src/`, `.env.example`, un test, una nota | sólo en `.env` |
| ruta de tu carpeta de usuario en el Mac | `run_admin.sh`, dos notas de `_audit/` | fuera; `run_admin.sh` busca streamlit en el `user-base` de quien lo ejecute |
| correo personal en commits **nuevos** | `git config` del repo | `62484989+Garcia-G-G@users.noreply.github.com` |

**La voz ya no tiene valor por defecto en el código.** Antes, si `.env` perdía
`ELEVENLABS_VOICE_ID`, el código usaba la voz escrita a mano y nadie se enteraba.
Ahora todas las llamadas a ElevenLabs pasan por un único control
(`_elevenlabs_with_retry` en `tts_elevenlabs.py`, y el equivalente en
`tts_bilingual.py`) que se niega a llamar a la API y dice dónde ponerla. El plan en
seco de `pipeline.py` muestra `(sin configurar…)` en vez de fallar.

`VOICES` en `tts_elevenlabs.py` conserva las nueve voces públicas de ElevenLabs
(Rachel, Adam…): son de la biblioteca pública y no identifican al canal. Nadie lee
ese diccionario.

## Lo que el código NO puede limpiar: el historial

Quitar algo de los archivos no lo quita de los commits anteriores. El ID de la voz,
la ruta y **tu Gmail en 236 commits** (109 de ellos en `main`, público desde enero)
siguen en el historial. Hay dos formas de cerrarlo:

**1. Hacer el repositorio privado — recomendado.** Cierra las cuatro cosas de golpe,
historial incluido, y se puede deshacer cuando quieras. Con 0 forks, nadie tiene
copia. GitHub → el repositorio → *Settings* → abajo del todo, *Danger Zone* →
*Change visibility* → *Make private*.

**2. Reescribir el historial — sólo si algún día lo vuelves a hacer público.**
Cambia el hash de todos los commits, así que rompe cada referencia `a69ee37`,
`9d70794`… que hay en las notas y los informes, y obliga a un `push --force` sobre
`main`. Con el repo privado no gana nada. Si llega el día, el procedimiento es
`git filter-repo` con un `.mailmap` que cambie `gilbergarciata@gmail.com` por la
dirección `noreply`, y un `--replace-text` para el ID y la ruta. Se hace antes de
volver a publicar, no después.

## El contenido

Los 103 guiones de la cola, las 18 lecciones de Manim y la marca **no estaban en
`main`**; se publicaron por primera vez con este push. Que sean públicos o no es una
decisión de negocio, no de seguridad. Hacer el repo privado también la resuelve.

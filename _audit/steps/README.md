# Steps

Every file here was one step of work: written, executed and closed. They are kept for
the reasoning and the evidence behind each change, **not for their numbers**: the numbers
in a step expire as soon as the change is committed. When a step and the code disagree,
the code wins:

| to know | look at |
|---|---|
| duration constants and bands | `config.yaml`, `duration` block |
| which video types exist | `src/video_types.py` |
| brand colours and type | `assets/branding/english-unlimited/brand.json` |
| audio repair (tails, gaps, onsets) | `src/tts_common.py` |

New steps take the next number (`STEP_54.md`, …). A `b` file is an addendum to the step
with the same number.

| step | what it was |
|---|---|
| [STEP 1](STEP_01.md) | FIX ALL VIDEO BUGS — Educational + Quiz/Test Videos |
| [STEP 2](STEP_02.md) | URGENT FIX: Video Subtitle System is Completely Broken |
| [STEP 3](STEP_03.md) | Animation Upgrade |
| [STEP 4](STEP_04.md) | ElevenLabs TTS Optimization — Analysis |
| [STEP 5](STEP_05.md) | FIX: Educational Video Text-Audio Sync (Text Goes Faster Than Voice) |
| [STEP 6](STEP_06.md) | FIX: Educational Video Display — English Words Isolated, Missing Translations, Sync Issues |
| [STEP 7](STEP_07.md) | FIX: Educational Video Text Bugs (Words Mixing Between Sentences) |
| [STEP 8](STEP_08.md) | FIX: Educational Videos Not Generating (Critical Bug) |
| [STEP 9](STEP_09.md) | FIX: Text Overflow, Font Size, Group Size, and Translations |
| [STEP 10](STEP_10.md) | Visual Bugs + Dashboard TTS Fix |
| [STEP 11](STEP_11.md) | Paso 0 |
| [STEP 12](STEP_12.md) | Paso 1 |
| [STEP 13](STEP_13.md) | Paso 2 |
| [STEP 14](STEP_14.md) | Paso 3 |
| [STEP 15](STEP_15.md) | Publicación automática de YouTube |
| [STEP 16](STEP_16.md) | `fit_text_font` → caja medida |
| [STEP 17](STEP_17.md) | C0 — de `--batch` a un video publicado |
| [STEP 17b](STEP_17b.md) | C0 · un contrato, no un validador más blando |
| [STEP 18](STEP_18.md) | El dashboard deja de tirar lo que el pipeline calcula |
| [STEP 19](STEP_19.md) | Reestructurar el dashboard por el ciclo de vida del artefacto |
| [STEP 20](STEP_20.md) | E1b — la privacidad se elige, no se hereda de un dataclass |
| [STEP 21](STEP_21.md) | E4a — el Inicio deja de contar y empieza a mostrar trabajo |
| [STEP 22](STEP_22.md) | El fondo generado solo existe en `--batch` |
| [STEP 22b](STEP_22b.md) | Adenda: el tercer sitio, y la decisión |
| [STEP 23](STEP_23.md) | El catálogo se mudó a los prompts |
| [STEP 23b](STEP_23b.md) | F3 — adenda: dónde no acompaño el informe |
| [STEP 24](STEP_24.md) | L1 — la caja dice que no cabe, y se dibuja igual |
| [STEP 25](STEP_25.md) | T1 — la duración pasa a ser una especificación, no un accidente |
| [STEP 26](STEP_26.md) | T2 — precisión del contenido: objetivo por ítem, tema coherente, tiempos reales |
| [STEP 27](STEP_27.md) | TXT — la puntuación deja de ser una palabra |
| [STEP 28](STEP_28.md) | TXT · segunda mitad — terminar el mismo bug |
| [STEP 29](STEP_29.md) | TXT · tercera parte — una tarjeta, una oración |
| [STEP 30](STEP_30.md) | V1 — fondos que se mueven de verdad |
| [STEP 31](STEP_31.md) | The vocabulary table draws text it already knows will not fit |
| [STEP 31b](STEP_31b.md) | VOCAB addendum — the badge gutter. Same step, not a new one. |
| [STEP 32](STEP_32.md) | The pronunciation layout is ten coordinates, and the slot is |
| [STEP 33](STEP_33.md) | The width check belongs in the shared function, and one more |
| [STEP 34](STEP_34.md) | The audio sounds chopped |
| [STEP 35](STEP_35.md) | Stop the code-switch truncation |
| [STEP 36](STEP_36.md) | Try not to lose it, then reconstruct what is lost |
| [STEP 37](STEP_37.md) | The instrument is fixed, the proof is still owed |
| [STEP 38](STEP_38.md) | The gaps, not the cuts |
| [STEP 39](STEP_39.md) | The entries — and a hole Step 4 made visible |
| [STEP 40](STEP_40.md) | Closing the "cortado antinatural" thread |
| [STEP 41](STEP_41.md) | Audit before the five new types: what a video type costs today |
| [STEP 42](STEP_42.md) | Reply to your audit: apply 1, 3-5 with changes. Do NOT apply 2. |
| [STEP 43](STEP_43.md) | Close the audit, then make the voice sound the way the scripts were written |
| [STEP 44](STEP_44.md) | Two questions per quiz — and the band that cannot serve six types |
| [STEP 45](STEP_45.md) | New video type #1: `how_do_you_say` ("¿Cómo se dice…?") |
| [STEP 46](STEP_46.md) | Manim lessons: brand, legibility and "grammar in motion" |
| [STEP 47](STEP_47.md) | Manim Phase C: neutral stage by default, and more life |
| [STEP 48](STEP_48.md) | Manim lesson audio: harsh "s" and stutters at the start |
| [STEP 49](STEP_49.md) | The "level" family: three new Short types on one engine |
| [STEP 49b](STEP_49b.md) | Addendum: background footage for the three level categories |
| [STEP 50](STEP_50.md) | A voice that sounds less "AI made": one probe, then a decision |
| [STEP 51](STEP_51.md) | Owner's verdict on the Manim onset A/B (2026-10-14) — make variant 4 the default |
| [STEP 52](STEP_52.md) | Clean the public history: no tool attribution, steps instead of prompts |
| [STEP 53](STEP_53.md) | More, and less repeated, background footage |

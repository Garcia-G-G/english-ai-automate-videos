# STEP 80 §6 — a better outro for LearningRoutes

- **Length kept**: 4.0 s (the STEP says «about 2.5 s; keep the current length» — the current is 4.0).
- **Top**: the v3 logo's wordmark («English Unlimited», cropped from `logo_horizontal.png`), then
  «Mañana:» and the queue's next topic of the same type, ending above Bubi's head:
  - how_do_you_say: «¿Cómo se dicen los ANIMALES DEL MAR? 🐬» (the article kept, «dice/dicen» by it,
    the first item's emoji drawn as art);
  - the series: the next queued script of the same style, its title without «RETO:»;
  - other types: their theme in capitals; no other script → «Síguenos para el siguiente».
- **Card**: Bubi waving on its top edge (unchanged), «Aprende inglés en», **learningroutes.com**,
  «Rutas para aprender lo que quieras», and a small «Link en la bio». Narrowed from 900 to 784 px
  (x 148–932): the old card and URL reached under the Shorts button rail (x > 940 from y 950).
- **Safe areas**: tested on the still — everything between y 154 and 1498, nothing right of x 940
  below y 950 (shadow included). The series' «¿Acertaste?» stays under the card.
- **Audio**: the variant's cached voice. The three cached clips were redrawn in place
  (`ensure_outro(force=True)`, no TTS). Since the line changes per video, `finalize_video` renders
  this video's 4 s of picture over that voice (same compositor, same stream parameters, so the concat
  stays `-c copy`); the sidecar records `outro_next`.
- Proof from cache: hc_m001, PASS, $0 — «Mañana: Mi amigo me dijo «I'm down» y pensé que estaba triste».

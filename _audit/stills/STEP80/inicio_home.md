# «Inicio», faster and plainer (Garcia, 27 Oct: «velocity without losing quality»)

What changed on the page, top to bottom:
- **Hoy**: four numbers first — Por revisar · Por subir · Vídeos publicados (7 días; distinct videos,
  not one ledger row per platform) · OpenRouter this month against its cap.
- **Siguiente vídeo**: the best queued script in words («Cómo se dice · las partes de la casa»), why
  it is next (no internal type key), and one button, «▶ Producir ahora». Empty queue: what to do.
- **Copy** (design:ux-copy): verbs on the actions («A revisión», «Revisar», «Subir»), empty states
  that say what to do next, no disk paths or English leftovers («output/pending/», «ledger.jsonl»,
  «DESACUERDO», «Selecting...», «queued (job …)»), the month by name, «Fallos recientes», «Crear rápido».
  The list-vs-disk cross-check (STEP D0) stays, in fewer words; the batch block shows only when
  something is in it.
- **Coste por vídeo** gets its OpenRouter column.

Speed (tools/panel_timing.py, AppTest, same machine as §3):

| page | §3 after | now |
|---|---|---|
| Inicio cold | 1.78 s | 1.61 s |
| Inicio warm (a click) | 0.49 s | 0.29 s |
| every other page warm | ≤ 0.42 s | 0.23–0.41 s |

Where the warm time went, measured with a line tracer on admin.py's top level: the queue ranking
re-read and re-scored ~600 scripts per click (now cached on the files' mtime/size), config.yaml was
parsed 27 ms at a time several times per click (now once per change), the month's OpenRouter spend
re-read every cost file (now per file, per change). Cold: `openai` (0.3 s) is imported only when a
script is generated. In a real browser (Playwright): 2.0–2.5 s to a settled page, 0 exceptions.

Found and fixed on the way: `test_performance`'s Facebook test reloaded `.env` and reached the real
Graph API when run after a test that imports the panel; it now cannot.

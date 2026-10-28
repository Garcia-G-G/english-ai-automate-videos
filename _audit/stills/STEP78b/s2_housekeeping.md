# STEP 78b §2 — housekeeping

1. **Skipped scripts.** The guard blocked 6, not 7 (the seventh, a second how_do_you_say, was
   rendered by the panel between the STEPs). They are in `content/queue/_skipped/` with a README
   naming each file and the topic that already has a video. `queue_guard.queued_scripts()` leaves
   `_skipped/` out like `_done/` and the series; the guard now reports 446 queued, none blocked.
   Two tests read bv001_familia and cu001_saludos from the queue: the first now also looks in
   `_skipped/`, the second takes any queued vocabulary script.
2. **Inter licence.** `assets/fonts/OFL-Inter.txt` is now, byte for byte, `LICENSE.txt` of rsms/inter
   at tag v4.0 (the vendored Inter-Bold/ExtraBold say «Version 4.000;git-a52131595»):
   https://raw.githubusercontent.com/rsms/inter/v4.0/LICENSE.txt, sha256 262481e8…54935a, pinned in a
   test.
3. **A real render from the panel.** Streamlit has no HTTP route per button: a click goes over the
   page's websocket (`/_stcore/stream`) as a rerun, and the rerun calls
   `admin.start_series_generation(style, level)`. So the panel was started on its own port
   (`python3 -m streamlit run src/admin.py --server.port 8599 --server.headless true`) and a headless
   Chromium (Playwright) opened `http://localhost:8599/?page=Generate`, chose Video Type «Hecho con
   Claude», Estilo comic, Nivel Medio («9 guiones en cola») and pressed «Crear video».
   - Job 2b94fa44, hc_c010: rendered, then **REJECT** — `english_unheard:for`,
     `english_unheard:since three o'clock`. The local whisper wrote «since 3 o clock» and the lone
     «for» as «4»: the English was said, the gate compared spelling. Filed the normal way:
     `output/rejected/hecho_con_claude/hc_c010_20261022_152257.mp4`, the script kept in the queue.
     TTS $0.128.
   - The gate now compares by sound (numbers as words, «o clock» as one word, four/for and
     two/to/too folded); the rejected video re-gated: PASS.
   - The 8599 server restarted (its processes held the old gate), the button pressed again: job
     0a324477, hc_c010 from the voice cache, **PASS** (−14.1 LUFS, TP −2.4, 36.1 s, longest still
     1.37 s) → `output/pending/hecho_con_claude/hc_c010_20261022_152603.mp4` with its sidecar
     (title, caption, 5 hashtags, gate), and `hc_c010.json` moved to `content/queue/_done/`. TTS $0.
   - The 8599 server was stopped. Garcia's panel was not touched.

**Found by this render: the STEP 78 §7 sidecar broke the panel.** `series.render_one` wrote the whole
gate report under `gate`; the panel (`admin.gate_record`, Inicio, Revisar) reads `gate` as a verdict
string, so the first series video in `pending/` made `import admin` fail («unhashable type: 'dict'»,
8 test files at collection). The sidecar now has the house shape: `gate` "PASS"/"REJECT",
`blocking_flags`, and the full report under `gate_checks`; the two hc_c010 sidecars on disk were
converted. A test now passes a series sidecar through `admin.gate_record`.
- `tools/level_length_report.scripts` (the level corpus: queue + `_done`) now counts `_skipped/` too: a set-aside script is still one of the family's 100 written scripts.

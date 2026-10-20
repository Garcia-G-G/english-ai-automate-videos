# STEP 71 — Bubi in the videos: the Shorts outro and the lesson end card

Context: Garcia approved brand v3 («cuaderno + Bubi») and already uses it on every network. The brand files were replaced in place, same names, by the commit that adds this STEP: `assets/branding/english-unlimited/{simbolo_512.png, logo_horizontal.png, perfil_*, banner_youtube_2560x1440.png, guia_de_marca.*}`, `assets/branding/{app_icon.png, tiktok_profile.png}`, and `brand.json` (version "v3 cuaderno + Bubi", colour `coral`, a `mascot` block). Mocks: `_audit/mocks/STEP71/mock_cierre_short.png` and `mock_cierre_leccion.png`.

Do this after STEP 72. Section by section: tests and one pushed commit per section; stop at the first failure and report. Cost must stay $0: no TTS call anywhere in this STEP.

## §1 Shorts outro card (src/video/outro.py)
- `simbolo_512.png` is now Bubi waving (668 px, transparent, with arms and the EN badge). At the current `SYMBOL_PX = 170` he is too small and his arm runs off the card. Follow the mock: Bubi about 440 px wide, centred, standing on the card's top edge so his body overlaps the edge by ~70 px; move the card down as the mock does (card centre ~60 px below the frame centre) and keep the card's text where it is relative to the card.
- Keep everything else on the card (lines, marker, colours, sizes, the URL auto-shrink).
- Redraw the three cached clips in `assets/outro/` with `ensure_outro(variant, force=True)`. That path keeps each clip's existing voice; prove it: a test (or the run's log) shows `generate_segment_audio` was never called, and each new clip's audio stream is byte-identical to the old one's (`ffmpeg -i old -map 0:a -c copy -f md5 -` vs new).
- Proof: a still of each variant at t = 2.0 s in `_audit/stills/STEP71/`, plus the clip durations (still 4.0 s).

## §2 Lesson end card (experiments/manim_voiceover_poc/lesson_scene.py, `end_screen`)
- `logo_horizontal.png` is now 1871×600 (was 1434×308), so at `scale_to_fit_width(4.4)` it is ~1.4 units tall instead of ~0.95. Follow the mock: width ~4.7, centre y ~2.7, and check it clears the «Sigue aprendiendo» title by at least 0.25 units; keep the two end-screen frames exactly where they are (YouTube pins its elements to them).
- Dark theme: the logo keeps sitting on its paper plate (the plate grows with the new logo's size).
- Do not re-render whole lessons. Render only the end card for sand and dark (a test scene or a short render that jumps to `end_screen`, whichever is fastest) and save stills to `_audit/stills/STEP71/`. Add a test that the logo's bottom stays above the title's top by ≥ 0.25 units.

## §3 Nothing else still shows the old brand
- `git grep -n "simbolo_512\|logo_horizontal\|perfil_1024\|app_icon"` and list every consumer; each one either uses the new files as they are or is fixed here. The owl in `assets/characters/owl` is not used by any renderer; leave it.
- The panel (if it shows `app_icon.png` or the logo anywhere): one screenshot with `tools/ui/shoot_pages.py` of the page that shows it.

## §4 Push
- The queue moves were already committed in STEP 72 §0 (53fcdab). Just push.

## Report
Per section: commit hash, tests and results, the stills' paths. End with `git log --oneline -8` and `git status --short`. Then stop.

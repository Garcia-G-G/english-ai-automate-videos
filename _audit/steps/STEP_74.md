# STEP 74 — Clean the folder (11 GB) and keep it clean with `make clean`

Context: the repo folder weighs 11 GB; most of it is old output Garcia never looks at. Garcia decided (2026-10-20): delete the videos already uploaded, the rejected ones, production folders older than 14 days, and make the cleanup a repeatable command. Do this after STEP 73. Section by section, tests and one pushed commit per section; stop at the first failure.

Measured on 2026-10-20 (du): output 5.4 G (artifacts 2.0, uploaded 1.9, rejected 1.8, clips 1.0, audio 0.17, qa 0.12, approved 0.11, r1_verify, step3_verify, frames, voice_tests*), assets/clips/_cache 1.9 G (Pexels), experiments/manim_voiceover_poc 1.7 G (media 0.59, renders 0.50, audio 0.21, .venv 0.35), _to_delete 0.64 G.

## §1 `tools/cleanup.py` + `make clean-dry` / `make clean`
Rules (one function per rule, each returns the paths and bytes it would free):
1. `output/uploaded/` — everything.
2. `output/rejected/` — everything.
3. `output/artifacts/<artifact>/` older than 14 days (mtime of the folder's newest file) — EXCEPT any artifact that is approved and not yet uploaded to every platform it is meant for (ask the ledger/attempt log and `output/approved/`), or queued in the Meta queue, or `in_doubt`/held. When unsure, keep it and list why.
4. `output/clips/`, `output/frames/`, `output/r1_verify/`, `output/step3_verify/`, `output/voice_tests*/` — everything (pipeline intermediates and old verification).
5. `_to_delete/` — everything (it was already set aside for deletion).
6. `experiments/manim_voiceover_poc/media/` — Manim's partial-movie cache, everything.
7. `experiments/manim_voiceover_poc/renders/<lesson>/` — keep the newest render set (mp4 + srt + timeline + chapters + jpg sharing one stem) per lesson and theme, plus any render a ledger/reviews entry marks as published or approved; delete older sets. Never touch `ledger.jsonl`, `reviews.jsonl`, `jobs/`.
8. `assets/clips/_cache/` (Pexels) — delete clips not used in the last 30 days (by atime if reliable on macOS, else by mtime) and then cap the cache at 1 GB, oldest first. Pexels is free; a deleted clip is downloaded again when needed.
9. `.pytest_cache/`, every `__pycache__/` outside `.venv`.

Never delete: anything tracked by git (`git ls-files` — the tool refuses such a path and the test proves it), `.git`, `.env*`, `.tokens*`, `content/`, `output/approved/`, `output/audio/` and every TTS/voice cache (they cost money), `experiments/manim_voiceover_poc/audio/`, `.venv/`, `assets/` other than `assets/clips/_cache/`, `logs/`, `output/published/`, `output/costs/`, `output/scripts/`, `output/qa/design_proposals/`.

`make clean-dry` prints a table per rule (count, size) and the total; writes nothing. `make clean` prints the same table, asks `¿Borrar? [s/N]`, and only on `s` deletes and prints the freed total. Tests on a temp tree: each rule, the never-delete list, the git-tracked refusal, the "approved but not uploaded" keep, the 14-day boundary, the 1 GB cache cap.

## §2 Run it once, for real
- `make clean-dry`, paste the table in the report.
- `make clean` (answer `s` yourself — Garcia approved these categories). Report `du -sh .` before and after, and `du -sh` of output, assets/clips/_cache, experiments.
- Then run the full suite and open the panel once (Inicio, Subir, Manim) to prove nothing it needs was removed.

## §3 Keep it clean
- The panel: a small «Limpiar» card in Ajustes (or wherever settings live) that shows what `clean-dry` would free and a button that runs the same cleanup after a confirmation.
- README: one paragraph on what `make clean` deletes and what it never touches.
- Push. Report per section: commit, tests, proof. End with `git log --oneline -8` and `git status --short`.

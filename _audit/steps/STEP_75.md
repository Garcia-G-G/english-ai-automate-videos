# STEP 75 — Safety fixes and output quality (audit wave 1)

Source: `_audit/AUDIT_2026-10-20.md` (items in brackets). Do this after STEP 74. Section by section: tests and one pushed commit per section; stop at the first failure. Cost: $0 (no new TTS; re-render from cached audio).

## §0 Measure the baseline first
Pick the newest approved how_do_you_say artifact and one level-mode artifact. Record for each final: video bitrate, keyframe count/median gap (`ffprobe -skip_frame nokey`), `has_b_frames`, color tags, integrated LUFS / true peak / LRA (`ebur128`), duration, and render seconds from its log. Paste the table; §4 and §6 compare against it.

## §1 Settings «Save» must never wipe config.yaml [33]
Replace the panel's config editors with key-level patches that preserve every other key and the comments (ruamel.yaml round-trip), written to a temp file + `os.replace`, with a timestamped backup next to it (gitignored). Remove editors for settings nothing reads [36]: `video.width/height/fps/animation_style`, `humanize`, `speaker_boost`, `output.*`, the placebo «Start Scheduler». Test: saving one key leaves the rest of the file byte-identical except that key.

## §2 Timeouts on every external command [35]
One helper (`src/proc.py: run(cmd, timeout, ...)`) for ffmpeg/ffprobe/Manim calls; replace the bare `subprocess.run/Popen` calls listed in the audit (qa_gate, outro, media_validation, publishers/common, tts_common, manim_studio). A timeout raises, is logged with the command's stderr tail, and releases the render lock. Manim lesson renders get a limit of 3× the lesson's audio length. Test with a fake command that sleeps.

## §3 Small panel guards [39]
- `.env` writes: temp file + rename, values validated through `config/secrets`, newlines rejected.
- A corrupt sidecar JSON shows as «archivo dañado» instead of crashing the page.
- «Generate Batch Now»: confirmation with the count and an estimated cost; routed through the existing batch queue.
- `tools/cleanup.py`: never delete an artifact whose state is `ready_for_review` (11 exist today and the panel cannot show them yet — STEP 79 fixes that). Test.

## §4 Shorts encoder and colour [1, 2, 6]
- `compositor.py`: drop VideoToolbox; libx264 `-crf 17 -preset slow -g 60 -bf 3 -profile:v high -pix_fmt yuv420p`, BT.709 conversion and tags (`scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int`, `-colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv`).
- Catch `BrokenPipeError` from the ffmpeg pipe, log ffmpeg's stderr, raise `RuntimeError`.
- Final file `-movflags +faststart`; the QA gate checks the FINAL duration (after the outro) against the type's band.
- Re-render the 3 cached outros with the same settings (their audio is copied as today, $0) so `-c copy` concat still matches.
- Proof: re-render the §0 how_do_you_say artifact from its cached audio and script ($0). Report the same table; colour check: sample the title blue and sticky yellow from the decoded frame and compare to #1B6FA8 / #F2D66B (ΔE).

## §5 Loudness for Shorts [3]
- Before concat: bring each clip to the median loudness of the clips (reuse `gen_audio.level_match` logic; clamp ±6 dB).
- After concat: two-pass `loudnorm=I=-14:TP=-1.5:LRA=7:linear=true` on the narration, then the mux. Durations do not change (assert it).
- Outro audio normalised to the same target when the outros are redrawn in §4.
- QA gate: integrated −14 ±1 LUFS, true peak ≤ −1 dBTP, clip spread ≤ 3 LU [14 of the audio audit].
- Proof: the §4 re-render measures −14 ±0.5 LUFS, TP ≤ −1.5, and the per-clip spread before/after.

## §6 Background band and speed [5]
For opaque-page types (how_do_you_say and the level modes) set the contrast band to 0 and skip `clip_contrast` sampling; instead soften the footage once per clip: 1/4-res Gaussian blur, slight warm grade toward the sand palette, gentle vignette. Fix the old `HEADLINE_COLOR` reference. Proof: render time before/after (expect −25 s) and 3 stills.

## §7 Lessons: final encode and loudness [4, lessons 4]
After Manim writes the lesson, one ffmpeg pass: `-c:v libx264 -crf 14 -preset slow -tune animation`, BT.709 tags, `+faststart`, audio two-pass loudnorm to −14 LUFS / −1.5 dBTP (AAC 48 kHz 192k). Keep the original until the pass succeeds. Proof: re-encode the latest make-vs-do render (no re-render): bitrate, tags, LUFS before/after, and one still crop of a vignette edge (banding).

## Report
Per section: commit, tests, proof tables. End with `git log --oneline -10` and `git status --short`. Then stop: Garcia listens to one Short and one lesson before STEP 76.

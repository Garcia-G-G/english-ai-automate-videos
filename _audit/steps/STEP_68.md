# STEP 68 — Close the open work: commit or drop everything uncommitted, push, clean tree

Run first, before any other STEP. $0. No renders, no API calls. One commit per section,
pushed. Stop and report if a section fails.

The audit of 2026-10-19 (`_audit/STATUS_2026-10-19.md`) found the branch 2 commits ahead
of origin and 126 changed paths in the working tree, some of them uncommitted since
2026-09-10.

## §1 STEP 67 is written but not committed

`src/upload_limits.py` and `tests/test_upload_limits.py` are untracked. The STEP 67
hunks are uncommitted, all saved 2026-10-16 22:40:
- `src/uploader.py`: Google's error reason kept;
- `src/admin.py`: the 24 h counter, the slot message and `claim`/`release`;
- `src/manim_studio.py`.

1. Read them against `STEP_67.md`. One thing to check in particular: in `admin.py`, the bulk
   upload path uses `nonlocal_state`. Confirm it is defined.
2. Run `tests/test_upload_limits.py` and `tests/test_dashboard_doors.py`.
3. Commit as STEP 67 and report what is done and what is still missing against the STEP.

## §2 Edits that were never committed

These hunks predate STEP 67. Some are from 2026-09-10/11:

| file | what the hunk does |
|---|---|
| `main.py` | re-indents `upload=args.upload` in the batch path |
| `src/clip_contrast.py` | a pinned band survives an empty measurement |
| `src/length_spec.py` | `FIELDS` served lazily through a module `__getattr__` |
| `src/video/utils.py` | `draw_pill_badge` returns `(0, 0)` for blank text |
| `src/video/fill_blank.py` | an option card with blank text draws no text instead of raising `IndexError` |
| `src/video/vocabulary.py` | a blank cell draws nothing instead of raising |
| `tests/conftest.py`, `tests/output_guard.py`, `tests/test_output_isolation.py`, `tests/test_dashboard_doors.py` | test isolation changes |

For each one:
1. Decide **keep** (it is right, and a test covers it, or you add one) or **drop**
   (`git checkout -- <file>`, or the hunk alone).
2. Commit the kept ones in one commit, with one line per hunk in the message.
3. Report the list with the decision for each.

## §3 The queue moves

Scripts that were produced moved to `content/queue/_done/`. Git sees:
- 58 untracked files under `_done/`;
- 63 deletions under `content/queue/<type>/`.

Commit both sides together, so git matches what has been used. Do not change the
mechanism.

## §4 Loose files

These are untracked:
- `_audit/ESTANDAR_FONDOS.md` (2026-09-04): commit it as history;
- `_audit/INVENTARIO_VERIFICADO.md` (2026-09-04): commit it as history;
- `experiments/manim_voiceover_poc/renders/reviews.jsonl`: this is runtime data from
  «Revisar y subir». Add it to `.gitignore`, the same way the Shorts review data is
  handled.

## §5 Push and prove

1. Push. My two commits `1ecdfd5` and `496e786` go too.
2. Run the full test suite on the Mac.
3. Paste:
   - `git status -sb`, which must show nothing to commit and "up to date with origin";
   - the test totals;
   - the `git log --oneline` of this step.

Note: in the Linux VM, 8 tests fail and 3 time out for environment reasons only
(ffmpeg MP3 padding, 1 px of font rendering, slow corpus tests). On the Mac they should
pass, as they did in STEP 62. If any fail on the Mac, report them and do not "fix" the
tolerance.

## Do not

- Do not start STEP 63, 66 or anything else in this step.
- Do not commit keys, `.env`, tokens, voice IDs or home paths.
- Do not add attribution lines.

# english-ai-videos — handoff briefing

Paste this into a fresh session. It assumes no repo access.
State as of **2026-09-02**, branch `6a-layout`, HEAD `a5ccfa0`.

---

## 1. What the product is

A pipeline that generates short vertical (1080×1920) videos teaching **English to
Spanish speakers**, and publishes them to YouTube Shorts. Narration is Spanish,
the taught phrases are English.

Six video types: `educational`, `quiz`, `true_false`, `fill_blank`,
`pronunciation`, `vocabulary`.

Declared goal in the roadmap: **2 videos/day, unattended**.

Two entry points:
- CLI — `python3 main.py --random --type quiz`
- Dashboard — `bash run_admin.sh` → Streamlit on `localhost:8501`

Stack: Python 3.9.6, Streamlit 1.50, PIL for frame drawing, ffmpeg, ElevenLabs
TTS (primary), OpenAI GPT for scripts + Whisper for word timestamps, gpt-image-2
for backgrounds.

---

## 2. Current state

| | |
|---|---|
| Branch | `6a-layout`, **54 commits ahead of `origin/main`**, not yet pushed |
| Tests | **1130 passing**, one known LibreSSL warning |
| Queue | 11 in `output/video/`, 0 pending, 3 approved, 17 uploaded, 109 rejected |
| Ledger | 21 published rows (`output/published/ledger.jsonl`) |
| Spend | August 2026 was $3.33 across 6 render days. Display ceiling $25/mo in `config.yaml` |

**There is uncommitted work in the tree.** See §6.

---

## 3. Architecture — there are now TWO layers, and this is the main thing to understand

### The legacy pipeline (everything that has ever actually shipped)
`main.py` → `src/pipeline.py` → `src/tts_*.py` → `src/video/<type>.py`

Artifacts move through directories, and the directory **is** the state:

```
output/video/<type>/       rendered by --batch, not yet promoted
output/pending/<type>/     awaiting human review
output/approved/<type>/    reviewed, not yet uploaded
output/uploaded/<type>/    published
output/rejected/<type>/
output/published/ledger.jsonl    append-only record of what is live
```

Each `.mp4` has a sibling `.json` sidecar carrying the script, the topic, and
the QA gate verdict.

### The Studio layer (added by Codex, 25 commits, ~2,300 lines + 5,100 lines of tests)
`src/studio/` — typed pydantic contracts, an artifact repository, a lifecycle
state machine, and a "workspace" concept for multiple markets.

It **is** wired in: `main.py` routes all creation through
`CreationService`, `src/profiles.py` resolves audiences through it, and all five
renderers call `studio.renderer_presentation.resolve_presentation()` for their
on-screen copy.

It writes to a **different tree**: `output/artifacts/<artifact_id>/`.

> ### ⚠️ The single biggest open issue
> The Studio writes `output/artifacts/`. The dashboard reads
> `output/{video,pending,approved,uploaded}`. **Anything the CLI produces is
> invisible to Review/Upload/Inicio.** `output/artifacts/` does not exist yet —
> the new path has never been run end to end. This matters more than it sounds,
> because publication is now owner-approved (§5) and the dashboard is the
> approval surface. Reconnecting them is "Task 8".

---

## 4. Two markets: YouTube (works) and Bilibili (does not)

A second workspace was added for **Bilibili**, Simplified Chinese narration
teaching English. The owner confirms this was requested — it stays.

It cannot currently produce a video. Three independent layers assume Latin:

| Layer | Status |
|---|---|
| **Font** | FIXED. `assets/fonts/Inter-Bold.ttf` has no Han glyphs — every Chinese character rendered to a byte-identical blank box (tofu). `src/video/utils.py` now resolves a CJK face (`VIDEO_FONT_PATH_CJK` → bundled Noto → system fonts) and raises `MissingCJKFont` rather than falling back. |
| **Line breaking** | FIXED. `line_break()` packed by `text.split()`; Chinese has no spaces. A 28-character sentence returned as **one line 1680px wide against an 800px box**. Now breaks per-character with basic kinsoku rules, keeping English runs whole. |
| **Word timing** | **NOT FIXED.** `src/animations/subtitle_processor.py` and `src/tts_openai.py` also `.split()` on whitespace, so Chinese narration yields one "word" per line. Educational karaoke is Spanish-only. |

Also still open, all configuration rather than code:
- `BILIBILI_ADULTS_ELEVENLABS_VOICE_ID` / `BILIBILI_CHILDREN_ELEVENLABS_VOICE_ID`
  are unset, so voice resolution **fails closed** with `InvalidVoiceProfile`.
  This is correct behaviour — the legacy voice fallback is deliberately scoped
  to `youtube_es_en` so Chinese can never be narrated in the Spanish voice.
- There is **no Bilibili upload route**: no uploader, not in
  `config.yaml upload.platforms`, not a ledger platform.

---

## 5. Decisions already made — do not re-litigate these

**Unattended publication is refused, on purpose.** `main.py --upload` renders and
then refuses, via `refuse_unattended_upload()`. The reason is on the record: a
video (`hPdSoqjvu3E`) was published to the channel twice, from a hand upload
against a queue that did not know it was already live. An unattended
`--batch N --upload` loop is that same mistake automated. `upload_video()` still
exists and still holds the idempotency guard, the ledger write and the metadata
resolution — it is kept for the approved path, not dead. Tests in
`tests/test_upload_policy.py` pin this so it cannot be removed by accident.

**Absence of a QA gate verdict is not a pass.** The gate verdict is written into
the artifact's own `.json` sidecar so the two live or die together. Artifacts
rendered before that change carry no verdict. Anywhere this is displayed it must
read "sin registro" — never a green tick, never a blank. A REJECT once reached
`output/pending/` with a green tick beside videos that passed; that is the defect
this rule exists to prevent.

**A gate REJECT is not a failed job.** "failed" means the pipeline raised. A
refused video is a *successful render of a bad artifact* and carries its verdict
as a field, not a status. Merging them corrupts both counts.

**The Spanish layout is measured, not guessed** (roadmap step 6a). Font metrics,
text-box budgets and line breaking were all calibrated against real output. Do
not change the Latin path of `line_break()`, or the base font — 76 regression
cases in `tests/test_cjk_text.py` run the original algorithm as an oracle and
will fail if it drifts.

---

## 6. Uncommitted work in the tree

Nothing below is committed. It all passes tests.

| File | Change | Owner |
|---|---|---|
| `src/admin.py` | +682/−104 — the "Inicio" dashboard rewrite | Claude |
| `src/thumbnails.py` | new, 111 lines — ffmpeg still extraction, cached | Claude |
| `tests/test_inicio_worklist.py` | new, 25 tests | Claude |
| `config.yaml` | +13 — `costs.monthly_ceiling_usd` | Claude |
| `src/video/utils.py` | +197 — CJK font + line breaking | Claude |
| `main.py` | +36/−2 — the upload policy | Claude |
| `tests/test_cjk_text.py` | new, 99 tests | Claude |
| `tests/test_upload_policy.py` | new, 6 tests | Claude |

**The Inicio rewrite** replaced a dashboard home page that opened with Total
Videos / Storage MB / "By Type 40%" — all aggregates nobody can act on. The rule
now: every block names specific artifacts and the one button that moves each
forward. Four queues (promote / review / upload / published), each count computed
twice by independent code paths and both shown, gate badges that make absence
visible, one line of cost, cached ffmpeg thumbnails.

> ⚠️ **Task 8 rewrites `src/admin.py`.** If it starts from a merged `main` while
> that 682-line change is unstaged, it becomes a hand-merge against a rewritten
> file. Commit it first.

---

## 7. Gotchas that will waste your time

- **`finalize_video()` is NOT idempotent.** It appends the outro and
  `os.replace()`s the file under the same name, with no marker recording that an
  outro is present. `src/admin.py:367` calls it, and
  `src/studio/legacy_pipeline.py:222` now calls it too. Routing the dashboard
  through `CreationService` without removing the `admin.py` call gives **two
  outros on every video and a double gate pass**.
- **Streamlit runs with `--server.fileWatcherType none`.** It will not pick up
  your edits. Restart it, or you are debugging a process older than your change.
- **Never edit the tree during a render.** It invalidates Streamlit caches and
  records healthy jobs as failed.
- **The ledger is append-only** and records irreversible events. A poisoned row
  cannot be rewritten, only appended around. Tests are blocked from writing to
  the real one by `tests/conftest.py`.
- **`clean_for_tts()` must be called before any TTS call.** It was defined and
  never used for a long time.
- Countdown is **silent** for all of quiz / fill_blank / true_false:
  1.5s per number + 1.0s pause = 7.0s think→answer.

---

## 8. Roadmap position

Done: pipeline unification, pydantic contracts, QA gate, YouTube auth,
watermark + outro, measured layout (6a), text grouping (6b), per-video generated
backgrounds (F, F2).

Current: **D — dashboard shows what the pipeline computes.** The Inicio page
above is part of this.

Next per the roadmap: **T** (vocabulary + pronunciation text), then **C** (more
categories/topics). Blocked/parked: 6c layout engine, mascot (drawn, switched
off until 6c gives it space), TikTok (needs external audit to publish publicly).

Not in the roadmap at all: the Studio layer, workspaces, and Bilibili. They were
requested directly.

---

## 9. Immediate next actions

1. Commit the uncommitted work above onto `6a-layout` (before anything rewrites
   `src/admin.py`).
2. Push `6a-layout`, open a PR against `main`, review the diff, merge through
   GitHub without force-pushing. Do not do a local checkout/merge — the working
   tree holds unrelated owner changes in `_audit/**`.
3. Task 8, from updated `main`: route the dashboard through `CreationService`,
   and **remove the direct `finalize_video()` call in `src/admin.py`** to prevent
   double finalization.
4. Decide whether Studio adopts the stage-directory tree or the dashboard learns
   to read `output/artifacts/` — that is the fork in §3.

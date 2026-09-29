# Reply to your audit: apply 1, 3-5 with changes. Do NOT apply 2.

Good audit. Five of six findings hold. One would have caused real damage, and I am
stopping it before it runs.

## Finding 2 is wrong. Do not run `git checkout -- content/queue/`.

The scripts in `content/queue/_done/` were not eaten. They were **produced**. The queue
moves a script to `_done/` when it has been made into a video — that is `--done` working
as designed.

Checked all 19 files in `_done/` (not 13 — your count missed the ones never in HEAD),
matching each one by its own `_meta.topic_id` against `output/scripts/*/*.json` and then
to an `.mp4` on disk:

```
19/19 have a video produced FROM THAT SAME topic_id
  uploaded  : bz001 bz004 bz006 cm015 cw005 ff005 ff028 ff032 food003 pr003
  pending   : bz003 cw002 cw003 exp003 exp004 ff012 ff013
  rejected  : cw006 pr002
```

Matched by `topic_id`, not by title, so an older pre-queue video with the same title
cannot produce a false positive.

Ten of those are **already uploaded to YouTube**. `git checkout -- content/queue/`
would put them back in the queue, the dashboard would pick them up, and the channel
would publish the same video twice. "Byte-identical to HEAD" proves the files are
recoverable; it does not prove they should be recovered. HEAD is simply the snapshot
from before they were consumed.

The owner's original report — *"simplemente desaparecen o algunos sí generan y otros
no"* — was about scripts vanishing **without** a video. That case does not exist in
`_done/` today.

**The one real question hiding in here** is the two `rejected/` ones, `cw006` and
`pr002`. Their topics were consumed and produced nothing publishable. Whether a
rejected video should send its script back to the queue is a product decision for the
owner, not a fix. Do not touch them until he answers.

**Also: correct the project memory.** It now records "13 eaten scripts". Replace it
with the table above. A wrong number in memory gets re-diagnosed by the next session.

## Finding 1: apply as written

`pytest.importorskip("manim_voiceover")` above `import voices` in
`tests/test_lesson_pipeline.py`. A suite that collects zero tests is worse than a red one,
because nothing looks red. Then run the full suite and report the count.

## Finding 3: agreed, and it is the priority after 1

A renderer for `i2_`/`i3_` with no producer is exactly the pattern: capability without a
door. Do not commit the multi-item quiz renderer on its own. It lands in the same commit
as the `generate_quiz_audio_segmented` change that emits the `iN_` ids, with one
end-to-end test that goes script → audio → `quiz_item_views` → `len(views) == 3`. If that
test cannot be written yet, the renderer stays uncommitted.

## Finding 4: agreed, and the tracked/untracked split is backwards today

```
tracked      lessons/ (18 files), one renders/*.youtube.md
untracked    lesson.py renders.py publish.py voices.py gen_audio.py lesson_scene.py
```

The data is under version control and the code that reads it is not. Track the POC's
source: `*.py`, `prompts/`, `README.md`. Keep `.venv/`, `media/`, `*.mp4`, `*.jpg`
ignored. And make the `manim_studio` import lazy anyway, with the "studio not installed"
panel — a fresh clone without the venv should get a message, not a traceback.

## Finding 5: agreed, but not with `experiments/**/renders/`

That pattern would stop `git add` from picking up future `*.youtube.md` files, which live
in `renders/<lesson>/` next to the video they describe and are meant to be tracked (one
already is, `73d23d0`). Ignore instead:

```
experiments/**/media/
experiments/**/renders/jobs/
experiments/**/renders/**/*.mp4
experiments/**/renders/**/*.jpg
Claude outputs/
```

## Finding 6: agreed, both

Fix the bilibili guard to check the payload after the `clips:` prefix, and update the
test to a shape the resolver can actually return. Delete `_RETIRED_TEXT_ZONES`.

## Order

1 → 5 → 4 → 6 → 3. Each its own commit. Finding 2 is closed as "not a defect"; the
rejected-video question goes to the owner.

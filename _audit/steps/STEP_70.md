# STEP 70 — Close out the Meta publisher before the first real Reel

Context: b9593b7 (Instagram + Facebook Reels publisher) is local and not pushed. The audit found five things to close before anything goes public. Work section by section: tests and one pushed commit per section; stop at the first failure and report. Do not publish any real Reel in this step.

## §0 Snapshot first
Before any code change: `cp -Rp .tokens ".tokens.bak-$(date +%Y%m%d-%H%M)"`. The dry run in STEP 66 already rewrote `.tokens/instagram_token.json`; from now on every change that can write tokens starts with a snapshot. Report the snapshot name only, never its contents.

## §1 No home paths in the repo
README.md line ~116 has the cron line with `/Users/...`. Replace it with a placeholder (`cd /path/to/english-ai-videos && ...`) and say in one sentence to replace it with the real folder. Then add a test that fails if any tracked text file contains `/Users/` or `/home/<name>/` (allow-list only test fixtures that need it, if any). Proof: `git grep -n "/Users/"` prints nothing.

## §2 `--dry-run` writes nothing
`dry_run()` currently calls `publisher.check()`, which calls `current_token()`, which can refresh and save the Instagram token. A dry run must have no side effects:
- In dry mode, `check()` uses the stored/env token as is and never calls the refresh endpoint or `_save_token`. If the token is close to expiry, report `"token: expires in N days (refresh with refresh-token)"` instead.
- Refreshing happens only in `refresh-token` and in a real publish.
- Test: dry run with a token 5 days from expiry → no HTTP call to `refresh_access_token`, `.tokens` file bytes and mtime unchanged.
- Update the docstring (remove "except that Instagram's token may be refreshed").

## §3 One lock for every Meta publish
The panel's Upload button does not take the queue lock, so a click at 10:00/19:00 can race the tick and post twice. Route every Meta publish (panel button, `now`, `tick`, `loop`) through the same lock and the same guard/attempt log. If the lock is held, the button shows "publicando en la franja, espera" and does nothing.
- Test: two concurrent publishes of the same artifact (thread + tick) → exactly one call to the publish endpoint, the other returns "locked" or "already published".

## §4 Suite green again
`tests/test_cut_renders.py` has 3 failures since STEP 63: its fake pipeline lacks `render_timeout`. Add it to the fake (return the real default), do not change `src/pipeline.py`. Proof: full suite count, 0 failures.

## §5 Small cleanups, then push
- `.gitignore`: the working tree has two extra `.env` lines at the end (duplicates of line 2). Drop them; leave the file otherwise as it is.
- Push b9593b7 and the §1–§5 commits to `origin/6a-layout`.

## Report
For each section: commit hash, tests run and their result, and the proof asked for. End with `git log --oneline -8` and `git status --short`. Then stop: Garcia decides when the first real Reel goes out.

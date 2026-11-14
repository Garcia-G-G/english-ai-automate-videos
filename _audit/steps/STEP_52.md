# STEP 52 — Clean the public history: no tool attribution, steps instead of prompts

## What the owner asked
Nothing in the repository or on GitHub should say which tools wrote it, and briefs are
"steps", not "prompts". The working tree is already clean (commit e05572f: briefs moved to
`_audit/steps/STEP_NN.md`, `_meta.model` is `"manual"`, tool folders excluded locally).
This step does the same for the **history** — every commit already pushed.

Measured on 2026-10-14: 275 commits on 6a-layout; ~305 attribution trailer lines
(`Co-Authored-By: …`, `Session: …`) and 66 "Generated with …" lines across all
commit messages; `.tool/settings.local.json` tracked in old commits; `manual` in
old script files. Also **238 commits carry the author `Gilber <gilbergarciata@gmail.com>`**
— a personal email in public history (the repo identity has been the GitHub no-reply
address since). The rewrite fixes that too, unless the owner says otherwise.

## This rewrites every commit hash and needs a force-push
Consequences, all accepted by the owner before running:
- `main` and `6a-layout` on GitHub get new hashes. Any other clone must be re-cloned
  (or `git fetch && git reset --hard origin/<branch>`). Hashes quoted in `_audit/` docs
  and in old step files will no longer resolve.
- `stash@{0}` and the reflogs do not survive. Look at the stash first; if it matters,
  turn it into a branch before starting.
- GitHub may keep showing old commits for a while through caches or PR refs.

## Procedure (on the Mac, from the repo root, with nothing uncommitted you care about)
1. Backup, untouched: `git clone --mirror . ../english-ai-videos-backup.git` and
   `git bundle create ../english-ai-videos-backup.bundle --all`. Do not continue until
   both exist.
2. Commit or set aside the in-progress work (main.py, src/clip_contrast.py,
   src/length_spec.py, src/video/{fill_blank,utils,vocabulary}.py, tests/conftest.py,
   tests/output_guard.py, tests/test_dashboard_doors.py, tests/test_output_isolation.py).
3. Install `git-filter-repo` (pip, free). Write three files outside the repo:
   - `mailmap`: `Garcia-G-G <62484989+Garcia-G-G@users.noreply.github.com> Gilber <gilbergarciata@gmail.com>`
   - `replace.txt` (file contents, every commit): `manual==>manual`,
     `Code==>Code`, and the old brief file names ==> their STEP names (the
     mapping is in `_audit/steps/README.md`).
   - a `--message-callback` that drops lines starting with `Co-Authored-By:`,
     `Session:`, `🤖 Generated with` and lines that are only a vendor
     link; replaces `Code` with `Code` and old brief names with STEP names; leaves
     every other word alone (do NOT replace the word "prompt" blindly — "GPT prompt" is
     about the script generator and must stay).
4. `git filter-repo --mailmap ../mailmap --replace-text ../replace.txt --message-callback "…" --invert-paths --path .tool/ --force`
5. Verify before pushing, and paste the output:
   - `git log --all --format=%B | grep -ic "co-authored-by\|session\|generated with"` → 0
   - `git log --all --format='%an <%ae>' | sort | uniq -c` → only the no-reply identity
   - `git grep -i <tool> $(git rev-list --all) | wc -l` → 0 except the Piper voice id
     `vits-piper-es_MX-claude-high` (a third-party model name; leave it)
   - the test suite gives the same result as before the rewrite.
6. `git remote add origin https://github.com/Garcia-G-G/english-ai-automate-videos.git`
   (filter-repo removes it), then `git push --force-with-lease origin main 6a-layout`.
7. Keep the backup for at least a month.

## From now on
- `.tool/settings.local.json` (local, not tracked) sets `"attribution": {"commit": "", "pr": ""}`
  and `"includeCoAuthoredBy": false`: no trailers on new commits or PRs. Check the first
  commit after this step.
- Briefs are `_audit/steps/STEP_NN.md`, next is STEP_53. No tool names in commit messages,
  docs or file contents.

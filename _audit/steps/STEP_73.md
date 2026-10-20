# STEP 73 — TikTok: drafts to the inbox from a sandbox, and a manual fallback

Context (audited 2026-10-20 in the TikTok developer portal and the repo):
- App "English_Unlimited" (individual): Production **Not approved** (rejected 2026-03-17 and 03-20). Its only scopes are `user.info.profile`, `user.info.stats`, `video.list` — read-only: no Login Kit for posting, no Content Posting API, no `video.upload`/`video.publish`. No sandbox exists yet.
- Repo: no TikTok token has ever existed. `TikTokUploader` cannot authenticate (token exchange sends JSON; TikTok needs form encoding — docs/recorded-debt.md item 9; redirect `https://localhost/callback` is not a desktop loopback URI) and its upload mixes two flows (inbox init, then a second direct-post init with no file). TikTok has 0 attempts in attempts.jsonl.
- TikTok policy: unaudited Direct Post is private-only (SELF_ONLY); its guidelines list "a utility tool to help upload contents to the account(s) you or your team manages" as not acceptable for audit. So public auto-posting is not a realistic goal. Target instead: **upload to the TikTok inbox as a draft** (`video.upload`), Garcia taps Post in the app. Test it in a **sandbox** (no review). If the sandbox refuses uploads, the manual fallback (§4) is the answer.

Garcia does the portal part first (sandbox, products, scopes, target user, sandbox keys in `.env`). Section by section, tests and one pushed commit per section, stop at the first failure. $0. Never print client_secret or tokens.

## §0 Code's review findings from the STEP 71 pass
- 1: anchor `src/generate_app_icon.py`'s guard path to the repo root (test: run it from another cwd, the guard still finds `assets/branding/app_icon.png` and refuses).
- 2: compute `note_setup_failure(...)` once in the single-upload path of `src/admin.py`.
- 3: document in `src/video/outro.py` and the README how to regenerate an outro's voice after changing `spoken` (delete that one clip; costs one TTS call).
- 4: render outros to a temp file and `os.replace` it into `assets/outro/` only when complete, so a cut render never becomes a cached clip (test with a render that raises halfway).

## §1 TikTok desktop OAuth that works
- `make auth-tiktok`: Login Kit for Desktop with PKCE (`code_challenge_method=S256`; TikTok's desktop doc says the challenge is the **hex** SHA-256 of the verifier — implement as documented and, if the server rejects it, try base64url and record which one worked), loopback redirect `http://127.0.0.1:<port>/callback/` (reuse the existing loopback helper; the exact URI must be registered in the sandbox's Login Kit), scopes `user.info.basic,video.upload`.
- Token exchange and refresh: `POST https://open.tiktokapis.com/v2/oauth/token/` as `application/x-www-form-urlencoded`, with `code_verifier`; treat any body with `error` as a failure even on HTTP 200 and never persist it (closes recorded-debt item 9). Access token 24 h, refresh token 365 days; always store the refresh token the answer returns. Token file `.tokens/tiktok_token.json` (0600).
- Tests with mocked endpoints: form encoding, PKCE params, error-on-200 not persisted, refresh rotation.

## §2 Upload as a draft (inbox), nothing else
- Replace the mixed flow with the inbox flow only: `POST /v2/post/publish/inbox/video/init/` (`source_info`: `FILE_UPLOAD`, size, one chunk if ≤ 64 MB, else TikTok's chunk rules) → `PUT upload_url` with `Content-Range` → poll `POST /v2/post/publish/status/fetch/` until the draft is delivered (`SEND_TO_USER_INBOX` or the documented final state) or fails.
- Result in attempts.jsonl as for the other platforms (same guard, same lock); the panel calls it «Enviado a borradores de TikTok — publícalo desde la app».
- No Direct Post code path. Title/caption: TikTok inbox drafts take no caption; put the caption in the attempt record and show it in the panel with a «Copiar texto» button so Garcia pastes it in the app.
- Tests with mocked API (init, PUT headers, status polling, failure states).

## §3 `tiktok setup-check`
`python3 -m uploader tiktok-check` (and a «Comprobar TikTok» button next to Meta's): keys present (no values), token present/expiry, granted scopes vs `user.info.basic`, `video.upload`, and `GET /v2/user/info/?fields=display_name` answering. One Spanish line per problem with the fix. Exit 0 only if all is present.

## §4 Manual fallback, always available
In Subir, per approved Short: «Preparar para TikTok» = a button that reveals the MP4 in Finder (`open -R`) and copies the TikTok caption (title + hashtags, ≤ 2200 chars) to the clipboard (`pbcopy`), and a «Marcar como subido a mano» button that records a manual TikTok attempt (status `manual`) so the queue and stats know. Tests for the record.

## §5 Live proof, then stop
- After Garcia's portal setup: `make auth-tiktok` (Garcia does the browser consent), then `tiktok-check` must exit 0. Report its output (no secrets).
- With Garcia's OK in chat: send ONE approved Short to his TikTok inbox as a draft. Report the final status. If the sandbox refuses the upload, report TikTok's exact error, keep §4 as the TikTok path, and stop.
- Push. Report per section: commit, tests, proof. End with `git log --oneline -8` and `git status --short`.

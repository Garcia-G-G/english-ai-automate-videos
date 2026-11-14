# STEP 72 — Make Instagram and Facebook actually publish

Context. On 2026-10-19 16:35 Garcia pressed Upload for 4 how_do_you_say Shorts (desayuno, postres, baño, dormitorio). Every call failed, nothing was published, no container was created (attempts.jsonl: 16 `failed`, no session):
- Instagram: `HTTP 400 code=100: The parameter video_url is required`. Cause: we use the Instagram Login API (graph.instagram.com + IG_ACCESS_TOKEN). Meta documents `upload_type=resumable` + rupload.facebook.com ONLY for the Instagram API with Facebook Login (graph.facebook.com); on graph.instagram.com the container needs a public `video_url`, which we do not have and will not pay to host. The STEP 66 dry run never created a container, so this was never exercised.
- Facebook: `HTTP 403 code=200: lack of pages_manage_posts permission`. The Page token was generated without that permission.

Fix: publish Instagram through the Facebook Login path with the same Page token Facebook uses. One token, one setup, no hosting, $0. Do this right after STEP 70 (before STEP 71). Section by section, tests and one pushed commit per section, stop at the first failure. Commit this STEP file with §0.

## §0 Snapshot
`cp -Rp .tokens ".tokens.bak-$(date +%Y%m%d-%H%M)"` and `cp -p .env ".env.bak-$(date +%Y%m%d-%H%M)"` (both stay untracked; check `git status` shows neither). Report the names only.
Also commit, in its own commit, the panel's queue moves now in the tree: `bv023_desayuno`, `bv024_postres`, `bv025_bano`, `bv026_dormitorio` from `content/queue/how_do_you_say/` to `content/queue/_done/` (all four were produced on 2026-10-19: the cómo_se_dice_20261019_16xxxx artifacts). STEP 71 §4 is then done.

## §1 Instagram over graph.facebook.com
- Host `https://graph.facebook.com/{GRAPH_VERSION}`; token = `FB_PAGE_TOKEN`; the Instagram id is the Page's `instagram_business_account.id` (GET `/{FB_PAGE_ID}?fields=instagram_business_account{id,username}`), looked up once and cached in `.tokens/meta_ids.json` (0600). The `IG_USER_ID` in `.env` today is the Instagram-Login id, not this one: never let it override. If it is set and differs from the Page's `instagram_business_account.id`, `setup-check` says so and the publisher uses the Page's id.
- Container: `POST /{ig_id}/media` with `media_type=REELS`, `upload_type=resumable`, `caption`, (`share_to_feed=true`). Read `uri` from the answer when present; else build `https://rupload.facebook.com/ig-api-upload/{GRAPH_VERSION}/{container}`.
- Upload: `POST` that uri with headers `Authorization: OAuth <token>`, `offset: 0`, `file_size: <bytes>`, body = raw file bytes. Then poll `status_code`, then `media_publish`, then permalink — the existing logic.
- Remove the Instagram-Login pieces that no longer apply (graph.instagram.com host, `IG_ACCESS_TOKEN`, the 60-day refresh). `refresh-token` becomes: report the Page token's expiry via `/debug_token` (a Page token from a long-lived user token never expires). Keep every redaction guarantee: no token in logs, errors, URLs or tests' output.
- Tests: mocked API for the new host and headers; the container call carries `upload_type=resumable` and never `video_url`; the rupload call has the three headers and the raw body.

## §2 `setup-check`: tell Garcia exactly what is missing
`python3 tools/meta_publish.py setup-check` (and `make meta-check` calls it) prints, without any token:
- Page name and id; linked Instagram username and id (or "Instagram no está vinculado a la Página").
- Token type and expiry.
- Permissions granted vs needed, from `/me/permissions` or `/debug_token` scopes. Needed: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`, `instagram_content_publish` (add `business_management` only if a call proves it necessary).
- One line per problem, in Spanish, with the fix. Exit code 0 only if everything is present.
The panel's Meta card shows the same result.

## §3 The panel stops on a setup error
On 16:35 and 16:36 the button tried 4 videos × 2 platforms twice: 16 calls that could only fail. When a platform fails with a setup error (codes 100 with `video_url`, 190, 200, 10, or any permission message), mark that platform "configuración pendiente" for the rest of the batch, skip its remaining videos with one Spanish message pointing at `setup-check`, and keep going with the other platforms. Test it with the mocked API.

## §4 Docs and a small cleanup
- README, Meta section, in Spanish: replace the Instagram Login instructions with the Facebook Login steps (link Instagram to the Page; Graph API Explorer → app → user token with the 5 permissions → extend it → `/me/accounts` → the Page's token into `FB_PAGE_TOKEN`; run `setup-check`). `.env.example`: drop `IG_ACCESS_TOKEN`, keep `IG_USER_ID` as optional.
- Streamlit warns `use_container_width` is deprecated (37 uses in src/admin.py): replace with `width="stretch"` / `width="content"` as the warning says. Proof: the warning no longer appears when the panel starts.

## §5 Live proof, then stop
- Garcia already put a new Page token in `.env` (the Page answers), but Meta blocked him for ~24 h from linking Instagram to the Page. So today `setup-check` is expected to report exactly one problem, «Instagram no está vinculado a la Página», and everything else green (Page, token type Page, expiry Never, the 5 permissions). Report its output (no tokens). If anything else is missing, report it and stop.
- In the panel, Instagram must show «configuración pendiente» and be skipped while Facebook proceeds (§3).
- `python3 tools/meta_publish.py now <artifact> --dry-run --platform facebook` (add the flag if it does not exist) for one of the four Shorts: the dry run must stay read-only (STEP 70 §2).
- Do NOT publish a real Reel. Garcia publishes the first one himself from the panel when `setup-check` is green.
- Push. Report per section: commit, tests, proof. End with `git log --oneline -8` and `git status --short`.

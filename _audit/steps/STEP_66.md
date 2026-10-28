# STEP 66 — The same Short also goes to Instagram Reels and the Facebook Page

Run after STEP 62 is closed. Work section by section: each section has its own tests
and its own pushed commit. Stop and report if a section fails.

Cost: the Meta Graph API is free. No new paid service. No hosting either: the file goes
up straight from the Mac (resumable upload), so nothing needs a public URL.

## What is there today

- `src/uploader.py` has `InstagramUploader` (around line 1084). It uses Graph **v19.0**
  and needs a public `video_url`, which we don't have. Nothing calls it.
- `.env.example` has `INSTAGRAM_ACCESS_TOKEN` and `INSTAGRAM_BUSINESS_ACCOUNT_ID`.
- There is no Facebook Page uploader.

## What the owner does by hand first (not you)

He links the Instagram professional account to a Facebook Page, creates a Meta app
(type Business, Facebook Login for Business), and puts `META_APP_ID` and
`META_APP_SECRET` in `.env`. He will log in himself in §1. Never print the app secret or
any token.

## §1 One login, one token file

- `tools/meta_auth.py`:
  1. Opens the Facebook Login for Business dialog on the loopback handler we already use
     for YouTube. Scopes: `pages_show_list`, `pages_read_engagement`,
     `pages_manage_posts`, `instagram_basic`, `instagram_content_publish`,
     `business_management`.
  2. Exchanges the short-lived user token for a long-lived one.
  3. Reads `/me/accounts` and lets him pick the Page. Then reads that Page's
     `instagram_business_account`.
  4. Saves `.tokens/meta_token.json`: `page_id`, `ig_user_id`, page token, user token,
     and the expiry dates. It goes through the same `_persist_token` choke point and file
     permissions as YouTube. Snapshot `.tokens` first.
- `tools/meta_auth.py --check` prints the Page name, the IG username, the scopes and the
  days left. No token text.
- Pin the Graph version in one constant, `META_GRAPH_VERSION = "v25.0"`.
- Tests: mocked HTTP, the token file shape, and that nothing secret reaches the logs.

## §2 Instagram Reels from the local file

Rewrite `InstagramUploader` to use the resumable flow (Facebook Login path):

1. `POST graph.facebook.com/{v}/{ig_user_id}/media` with `media_type=REELS`,
   `upload_type=resumable`, `caption`, and `share_to_feed=true`. This returns `id` and `uri`.
2. `POST` the bytes to that `uri` (`rupload.facebook.com/ig-api-upload/...`) with these
   headers: `Authorization: OAuth <token>`, `offset: 0`, `file_size: <bytes>`.
3. Poll `GET /{container}?fields=status_code,video_status` once every 20 s, for 5 minutes
   at most, until `FINISHED`. If the upload breaks, resume from `bytes_transferred`.
4. `POST /{ig_user_id}/media_publish?creation_id=...`. Store the media id and the
   permalink.
5. Before publishing, read `GET /{ig_user_id}/content_publishing_limit` and refuse
   cleanly when the quota is used up.

Remove the `video_url` requirement. Tests with mocked HTTP for these cases: happy path,
`ERROR` status, timeout, resume after a cut, and quota reached.

## §3 Facebook Page Reels

Add a new `FacebookPageUploader`:

1. `POST /{page_id}/video_reels` with `upload_phase=start` and the Page token. This
   returns `video_id` and `upload_url`.
2. `POST` the bytes to the `upload_url` with the same three headers, plus
   `Content-Type: application/octet-stream`.
3. Poll `GET /{video_id}?fields=status` until uploading and processing are complete.
4. `POST /{page_id}/video_reels` with `upload_phase=finish`, `video_state=PUBLISHED`,
   `video_id` and `description`.

The docs show both `finish` and `complete`. Use `finish`. If the API refuses it, try
`complete` once and say in the report which one worked.

**Facebook Reels must be 3 to 90 s.** Many level Shorts run 90–95 s. If a video is over
90 s, skip Facebook for that video and log `FB SKIP >90s`. Do not cut the video. Tests
cover that.

## §4 One button, three platforms

- On «Revisar y subir» (Shorts), next to «📤 Upload», add three checkboxes: YouTube,
  Instagram, Facebook.
  - Each one is ticked by default only when that platform is configured.
  - Facebook is greyed out with «>90 s» when the video is over 90 s.
- `upload_guard.decide` runs **once**, before any platform. If it refuses, nothing goes
  anywhere.
- Each platform's result goes to its own line in the uploads log: platform, id/permalink,
  and OK/FAIL. If one platform fails, the other platforms still run. The failed one gets a
  «Reintentar» button.
- The duplicate topic_id rule works per platform. A topic already on YouTube can still go
  to Instagram once.
- Caption, built from the script's own fields:
  1. the `video_title`
  2. a blank line
  3. the `video_description`, with the learningroutes.com line changed to «🔗 link en la bio»,
     because Instagram does not make links in captions clickable
  4. the script's hashtags, at most 5
  5. a 2,200-character cap

  Facebook gets the same text, with the real learningroutes.com URL.
- Long lessons stay YouTube-only. Their checkboxes are not shown.

## §5 Proof, then stop

- Upload **one** Short that the owner already approved and that runs under 90 s. Send it
  to Instagram and Facebook only (it is already on YouTube).
- Report the two permalinks, the time each step took, and the log lines.
- Do not batch-upload anything else.

## Do not

- Do not use any third-party scheduler or hosting service.
- Do not commit `.env`, any token, the app secret, or the Page/IG ids in docs.
- Do not touch Learning Routes code.

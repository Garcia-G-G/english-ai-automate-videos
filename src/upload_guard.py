"""Do not publish the same video twice — and do not silently refuse to retry.

THE DEFECT. hPdSoqjvu3E and IvO969ZeQsM are the same video published three
minutes apart, first private then public: a retry that left the first one
live. The window is structural, not a race inside one function. Every upload
path does:

    result = manager.upload(...)      # the video is now LIVE
    if result.success:
        record_publication(...)       # may fail; may never be reached

Between those two statements the video exists on YouTube and nothing on disk
says so. A retry cannot tell that state apart from "never uploaded", and at
2/day unattended that stops being an accident.

WHY unrecorded_platforms IS NOT ENOUGH ON ITS OWN. It answers "is there a
publication row?", which is exactly the wrong question in the failure window:
there is no row, because the row is what did not get written. Used alone it
returns "not published, go ahead" for the one case that produced the
duplicate. It is necessary — it is the cheap, authoritative answer for a
CLEAN previous run — but it needs the attempt log underneath it to cover the
window it cannot see.

So the decision is two-layer:

    ledger row exists          -> PUBLISHED. Skip. Cheap and certain.
    no row, no open attempt    -> never uploaded. Go ahead.
    no row, open attempt       -> AMBIGUOUS. Ask the platform before acting.

The third branch is the whole point. Blindly retrying re-publishes; blindly
skipping loses videos forever and does it silently, which is worse. Neither is
acceptable, so it reconciles against the resumable session URI captured before
the first byte was sent.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# What the caller should do about one platform.
PROCEED = "proceed"      # nothing published; upload
SKIP_DONE = "skip_done"  # already published; do not upload
SKIP_HOLD = "skip_hold"  # cannot determine; do not upload, tell a human


class Decision:
    """What to do, and why — the why is carried so callers can log it."""

    def __init__(self, action: str, reason: str, upload_id: str = None,
                 recovered: bool = False):
        self.action, self.reason = action, reason
        self.upload_id, self.recovered = upload_id, recovered

    def __repr__(self):
        return f"<Decision {self.action}: {self.reason}>"

    @property
    def should_upload(self) -> bool:
        return self.action == PROCEED


def decide(artifact: str, platform: str, *, manager=None,
           ledger_path=None, attempts_path=None) -> Decision:
    """Should `artifact` be uploaded to `platform`?

    `manager` is an UploadManager, used only to reconcile an ambiguous
    attempt. Without one an ambiguous attempt resolves to SKIP_HOLD, which is
    the safe direction: refusing to upload can be undone by a human, an
    accidental second publication cannot.
    """
    from publication_log import (ATTEMPT_PUBLISHED, find_by_artifact,
                                 open_attempt, record_attempt,
                                 record_upload_result)

    rows = [r for r in find_by_artifact(artifact, ledger_path)
            if r.get("platform") == platform]
    if rows:
        return Decision(SKIP_DONE, "already in the ledger",
                        upload_id=rows[0].get("upload_id"))

    pending = open_attempt(artifact, platform, attempts_path)
    if not pending:
        return Decision(PROCEED, "no publication row and no open attempt")

    # ── ambiguous ────────────────────────────────────────────────────
    session_uri = pending.get("session_uri")
    if not session_uri:
        # The attempt was written but the session never opened, so no bytes
        # can have reached YouTube: the init POST had not returned yet.
        if pending.get("status") == "started":
            return Decision(PROCEED,
                            "attempt started but no session was ever opened")
        return Decision(SKIP_HOLD, "open attempt with no session URI to query")

    if manager is None:
        return Decision(SKIP_HOLD,
                        "open attempt needs reconciling but no manager was given")

    backend = getattr(manager, "uploaders", {}).get(platform)
    query = getattr(backend, "query_session", None)
    if query is None:
        return Decision(SKIP_HOLD,
                        f"{platform} cannot query an interrupted session")

    try:
        if not backend.authenticate():
            return Decision(SKIP_HOLD, "cannot authenticate to reconcile")
        state = query(session_uri, pending.get("file_size") or 0)
    except Exception as exc:                              # noqa: BLE001
        logger.exception("reconciling %s/%s raised", artifact, platform)
        return Decision(SKIP_HOLD, f"reconcile raised: {exc}")

    kind = state.get("state")

    if kind == "published":
        # It IS live. Close the gap the crash left: write the publication row
        # that never got written, so the next run takes the cheap path.
        upload_id = state.get("upload_id")
        logger.warning(
            "RECOVERED: %s was already published to %s as %s; the record was "
            "missing and has been written now", artifact, platform, upload_id)
        try:
            record_upload_result(
                artifact=artifact,
                video_path=pending.get("video_path", ""),
                video_type="",
                platform=platform,
                result={"upload_id": upload_id,
                        "url": f"https://youtube.com/shorts/{upload_id}"
                               if upload_id else None,
                        "success": True},
                sent_title=pending.get("detail", ""),
                sent_description="",
                sent_hashtags=[],
                ledger_path=ledger_path,
            )
        except Exception:                                 # noqa: BLE001
            # Still do not upload again. A missing record is a bookkeeping
            # problem; a second live video is not.
            logger.exception("could not backfill the recovered publication")
        record_attempt(artifact=artifact, platform=platform,
                       status=ATTEMPT_PUBLISHED, upload_id=upload_id,
                       session_uri=session_uri,
                       detail="recovered by session query",
                       attempts_path=attempts_path)
        return Decision(SKIP_DONE, "session query says it already published",
                        upload_id=upload_id, recovered=True)

    if kind == "incomplete":
        # 308: bytes are missing, so YouTube never created the video resource.
        # Nothing is live and a fresh upload cannot duplicate anything.
        return Decision(PROCEED, f"session incomplete ({state.get('detail')})")

    if kind == "failed":
        return Decision(PROCEED, f"session failed permanently ({state.get('detail')})")

    return Decision(SKIP_HOLD,
                    f"session state undetermined ({state.get('detail')}) — "
                    f"check the channel by hand before retrying")

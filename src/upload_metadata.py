"""What actually gets PUBLISHED — one resolver for every upload path.

WHY THIS MODULE EXISTS AND NOT admin.py. The resolver was written for the two
dashboard paths and lived in admin.py, which imports streamlit at module
scope. main.py's `--batch N --upload` path could not reach it without pulling
in the whole dashboard: streamlit itself, a `logging.basicConfig` call that
overrides main.py's own logging setup, and a `load_dotenv`. So main.py grew
its OWN generate + adapt block instead — a third copy of the same four lines,
in the one path that runs with no operator watching.

That is the same drift 0b996bc closed for the other two paths, reintroduced
where nobody would see it. The fix is to put the resolver somewhere all three
can import: no streamlit, no side effects at import.

The `state` mapping is a PLAIN DICT, never `st.session_state` specifically —
the dashboard happens to pass session_state because that is where an
operator's edits live. A headless caller has no operator and passes
NO_OPERATOR_EDITS to say so explicitly, rather than relying on a default.
"""

from __future__ import annotations

import logging
from typing import Mapping

logger = logging.getLogger(__name__)

#: Explicit "there is no operator" for headless callers.
#:
#: An empty dict would work identically, but it reads as an oversight at the
#: call site — and the difference matters: the branch it selects publishes
#: generated text without anyone having seen it. A headless caller should have
#: to say that is what it means.
NO_OPERATOR_EDITS: Mapping = {}


def metadata_session_keys(video_name: str) -> tuple:
    """The three session_state keys the Upload page edits for one video."""
    return (f"meta_title_{video_name}", f"meta_desc_{video_name}",
            f"meta_tags_{video_name}")


def resolve_upload_metadata(video_name: str, script: dict, platform: str,
                            video_type: str = "educational",
                            category: str = "", state: Mapping = None) -> dict:
    """The title/description/hashtags that will actually be PUBLISHED.

    ONE resolver for all three upload paths. They used to disagree:

      admin single   read st.session_state — the operator's text
      admin bulk     called generate_metadata(script, ...) at upload time and
                     never looked at session_state at all
      main.py        called generate_metadata + adapt_for_platform inline,
                     a third copy, on the unattended path

    So a bulk upload published metadata the operator never saw, while the
    screen showed something else. That is worse than the regeneration bug it
    sat behind, because it looks like it worked.

    WHAT THE OPERATOR APPROVED WINS. If the session holds edited or
    regenerated text, it is used verbatim for every platform — the operator
    already chose it, and silently re-adapting it per platform would be the
    same class of substitution. Only when the session has nothing do we
    generate and adapt.

    `state=None` and `state=NO_OPERATOR_EDITS` behave identically. Headless
    callers should pass the constant so the intent is visible at the call
    site; the returned `source` field proves which branch ran.
    """
    state = {} if state is None else state
    title_key, desc_key, tags_key = metadata_session_keys(video_name)

    from metadata_generator import (adapt_for_platform, compose_description,
                                    generate_metadata)

    approved_title = (state.get(title_key) or "").strip()
    approved_desc = (state.get(desc_key) or "").strip()
    approved_tags = (state.get(tags_key) or "").split()

    if approved_title:
        tags = [t.lstrip("#") for t in approved_tags]
        return {
            "title": approved_title,
            # Composed HERE, through the one composer, because the operator
            # edits the body and the hashtags in two separate fields and the
            # uploader no longer joins them. Item 1 briefly sent the raw body
            # alone, which would have published the operator's text with no
            # hashtags at all.
            "description": compose_description(approved_desc, tags),
            "hashtags": tags,
            "source": "session",       # surfaced so a dry run can prove it
        }

    adapted = adapt_for_platform(
        generate_metadata(script, video_type, category), platform)
    return {
        "title": adapted["title"],
        "description": adapted["description"],
        "hashtags": [h.lstrip("#") for h in adapted["hashtags"]],
        "source": "generated",
    }

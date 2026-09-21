#!/usr/bin/env python3
"""Item-prefixed segment ids, parsed in ONE place.

    from segment_ids import bare, split_item
    split_item("i2_countdown_3")   -> (2, "countdown_3")
    bare("i2_countdown_3")         -> "countdown_3"
    bare("countdown_3")            -> "countdown_3"

WHY THIS IS ITS OWN MODULE. 1af342d gave a multi-item quiz segment ids of
the form `i<N>_<name>`, with item 1 deliberately UNPREFIXED so every stored
artifact stayed valid. The renderer learned to parse that; the QA gate did
not, and it had its own rule keyed on the bare name:

    SILENT_SEGMENT_PREFIXES = ("countdown_",)
    if not name.startswith(SILENT_SEGMENT_PREFIXES): ...

"i2_countdown_3" does not start with "countdown_". So items 2 and 3 had
their deliberately-silent countdowns counted as UNEXPLAINED silence, and
the gate rejected a correct artifact for 14.525 s of dead air -- six
countdowns it had no way to recognise.

A LEAF, with no imports, because the two callers cannot share anything
else: video/quiz.py pulls in PIL and numpy, and qa_gate is run over
finished artifacts by tools that render nothing.
"""

from __future__ import annotations

import re
from typing import Tuple

#: `i2_option_a` -> ("2", "option_a"). Item 1 is unprefixed by construction,
#: which is what keeps every artifact written before multi-item valid.
ITEM_KEY = re.compile(r"^i(\d+)_(.+)$")


def split_item(seg_id: str) -> Tuple[int, str]:
    """(item index, bare name). An unprefixed id belongs to item 1."""
    match = ITEM_KEY.match(seg_id or "")
    if not match:
        return 1, (seg_id or "")
    return int(match.group(1)), match.group(2)


def bare(seg_id: str) -> str:
    """The id with any item prefix removed — what every name-based rule
    written before multi-item is actually asking about."""
    return split_item(seg_id)[1]

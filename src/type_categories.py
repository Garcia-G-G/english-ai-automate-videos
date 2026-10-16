#!/usr/bin/env python3
"""Which topic categories each video type may draw from.

    from type_categories import resolve
    resolve("pronunciation", profile_categories=None)  -> ["pronunciation"]

WHY THIS EXISTS. Video type and topic category were INDEPENDENT DRAWS.
legacy_pipeline's author resolved the video type from the request or the
profile and then called _random_topic() without consulting it, so nothing
constrained which categories a type could draw from. Measured across 221
rendered artifacts that record both, 43 (19%) drew a category that did not
suit the type.

The pronunciation column was total: 0 of 20 pronunciation videos ever drew
from content/topics/pronunciation.json. That file holds 56 minimal pairs and
stress shifts — ship/sheep, bit/beat, REcord the noun, water British vs
American — and the type built for it had never used it once. It drew
"Asking for Help" from social and "Double negatives (grammatical error)"
from spanish_specific instead. Neither is a word anyone can pronounce.

WHAT THIS IS NOT. It is not a replacement for the audience profile's own
`categories` list, which is how the children profile is kept to kids
content. The two INTERSECT: the profile says who the video is for, this says
what the type can teach. They are different questions and both must hold.

THE MAPPING LIVES IN config.yaml, next to the duration bands, and NOT here.
A category list is an editorial judgement that will be revised by whoever
owns the content, and it should not require a code change — the same reason
the duration band is config and not a constant in a prompt string.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
TOPICS_DIR = ROOT / "content" / "topics"

_CACHE: Optional[Dict] = None


class NoEligibleCategory(ValueError):
    """A type and a profile with nothing in common.

    RAISED, NEVER DEFAULTED. Falling back to an unconstrained random draw is
    exactly the behaviour this module exists to remove: it is how a
    pronunciation video ended up teaching "Asking for Help". A combination
    with no eligible category is a configuration question for a human, and
    a loud failure is the only thing that asks it.
    """


def _config() -> Dict[str, List[str]]:
    global _CACHE
    if _CACHE is None:
        import yaml
        raw = yaml.safe_load((ROOT / "config.yaml").read_text()) or {}
        _CACHE = raw.get("type_categories") or {}
    return _CACHE


def reload() -> None:
    """Drop the cached config. For tests and a long-lived dashboard."""
    global _CACHE
    _CACHE = None


def known_categories() -> List[str]:
    """The categories that actually exist on disk."""
    return sorted(p.stem for p in TOPICS_DIR.glob("*.json"))


def allowed_for(video_type: str) -> List[str]:
    """The categories this type may draw from, in config order.

    Raises for a type with no declared list rather than returning
    everything: an undeclared type is the unconstrained draw this module
    replaces, and silently permitting all 20 would reinstate it.
    """
    entry = _config().get((video_type or "").lower())
    if not entry:
        raise NoEligibleCategory(
            f"video type {video_type!r} declares no category list; add one to "
            f"config.yaml type_categories. Declared types: "
            f"{', '.join(sorted(_config())) or '(none)'}")
    return list(entry)


def resolve(video_type: str, profile_categories=None) -> List[str]:
    """The categories this type may draw from FOR THIS AUDIENCE.

    The intersection of the type's list and the profile's, in the type's
    order. A profile with no list of its own means "no audience
    restriction", which is how the adults profile is configured today, and
    the type's list stands alone.

    Raises NoEligibleCategory when the intersection is empty — see the
    exception's docstring for why that is not a fallback.
    """
    allowed = allowed_for(video_type)

    on_disk = set(known_categories())
    missing = [c for c in allowed if c not in on_disk]
    if missing:
        # A category in config with no file behind it silently shrinks the
        # pool, so it is worth a line in the log even though it is not fatal.
        logger.warning("type_categories: %s lists %s, which has no file in %s",
                       video_type, ", ".join(missing), TOPICS_DIR)
    eligible = [c for c in allowed if c in on_disk]

    if profile_categories:
        wanted = {str(c).lower() for c in profile_categories}
        eligible = [c for c in eligible if c in wanted]
        if not eligible:
            raise NoEligibleCategory(
                f"video type {video_type!r} may draw from "
                f"{', '.join(allowed_for(video_type))}, and this audience "
                f"allows {', '.join(sorted(wanted))} — the two do not "
                f"overlap, so there is no topic this video could be about. "
                f"Widen one of the two lists in config.yaml.")

    if not eligible:
        raise NoEligibleCategory(
            f"video type {video_type!r} has no eligible category: its list "
            f"({', '.join(allowed)}) matches no file in {TOPICS_DIR}")
    return eligible

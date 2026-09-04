#!/usr/bin/env python3
"""Real moving footage per video, fetched from that video's own topic.

    from topic_clips import fetch_for_topic
    result = fetch_for_topic("At the Airport - Check-in", "travel",
                             duration=38.0, out_dir=artifact_dir / "clips")

The owner has asked for MOVING backgrounds repeatedly — "un avión volando
sobre un río, un tipo andando en kayak por el mar muerto". Not a still with a
Ken Burns pan over it: real footage. src/video/clip_background.py has been
able to play a library of mp4s as the frame background for some time; what it
never had was any mp4s. assets/clips/adults/ and assets/clips/kids/ are both
empty. The feature was starved, not missing. This module feeds it.

WHY THE QUERY IS SHAPED THE WAY IT IS — THE F3 LESSON, APPLIED

F3 generated fourteen background images and eleven came out looking alike.
The cause was not the image model: CATEGORY_SCENES had 11 keys for 20 real
categories, so 9 categories plus every unknown one fell through to a single
DEFAULT stem, and a single stem can only draw one picture. The measurement
that would have caught it (contrast) was blind to it, because eleven copies
of the same room score exactly as well as eleven different rooms.

Rebuilding that with video would be worse, not better — a repeated clip is
more obvious than a repeated still, because the motion makes it recognisable
within a second.

So there is NO CATCH-ALL HERE, deliberately. CATEGORY_FOOTAGE has one entry
per category in content/topics/, checked by test rather than by eye
(tests/test_topic_clips.py asserts the key set equals the directory
listing), and an unknown category raises instead of quietly borrowing a
default. `query_space()` reports the size so the number is on the record and
a future edit that shrinks it is visible.

WHY PEXELS

Verified before writing, not researched here: the free video search API,
200 requests/hour and 20,000/month, no subscription, portrait orientation
supported natively. The license permits commercial use, modification and
monetised YouTube, and does not require attribution — but the API terms ask
separately for a visible link back to Pexels, which is satisfied by one line
in the channel description. See ATTRIBUTION_LINE below.

COST. Zero. This also REPLACES the gpt-image-2 call that tier 3 makes, so a
video that takes clips costs $0.041 less than one that takes a generated
image.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
TOPICS_DIR = ROOT / "content" / "topics"

#: Downloads are cached here by query, keyed on the query text. The artifact
#: gets its own copies (hardlinks where the filesystem allows); this is only
#: the download cache, so a second video searching "aerial view of a river"
#: costs one HTTP round trip instead of a fresh 3 MB download.
CACHE_DIR = ROOT / "assets" / "clips" / "_cache"

#: One line for the channel description. The license does not require
#: attribution; the API terms ask for a visible Pexels link, and this is it.
#: Recorded here rather than in a doc so it travels with the code that
#: incurs the obligation.
ATTRIBUTION_LINE = "Stock footage: Pexels (https://www.pexels.com)"

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/videos/search"

#: Portrait, and big enough that upscaling to 1080x1920 does not soften it.
#: `size=medium` on the request already biases the result set; this is the
#: per-file choice within one result.
MIN_CLIP_HEIGHT = 960
PREFERRED_CLIP_HEIGHT = 1920

#: A background clip is scenery, not a story. Long clips are mostly wasted
#: bytes — the playlist cuts away long before they end — and short ones make
#: the playlist churn. Both bounds are on the SOURCE clip, in seconds.
MIN_CLIP_SECONDS = 4.0
MAX_CLIP_SECONDS = 35.0

#: Hard ceiling per download. Pexels serves some 4K files at 40 MB+ and a
#: background does not earn that; the fitter crops them to 1080x1920 anyway.
MAX_CLIP_BYTES = 12 * 1024 * 1024

#: How much footage to fetch relative to the video's duration. Above 1.0 so
#: the playlist has something to cut to rather than looping one clip, and so
#: a single unreadable clip is a fraction of the video and not all of it.
COVERAGE_FACTOR = 1.3

#: Never fewer than this many distinct clips, however short the video. Two
#: clips is the minimum that reads as "footage" rather than "a video file
#: playing behind the text".
MIN_CLIPS = 3
MAX_CLIPS = 8


class UnknownCategory(ValueError):
    """A category with no footage table.

    Raised, never defaulted. Absorbing this quietly is precisely the bug
    that made eleven of fourteen F3 images identical: a missing key became a
    shared fallback, and nothing measured sameness so nothing complained.
    """


#: FOOTAGE SUBJECTS PER CATEGORY, one entry for every file in
#: content/topics/. Concrete, filmable things — a stock video search for an
#: abstraction ("grammar") returns whiteboards and stock-photo handshakes,
#: so each stem names something a camera can point at.
#:
#: Six per category rather than one, because `social` alone appears six times
#: in the job history and one stem per category means those six videos share
#: their footage. Multiplied by the MOTION axis below, see query_space().
CATEGORY_FOOTAGE = {
    "business": [
        "aerial view of a city skyline at sunrise",
        "glass office tower reflecting clouds",
        "busy pedestrian crossing from above",
        "train travelling through a modern city",
        "harbour cranes loading cargo ships",
        "sunlight moving across a quiet boardroom window",
    ],
    "work_office": [
        "coffee being poured into a cup",
        "hands typing on a laptop keyboard",
        "sunlight moving across an empty desk",
        "plants on a windowsill in an office",
        "a lift ascending a glass atrium",
        "notebook pages turning in the breeze",
    ],
    "travel": [
        "an airplane flying over a river",
        "a kayak paddling across open sea",
        "a train winding through mountains",
        "waves breaking on a tropical beach",
        "a hot air balloon rising over a valley",
        "a road trip through desert canyons",
    ],
    "social": [
        "friends laughing around a campfire",
        "a rooftop party with string lights at dusk",
        "people walking through a night market",
        "confetti falling over a celebrating crowd",
        "a crowded cafe terrace in summer",
        "hands clinking glasses in a toast",
    ],
    "everyday_expressions": [
        "rain running down a window pane",
        "laundry drying on a line in the wind",
        "a cat stretching in a sunlit room",
        "steam rising from a mug on a table",
        "a bicycle rolling down a quiet street",
        "curtains moving in an open window",
    ],
    "idioms": [
        "a storm cloud rolling over open fields",
        "ice cracking on a frozen lake",
        "a chess piece being moved on a board",
        "a candle flame flickering in the dark",
        "birds scattering from a rooftop",
        "dominoes falling in a line",
    ],
    "phrasal_verbs": [
        "an escalator moving through a station",
        "a door opening onto a bright garden",
        "water pouring over a waterfall",
        "a hand turning the pages of a book",
        "a lift door closing in a hotel lobby",
        "a paper plane gliding through the air",
    ],
    "false_friends": [
        "two roads dividing in a forest",
        "reflections rippling on still water",
        "a mirror reflecting a moving crowd",
        "twin waterfalls side by side",
        "shadows and light alternating on a wall",
        "a prism splitting light into colours",
    ],
    "confusing_words": [
        "fog drifting through a pine forest",
        "a compass needle turning",
        "a maze of hedges seen from above",
        "raindrops merging on glass",
        "a signpost at a country crossroads",
        "shifting sand dunes in the wind",
    ],
    "common_mistakes": [
        "waves erasing footprints in the sand",
        "a pencil eraser on white paper",
        "chalk being wiped from a blackboard",
        "crumpled paper unfolding",
        "a potter reshaping clay on a wheel",
        "a typewriter carriage returning",
    ],
    "grammar": [
        "gears turning inside a clock",
        "a printing press running",
        "library shelves passing in a slow pan",
        "an architect's blueprint unrolling",
        "scaffolding rising against the sky",
        "a bridge structure seen from below",
    ],
    "pronunciation": [
        "a microphone in a recording studio",
        "sound waves on a mixing desk display",
        "a guitar string vibrating in close up",
        "water ripples spreading in a circle",
        "a radio tower against a moving sky",
        "headphones on a table under warm light",
    ],
    "spanish_specific": [
        "a flamenco dress spinning",
        "sunlight through a tiled Andalusian courtyard",
        "olive trees moving in the wind",
        "a Spanish plaza fountain at golden hour",
        "waves against a Mediterranean cliff",
        "a market stall of coloured ceramics",
    ],
    "cultural": [
        "lanterns floating on a river at night",
        "a carnival parade in the street",
        "fireworks over a city skyline",
        "traditional dancers in motion",
        "flags moving in the wind",
        "a temple courtyard at sunrise",
    ],
    "food_restaurant": [
        "steam rising from a pan in a kitchen",
        "coffee being poured in slow motion",
        "fresh vegetables under running water",
        "bread dough being kneaded",
        "a chef plating a dish",
        "a busy market fruit stall",
    ],
    "technology": [
        "server room lights blinking in the dark",
        "circuit board macro with moving light",
        "a drone taking off at dusk",
        "code scrolling on a monitor",
        "a robotic arm assembling parts",
        "fibre optic cables glowing",
    ],
    "slang": [
        "a skateboarder riding through a city",
        "graffiti artist spraying a wall",
        "neon signs flickering at night",
        "a basketball bouncing on an outdoor court",
        "a subway train rushing past",
        "sneakers walking on wet pavement",
    ],
    "kids_animals": [
        "puppies playing on grass",
        "a butterfly landing on a flower",
        "ducklings swimming in a pond",
        "a kitten chasing a toy",
        "horses running in a green field",
        "fish swimming in a coral reef",
    ],
    "kids_colors": [
        "coloured paint mixing in water",
        "rainbow balloons rising into the sky",
        "coloured powder exploding in slow motion",
        "a field of bright wildflowers",
        "soap bubbles floating in sunlight",
        "coloured lights spinning at a fairground",
    ],
    "kids_numbers": [
        "wooden blocks being stacked",
        "a clock's second hand moving",
        "bubbles rising in a glass of water",
        "raindrops counting on a puddle",
        "an abacus being moved by hands",
        "birds landing one by one on a wire",
    ],
}

#: The second axis. Stock video responds strongly to camera language, so
#: this changes the returned footage far more than its length suggests — an
#: "aerial view of a river" and a "close up of a river" are different films.
MOTION = [
    "aerial drone shot",
    "slow motion",
    "cinematic close up",
    "timelapse",
    "handheld tracking shot",
]


def categories() -> List[str]:
    """The category names on disk, which the footage table must cover."""
    return sorted(p.stem for p in TOPICS_DIR.glob("*.json"))


def query_space() -> Dict:
    """How many distinct searches this table can produce.

    Reported rather than assumed. The F3 failure was a query space of one
    for eleven categories, and nothing in the output said so.
    """
    per_category = {c: len(v) * len(MOTION) for c, v in CATEGORY_FOOTAGE.items()}
    on_disk = set(categories())
    return {
        "categories": len(CATEGORY_FOOTAGE),
        "categories_on_disk": len(on_disk),
        "missing_from_table": sorted(on_disk - set(CATEGORY_FOOTAGE)),
        "orphan_in_table": sorted(set(CATEGORY_FOOTAGE) - on_disk),
        "subjects_per_category": len(next(iter(CATEGORY_FOOTAGE.values()))),
        "motion": len(MOTION),
        "per_category": min(per_category.values()),
        "total": sum(per_category.values()),
    }


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "clip").lower()).strip("_") or "clip"


def _axis_pick(seq, seed_text: str, salt: str):
    """Deterministic choice from `seq`. Same topic, same footage.

    Mirrors topic_background._axis_pick on purpose: a re-run must reproduce
    the video rather than quietly fetching different footage, which would
    make a rendering bug impossible to reproduce.
    """
    h = hashlib.sha256(f"{salt}:{seed_text}".encode("utf-8")).digest()
    return seq[int.from_bytes(h[:4], "big") % len(seq)]


def build_queries(topic: str, category: str, count: int = 3) -> List[str]:
    """`count` DISTINCT search queries for one video.

    Distinct is the whole point and is enforced, not hoped for: the subject
    walks through the category's list from a topic-seeded offset, so two
    queries for the same video can never collide, and two videos in the same
    category start at different offsets.
    """
    cat = (category or "").lower()
    subjects = CATEGORY_FOOTAGE.get(cat)
    if not subjects:
        raise UnknownCategory(
            f"no footage subjects for category {category!r}; add it to "
            f"CATEGORY_FOOTAGE — known categories are "
            f"{', '.join(sorted(CATEGORY_FOOTAGE))}"
        )

    slug = _slug(topic)
    offset = int.from_bytes(
        hashlib.sha256(f"subject:{slug}".encode("utf-8")).digest()[:4], "big")
    count = max(1, min(count, len(subjects)))

    queries = []
    for i in range(count):
        subject = subjects[(offset + i) % len(subjects)]
        motion = _axis_pick(MOTION, f"{slug}:{i}", "motion")
        queries.append(f"{motion} {subject}")
    return queries


def clips_needed(duration: float) -> int:
    """How many clips to fetch to cover `duration` with room to cut."""
    typical = (MIN_CLIP_SECONDS + MAX_CLIP_SECONDS) / 2
    want = int((float(duration or 0) * COVERAGE_FACTOR) // typical) + 1
    return max(MIN_CLIPS, min(want, MAX_CLIPS))


# ─────────────────────────── the Pexels client ───────────────────────────

def api_key() -> Optional[str]:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    return key or None


def _cache_slot(query: str) -> Path:
    """One directory per query. The query text is stored beside the files so
    a cache directory can be read back without reversing the hash."""
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{_slug(query)[:48]}_{digest}"


def _pick_file(video: dict) -> Optional[dict]:
    """The best portrait file in one Pexels result, or None.

    Prefers the largest file that is still under MAX_CLIP_BYTES worth of
    resolution — a 4K background is thrown away by the 1080x1920 crop.
    """
    files = [
        f for f in (video.get("video_files") or [])
        if (f.get("height") or 0) >= MIN_CLIP_HEIGHT
        and (f.get("height") or 0) >= (f.get("width") or 0)   # portrait
        and f.get("link")
    ]
    if not files:
        return None
    # Closest to 1920 tall without going far above it.
    return min(files, key=lambda f: abs((f.get("height") or 0) - PREFERRED_CLIP_HEIGHT))


def search(query: str, *, key: str = None, per_page: int = 8,
           timeout: float = 20.0) -> List[dict]:
    """One Pexels video search. Returns the raw `videos` list.

    Never raises for a network or API problem — a background must cost a
    plain background, never the video. Returns [] and logs instead.
    """
    import requests

    key = key or api_key()
    if not key:
        logger.warning("clips: no PEXELS_API_KEY — cannot search %r", query)
        return []
    try:
        response = requests.get(
            PEXELS_SEARCH_URL,
            headers={"Authorization": key},
            params={"query": query, "orientation": "portrait",
                    "size": "medium", "per_page": per_page},
            timeout=timeout,
        )
        if response.status_code != 200:
            logger.warning("clips: Pexels returned %s for %r: %s",
                           response.status_code, query, response.text[:200])
            return []
        return response.json().get("videos") or []
    except Exception:                                       # noqa: BLE001
        logger.exception("clips: search failed for %r", query)
        return []


def _download(url: str, dest: Path, timeout: float = 60.0) -> Optional[Path]:
    """Stream one clip to `dest`, refusing anything over MAX_CLIP_BYTES.

    Streamed and size-checked as it arrives rather than after: the ceiling
    exists to bound disk, and a check that runs once the file is already on
    disk does not bound anything.
    """
    import requests

    tmp = dest.with_suffix(".part")
    try:
        with requests.get(url, stream=True, timeout=timeout) as response:
            if response.status_code != 200:
                logger.warning("clips: download %s -> HTTP %s", url, response.status_code)
                return None
            written = 0
            with open(tmp, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1 << 16):
                    written += len(chunk)
                    if written > MAX_CLIP_BYTES:
                        logger.info("clips: %s exceeds %d bytes — skipping",
                                    url, MAX_CLIP_BYTES)
                        handle.close()
                        tmp.unlink(missing_ok=True)
                        return None
                    handle.write(chunk)
        tmp.replace(dest)
        return dest
    except Exception:                                       # noqa: BLE001
        logger.exception("clips: download failed for %s", url)
        tmp.unlink(missing_ok=True)
        return None


def fetch_query(query: str, *, key: str = None) -> Optional[Path]:
    """One clip for one query, from cache if it is already there.

    Returns the cached file's path. The caller links or copies it into the
    artifact; the cache itself is never handed to the renderer, so a cache
    eviction cannot pull footage out from under a rendered video.
    """
    slot = _cache_slot(query)
    existing = sorted(slot.glob("*.mp4"))
    if existing:
        logger.info("clips: cache HIT for %r (%s)", query, existing[0].name)
        return existing[0]

    videos = search(query, key=key)
    for video in videos:
        seconds = float(video.get("duration") or 0)
        if not (MIN_CLIP_SECONDS <= seconds <= MAX_CLIP_SECONDS):
            continue
        chosen = _pick_file(video)
        if not chosen:
            continue
        slot.mkdir(parents=True, exist_ok=True)
        dest = slot / f"pexels_{video.get('id')}.mp4"
        if _download(chosen["link"], dest):
            (slot / "query.json").write_text(json.dumps({
                "query": query,
                "pexels_id": video.get("id"),
                "pexels_url": video.get("url"),
                "duration": seconds,
                "width": chosen.get("width"),
                "height": chosen.get("height"),
                "fps": chosen.get("fps"),
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, indent=2), encoding="utf-8")
            logger.info("clips: cache MISS for %r -> %s (%.1fs, %sx%s, %.1f MB)",
                        query, dest.name, seconds, chosen.get("width"),
                        chosen.get("height"), dest.stat().st_size / 1e6)
            return dest
    logger.warning("clips: no usable clip for %r", query)
    return None


def _place(source: Path, out_dir: Path) -> Path:
    """Put a cached clip into the artifact. Hardlink where possible.

    A hardlink costs one inode instead of several megabytes, and the cache
    and the artifact are both under the repo so they are almost always the
    same filesystem. Falls back to a copy when they are not.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / source.name
    if dest.exists():
        return dest
    try:
        os.link(source, dest)
    except OSError:
        shutil.copy2(source, dest)
    return dest


def fetch_for_topic(topic: str, category: str = None, *,
                    duration: float = 30.0,
                    out_dir: Path = None,
                    key: str = None) -> Optional[Dict]:
    """Fetch this video's footage into ITS OWN directory. Returns a dict.

    `out_dir` is the artifact's own clips directory, not a global one — the
    same reason F3 writes its image per artifact. It is also what closes the
    objection recorded at legacy_pipeline.py:244, which omitted topic and
    category from the Studio background call because "the legacy topic tier
    writes to global output/backgrounds and has no destination argument".
    This one takes a destination.

    Returns None when nothing could be fetched, so the caller falls through
    to the next background tier rather than rendering against an empty
    directory.
    """
    if out_dir is None:
        raise ValueError("out_dir is required — clips belong to one artifact")
    out_dir = Path(out_dir)

    want = clips_needed(duration)
    queries = build_queries(topic, category, count=want)
    logger.info("clips: %r (%s) -> %d queries for %.1fs",
                topic, category, len(queries), duration)

    placed, records, total_bytes = [], [], 0
    for query in queries:
        cached = fetch_query(query, key=key)
        if not cached:
            continue
        dest = _place(cached, out_dir)
        size = dest.stat().st_size
        total_bytes += size
        placed.append(dest)
        meta_path = cached.parent / "query.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        records.append({"query": query, "path": str(dest),
                        "bytes": size, **meta})

    if not placed:
        logger.warning("clips: nothing fetched for %r (%s)", topic, category)
        return None

    return {
        "dir": str(out_dir),
        "topic": topic,
        "category": category,
        "queries": queries,
        "clips": records,
        "clip_count": len(placed),
        "bytes": total_bytes,
        "megabytes": round(total_bytes / 1e6, 2),
        "cost_usd": 0.0,
        "attribution": ATTRIBUTION_LINE,
    }

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
#:
#: TWENTY since 2026-10-14. Measured over output/: 54 videos placed 295 clips
#: but only 177 distinct, 58 of them reused and the top ones seven times each
#: -- six subjects x five motions is thirty queries per category, and each
#: query caches exactly one clip. Fourteen more subjects per category take it
#: to a hundred queries before anything else changes.
CATEGORY_FOOTAGE = {
    "business": [
        "aerial view of a city skyline at sunrise",
        "a harbour full of cargo ships from above",
        "motorway traffic flowing through open country",
        "a bridge spanning a wide river at dawn",
        "a container port seen from the air",
        "a lit city grid seen from the air at night",
        "glass towers reflecting moving clouds",
        "a financial district street at blue hour",
        "an empty airport runway at sunrise",
        "freight trains moving through a rail yard",
        "a cable car rising over a modern city",
        "rooftop gardens on high buildings",
        "boats moving along a city river at dusk",
        "a highway interchange seen from above",
        "skyscraper windows lighting up at dusk",
        "a stock of shipping containers in rows",
        "a tram crossing a modern square",
        "an airport apron with planes taxiing",
        "a riverside promenade in early light",
        "clouds passing over a tall tower",
    ],
    "work_office": [
        "a city skyline at first light from above",
        "a long bridge full of morning traffic",
        "a river running through a bright city",
        "commuter trains crossing open ground",
        "a business district lit at night from above",
        "sunrise over a wide urban horizon",
        "morning light moving across a modern atrium",
        "an escalator flow in a glass building",
        "a quiet coworking terrace with plants",
        "rain on tall office windows",
        "a city ferry crossing in the morning",
        "bike lanes busy at rush hour from above",
        "a train platform as a train arrives",
        "sunset over rooftops and cranes",
        "elevators rising in a glass shaft",
        "a park bench area at lunchtime from above",
        "a coffee cart street at dawn",
        "lights switching on across a skyline",
        "a metro train crossing a bridge",
        "clouds over a grid of office roofs",
    ],
    "travel": [
        "an airplane flying over a wide river",
        "a kayak paddling across open sea",
        "a train winding through mountains",
        "waves breaking on a tropical beach",
        "a hot air balloon rising over a valley",
        "a road trip through desert canyons",
        "a ferry crossing turquoise water",
        "a cable car above snowy peaks",
        "a sailboat on a calm bay at sunset",
        "a mountain lake reached by a winding road",
        "camels crossing desert dunes",
        "a waterfall plunging into a jungle pool",
        "a lighthouse road by the ocean",
        "an old harbour town from the water",
        "a glacier seen from a boat",
        "a coastal train along cliffs",
        "a scenic overlook above a fjord",
        "a night train crossing a lit bridge",
        "a beach path through palm trees",
        "a mountain village under fresh snow",
    ],
    "social": [
        "a crowded beach seen from above in summer",
        "an outdoor festival field in daylight",
        "people crossing a wide sunlit plaza",
        "a picnic meadow under open sky",
        "a beach bonfire under an open night sky",
        "a coastal town seen from the water",
        "lanterns over a street festival from above",
        "a riverside walk on a summer evening",
        "a busy pier at sunset",
        "a town square with a fountain in sunlight",
        "boats gathered in a bay on a holiday",
        "a rooftop terrace at dusk over a city",
        "fireworks over a harbour",
        "a pedestrian bridge full of walkers",
        "a crowded ice rink from above",
        "a carousel turning at a fair",
        "a long table in an outdoor garden at golden hour",
        "kites flying over a seaside park",
        "string lights over a courtyard at night",
        "a concert crowd under stage lights from afar",
    ],
    "everyday_expressions": [
        "a quiet street lined with trees in the wind",
        "a park in bright afternoon light",
        "a coastal path above the sea",
        "a quiet coastal town lit at night from above",
        "a bicycle crossing a wide open square",
        "rain sweeping across open fields",
        "laundry drying on a balcony in the wind",
        "a bus stop on a rainy evening",
        "morning light through window blinds",
        "steam rising from a cup by a window",
        "a dog walking path in a park",
        "autumn leaves falling on a sidewalk",
        "a corner bakery street at dawn",
        "children's swings moving in the wind",
        "sunset light on apartment buildings",
        "a quiet train window view of fields",
        "snow falling on a quiet street",
        "a garden hose watering plants",
        "clouds passing over rooftops",
        "a market stall being set up at sunrise",
    ],
    "idioms": [
        "a storm cloud rolling over open fields",
        "ice cracking across a frozen lake",
        "birds scattering above an empty plain",
        "lightning over an open plain at night",
        "a lone tree on a windswept hill",
        "waves hitting cliffs in heavy weather",
        "a fog bank rolling over the sea",
        "a waterfall in heavy rain",
        "a volcano steaming under clouds",
        "a whirlpool in a fast river",
        "a desert dust storm approaching",
        "a frozen waterfall in winter",
        "clouds parting over a mountain",
        "a tide racing across mud flats",
        "a lone boat on a stormy sea",
        "a sunbeam breaking through a forest",
        "an iceberg drifting in grey water",
        "a hailstorm over open fields",
        "a rainbow after a storm over hills",
        "wind bending trees on a cliff",
    ],
    "phrasal_verbs": [
        "a road winding up an open mountainside",
        "a river running through a wide canyon",
        "a trail climbing above the treeline",
        "a train crossing an open plain",
        "car lights tracing a mountain road at night",
        "a boat leaving a harbour into open sea",
        "a cable ferry crossing a river",
        "a funicular climbing a hillside",
        "a road tunnel exit into sunlight",
        "a ski lift moving up a slope",
        "a drawbridge lifting over a canal",
        "a paraglider taking off from a ridge",
        "a hot spring steaming in the snow",
        "a zip line over a forest canopy",
        "a canal lock filling with water",
        "a sailboat setting off at dawn",
        "a staircase path up a sea cliff",
        "a river barge passing under bridges",
        "a roller coaster climbing against the sky",
        "a kite surfer jumping over waves",
    ],
    "false_friends": [
        "mountains reflected in a still lake",
        "twin waterfalls in a green gorge",
        "a symmetrical coastline from the air",
        "clouds mirrored on a salt flat",
        "two rivers meeting in open country",
        "stars reflected on a still lake at night",
        "a city reflected in a calm river",
        "a palace reflected in a long pool",
        "a forest reflected in a mountain lake",
        "a skyline reflected on wet streets",
        "twin peaks above a valley of clouds",
        "a shoreline mirrored in morning calm",
        "two bridges side by side over a river",
        "a double rainbow over farmland",
        "mirror-like rice paddies at sunrise",
        "a canyon mirrored in still water",
        "sailboats mirrored in a harbour",
        "a sunset mirrored in tidal pools",
        "two lighthouses at a harbour mouth",
        "a pier reflected in glassy water",
    ],
    "confusing_words": [
        "two roads dividing across open plains",
        "fog lifting off a wide pine valley",
        "a river fork seen from the air",
        "a signpost at a country crossroads",
        "a lighthouse beam sweeping over the sea at night",
        "a coastline splitting into two bays",
        "a maze garden seen from above",
        "a road splitting around a mountain",
        "a river delta branching into streams",
        "a railway junction from above",
        "a winding staircase seen from the top",
        "a roundabout with traffic from above",
        "a forest path forking in autumn",
        "crossing ski trails on a snowy slope",
        "a braided river in a wide valley",
        "boats crossing paths in a bay",
        "a highway splitting at dusk",
        "contrails crossing in a blue sky",
        "a trail fork above a valley",
        "overlapping waves on a sandbar",
    ],
    "common_mistakes": [
        "waves erasing footprints on a wide beach",
        "a river carving a bend through open land",
        "shifting sand dunes under a clear sky",
        "moonlight moving across an open desert",
        "clouds reshaping over a mountain ridge",
        "tide filling a long empty estuary",
        "a sandcastle washed away by the tide",
        "snow melting off a roof in sunlight",
        "a candle flame flickering by a window",
        "raindrops running down a window",
        "footprints filling with snow",
        "leaves drifting down a stream",
        "an hourglass of sand dunes in wind",
        "a melting icicle dripping",
        "ink-like clouds spreading at sunset",
        "ripples erasing a reflection",
        "a path covered by falling leaves",
        "fog swallowing a bridge",
        "a wave reshaping a beach",
        "sand pouring down a dune face",
    ],
    "grammar": [
        "a viaduct crossing a wide green valley",
        "terraced fields in geometric rows",
        "a long bridge over open water",
        "a lighthouse on an exposed headland",
        "a lit bridge crossing open water at night",
        "a canal running straight through farmland",
        "a spiral staircase from above",
        "a modern bridge with a cable pattern",
        "rows of greenhouses from the air",
        "a salt evaporation pond pattern from above",
        "a vineyard in straight lines",
        "a train crossing a stone arch bridge",
        "a geometric park from the air",
        "a harbour breakwater from above",
        "a solar panel grid in sunlight",
        "a symmetrical palace garden",
        "a city block grid at noon",
        "parallel canals in a city",
        "a dam spillway with flowing water",
        "a lighthouse spiral seen from below",
    ],
    "pronunciation": [
        "wind moving across tall grass",
        "waves breaking along an open shore",
        "a wide canyon in afternoon light",
        "the milky way over an open desert",
        "clouds racing over an open ridge",
        "a valley opening below a mountain pass",
        "a mountain stream over smooth stones",
        "wind chimes moving in the breeze",
        "rain falling on a forest canopy",
        "waves rolling into a sea cave",
        "a desert wind lifting sand",
        "a wheat field rippling in the wind",
        "fog flowing over a ridge",
        "snow blowing across a high pass",
        "a river rapids in sunlight",
        "sea foam on black sand",
        "reeds moving by a lake",
        "a geyser erupting",
        "birds in a murmuration at dusk",
        "bubbles rising in clear water",
    ],
    "spanish_specific": [
        "olive groves moving in the wind",
        "a Mediterranean cliff above clear water",
        "a wide Andalusian plaza at golden hour",
        "sunflower fields to the horizon",
        "a hill town lit at night above the coast",
        "a coastal road above the Mediterranean",
        "a white village on a hill in sunlight",
        "a flamenco courtyard with orange trees",
        "vineyards in the Spanish countryside",
        "a lighthouse on a Galician coast",
        "a desert in Almería from above",
        "a Canary Islands volcanic coast",
        "a Mexican colonial square at dusk",
        "agave fields in Jalisco",
        "a colourful street in Guanajuato",
        "a Patagonian lake under mountains",
        "a Colombian coffee hillside",
        "Andean peaks above a valley",
        "a Caribbean beach in Puerto Rico",
        "a cathedral square in Salamanca",
    ],
    "cultural": [
        "a temple courtyard at sunrise from above",
        "a hilltop village in afternoon light",
        "an open plaza with flags in the wind",
        "terraced rice fields in morning sun",
        "lanterns rising over an open field at night",
        "an ancient ruin on an open hillside",
        "a lantern festival on a river",
        "a cherry blossom path in spring",
        "a desert fortress at sunset",
        "a Moroccan rooftop view at dusk",
        "a floating market from above",
        "colourful houses on a harbour hill",
        "a stone bridge over an old river town",
        "prayer flags in mountain wind",
        "a pagoda on a misty hill",
        "a Greek island village above the sea",
        "a medieval castle above a valley",
        "canal boats in an old city",
        "a mosque courtyard at sunrise",
        "a Viking-style wooden church in snow",
    ],
    "food_restaurant": [
        "rows of vines on a sunlit hillside",
        "an orchard in full bloom from above",
        "an open air night market seen from above",
        "fishing boats returning to a bright harbour",
        "wheat fields moving in the wind",
        "terraced farmland at golden hour",
        "lemon trees in a sunny grove",
        "a coffee plantation on a hillside",
        "olive harvest under a blue sky",
        "a fishing village at dawn",
        "tea terraces in the mist",
        "an apple orchard in autumn",
        "a lavender field in summer",
        "a farmers market street from above",
        "cows grazing on an alpine meadow",
        "a citrus orchard at golden hour",
        "a cocoa farm in the tropics",
        "a rice field being flooded",
        "pumpkins in an autumn field",
        "a seaside town with fish stalls",
    ],
    "technology": [
        "wind turbines turning on open hills",
        "a solar farm seen from the air",
        "a satellite dish array in a desert",
        "power lines crossing wide open land",
        "a drone rising above a green valley",
        "a satellite trail across a starry sky",
        "a data centre corridor of lights",
        "a high-speed train passing",
        "a radio telescope under stars",
        "a rocket launch plume in the distance",
        "an electric car charging at night",
        "a wind farm offshore",
        "a highway of headlights at night",
        "a hydroelectric dam",
        "a smart city skyline with lights",
        "cables of a suspension bridge",
        "a satellite view of night lights",
        "a robotic warehouse from above",
        "a fibre-optic glow abstract",
        "a lighthouse with a rotating beam",
    ],
    "slang": [
        "a skatepark under open sky in daylight",
        "a rooftop view over a bright city",
        "an outdoor basketball court from above",
        "a city skyline glowing after sunset",
        "city streets from a high vantage point",
        "a coastal highway in afternoon sun",
        "a skateboarder at sunset by the sea",
        "graffiti walls in an urban park",
        "a night city from a moving car",
        "neon signs in the rain",
        "a surfing beach on a sunny day",
        "a rooftop basketball court at dusk",
        "bikes riding across a bridge",
        "a city waterfront at night",
        "a street food alley lit at night",
        "a beach volleyball court from above",
        "a summer pool from above",
        "a city park on a hot day",
        "a boardwalk at sunset",
        "a subway train passing at night",
    ],
    "kids_animals": [
        "horses running across a green field",
        "ducklings swimming on an open pond",
        "a flock of birds over a wide meadow",
        "deer crossing a sunlit clearing",
        "dolphins moving through open sea",
        "fireflies over an open meadow at dusk",
        "penguins waddling on ice",
        "a giraffe walking on the savanna",
        "butterflies in a flower meadow",
        "a turtle swimming in clear water",
        "sheep running on a green hill",
        "a panda eating bamboo",
        "a kitten playing in the grass",
        "a puppy running on a beach",
        "elephants walking at a water hole",
        "goldfish in a pond",
        "a squirrel in an autumn tree",
        "a hummingbird at a flower",
        "lambs in a spring field",
        "a whale tail in the ocean",
    ],
    "kids_colors": [
        "a field of bright wildflowers in the wind",
        "hot air balloons rising over a valley",
        "an autumn forest from above",
        "a rainbow over open countryside",
        "tulip fields in rows at sunrise",
        "northern lights over an open valley",
        "coloured smoke drifting over a field",
        "a lavender field in purple rows",
        "a pink sunset over the sea",
        "orange autumn leaves falling",
        "a blue lagoon from above",
        "yellow canola fields from the air",
        "coloured umbrellas on a beach",
        "a red poppy field in wind",
        "green rice terraces",
        "a turquoise river in a canyon",
        "colourful houses along a canal",
        "a coral reef with bright fish",
        "rainbow-coloured stairs in a park",
        "a field of sunflowers turning",
    ],
    "kids_numbers": [
        "birds landing one by one on open wires",
        "rows of trees passing in an aerial shot",
        "ripples spreading across a wide lake",
        "dunes repeating to the horizon",
        "waves arriving on a long empty beach",
        "stars turning over an open horizon",
        "ducks swimming in a line",
        "boats moored in a row",
        "stepping stones across a stream",
        "a train with many wagons crossing a plain",
        "rows of beach huts",
        "pine trees in rows on a hill",
        "a flock of geese in a V formation",
        "fishing boats lined up at a pier",
        "bales of hay across a field",
        "wind turbines in a row",
        "street lamps lighting up one by one",
        "lanes of a running track from above",
        "a staircase of rice terraces",
        "ripples from raindrops on a pond",
    ],
    # how_do_you_say: the notebook covers the middle of the frame, so these
    # are calm, open, everyday scenes that read as a margin, not a subject.
    "basic_vocab": [
        "a quiet suburban street in morning sun",
        "a sunlit kitchen window with plants",
        "a city park with trees in soft light",
        "a market street from above at midday",
        "clouds drifting over green hills",
        "a calm lake shore in early light",
        "a sunny garden with flowers",
        "a bicycle leaning by a fence in the sun",
        "a bus driving down a quiet street",
        "a playground in the morning",
        "a cat on a sunny window sill",
        "a supermarket street from above",
        "a small boat on a calm river",
        "a train passing a country station",
        "a bakery window at dawn",
        "a house with a garden from above",
        "a farm with a red barn",
        "a beach with umbrellas in the morning",
        "a quiet library street",
        "an orchard path in spring",
    ],
    # level_test and say_it_level (STEP 58): the same notebook page as
    # how_do_you_say, so the same rule -- scenes of climbing and levels, read as
    # a margin. From content/drafts/topics/footage_level_family.json.
    "level_vocab": [
        "a mountain trail climbing to a summit",
        "stairs climbing a hillside town",
        "a summit view above the clouds",
        "a cable car rising up a mountain",
        "a hiker's path along a ridge",
        "a lighthouse at the end of a long pier",
        "a climbing wall on a sea cliff",
        "a winding road to a mountain pass",
        "a ladder of rice terraces at sunrise",
        "a staircase waterfall in a forest",
        "a summit flag in the wind",
        "hot air balloons at different heights",
        "a spiral road up a hill",
        "a rocket trail rising into the sky",
        "a sunrise seen from a peak",
        "a glacier trail with blue ice",
        "layers of hills at dawn",
        "a long bridge rising over a bay",
        "clouds rolling below a peak",
        "a mountain hut in the morning sun",
    ],
    "say_it": [
        "a café terrace on a quiet square",
        "a train station hall from above",
        "an airport window with planes",
        "a hotel pool at sunset",
        "a city taxi rank at night",
        "a market street with stalls",
        "a ferry terminal at dawn",
        "a pharmacy street on a rainy day",
        "an outdoor cinema in a park at night",
        "a museum courtyard in sunlight",
        "a seaside promenade with bikes",
        "a supermarket car park from above",
        "a cable car station in the mountains",
        "a harbour with small boats",
        "a busy crossing seen from above",
        "a bus moving through a historic city",
        "a hostel balcony over rooftops",
        "a campsite by a lake at dusk",
        "a gym by a window with a city view",
        "a picnic in a park from above",
    ],
}
#: STEP 77 §9: the true_false_level drafts' own category: scenes of choosing, two ways at once.
CATEGORY_FOOTAGE["quiz_facts"] = [
    "a fork in a forest path in autumn",
    "a coin spinning on a wooden table",
    "two doors in a sunlit corridor",
    "a rail switch moving on a branch line",
    "a traffic light changing at dusk",
    "a weather vane turning on a rooftop",
    "a compass on an old map",
    "a crossroads in open farmland",
    "a revolving door in a lobby",
    "a seesaw in an empty playground",
    "a lighthouse beam sweeping at night",
    "dominoes falling in a long line",
    "a chess board by a window",
    "a pair of dice rolling on felt",
    "a signpost on a mountain pass",
    "a mirror lake reflecting pines",
    "a split road through desert hills",
    "a tidal causeway at low tide",
    "a hedge maze from above",
    "a swing bridge opening on a canal",
]

#: The second axis. Stock video responds strongly to camera language, so
#: this changes the returned footage far more than its length suggests — an
#: "aerial view of a river" and a "close up of a river" are different films.
MOTION = [
    "aerial drone shot",
    "slow motion",
    "timelapse",
    "wide establishing shot",
    "slow aerial push in",
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


#: STEP 78 §0: a theme that names a place or an activity gets footage OF that place. Spanish
#: keyword (accents stripped, lower case) -> queries for the same Pexels source.
PLACE_FOOTAGE = {
    "restaurant": ["restaurant interior with diners", "waiter serving food at a restaurant table",
                   "restaurant kitchen pass with plates", "candle lit restaurant table",
                   "people ordering food in a restaurant", "restaurant terrace with tables"],
    "aeropuert": ["airport terminal with travellers", "airport departures board", "airplane taking off",
                  "passengers walking with suitcases in an airport", "airport check in desk", "airport window with planes"],
    "hotel": ["hotel lobby with reception desk", "hotel room with a made bed", "hotel corridor with doors",
              "hotel pool in the morning", "guest checking in at a hotel", "hotel breakfast buffet"],
    "medic": ["doctor's office with a desk", "doctor listening with a stethoscope", "hospital corridor",
              "pharmacy shelves with medicine", "waiting room in a clinic", "nurse at a hospital desk"],
    "farmacia": ["pharmacy shelves with medicine", "pharmacist at a counter", "medicine boxes on a shelf",
                 "pharmacy sign on a street", "pills on a table", "waiting room in a clinic"],
    "compra": ["shopping street with stores", "people shopping in a clothing store", "shopping bags in hand",
               "supermarket aisle with products", "cashier at a store checkout", "shop window display"],
    "tienda": ["shop window display", "people shopping in a clothing store", "small shop counter",
               "shopping street with stores", "cashier at a store checkout", "store shelves with products"],
    "supermercado": ["supermarket aisle with products", "shopping cart in a supermarket", "fresh fruit in a supermarket",
                     "supermarket checkout", "supermarket shelves", "people shopping for groceries"],
    "gimnasio": ["gym with exercise machines", "person lifting weights in a gym", "running on a treadmill",
                 "fitness class in a studio", "gym locker room", "stretching on a gym mat"],
    "cocina": ["home kitchen cooking", "chopping vegetables on a board", "pan frying on a stove",
               "kitchen counter with ingredients", "boiling pot on a stove", "baking in a home oven"],
    "taxi": ["taxi driving through a city", "yellow taxi at night", "hailing a taxi on a street",
             "taxi interior with driver", "taxi rank at a station", "city traffic with taxis"],
    "tren": ["train arriving at a platform", "train station hall", "passengers on a train",
             "metro train in a tunnel", "subway platform with commuters", "train window landscape"],
    "metro": ["subway platform with commuters", "metro train in a tunnel", "subway map on a wall",
              "people on an escalator in a metro station", "metro car interior", "train arriving at a platform"],
    "playa": ["beach with umbrellas", "waves on a sandy beach", "people walking on a beach",
              "beach bar by the sea", "seaside promenade", "beach towel and sunscreen"],
    "banco": ["bank teller counter", "atm cash machine", "bank interior", "counting money at a desk",
              "credit card payment", "bank building entrance"],
    "oficina": ["office desk with a laptop", "people in a meeting room", "open plan office",
                "typing on a keyboard at work", "coffee break in an office", "office window with a city view"],
    "trabajo": ["office desk with a laptop", "people in a meeting room", "open plan office",
                "typing on a keyboard at work", "coffee break in an office", "office window with a city view"],
    "escuela": ["classroom with desks", "teacher at a whiteboard", "students writing in notebooks",
                "school hallway with lockers", "school library", "backpack on a desk"],
    "clase": ["classroom with desks", "teacher at a whiteboard", "students writing in notebooks",
              "school library", "backpack on a desk", "school hallway with lockers"],
    "viaje": ["suitcase being packed", "traveller with a backpack at a station", "map and passport on a table",
              "airplane window view", "train window landscape", "tourist street in an old town"],
    "cafe": ["barista making coffee", "coffee shop counter", "cup of coffee on a cafe table",
             "people chatting in a cafe", "espresso machine pouring", "cafe window with rain"],
}

#: Grammar and abstract themes: one calm, consistent set, no random landscapes.
CALM_FOOTAGE = ["open notebook on a wooden desk", "cafe table with coffee and a notebook",
                "window with soft morning light", "pencil writing in a notebook",
                "desk with books and a lamp", "steam rising from a coffee cup",
                "pages of a book turning", "sunlight on a quiet study desk"]

#: Types whose script names no visual objects: their theme decides place or calm.
_LEVEL_TYPES = ("level_test", "say_it_level", "true_false_level", "fill_level", "choose_level", "phrases_level")


def _plain(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if unicodedata.category(c) != "Mn")


def place_queries(theme: str) -> List[str]:
    """The place footage a Spanish theme names, or [] (STEP 78 §0)."""
    import re
    words = re.findall(r"[a-z]+", _plain(theme))
    for key, queries in PLACE_FOOTAGE.items():
        if any(w.startswith(key) for w in words):            # «entrenar» is not «tren»
            return list(queries)
    return []


def footage_themes(script: Dict) -> List[str]:
    """Queries from the script's own theme, asked BEFORE (and for the level types, INSTEAD OF)
    the category's fallbacks.

    how_do_you_say names its objects in English (pillow, blanket, lamp…): those, then its place.
    The level types: the place their theme names (restaurante, aeropuerto…), else — grammar,
    phrasal verbs, abstract themes — the calm desk/notebook/café set. Enough queries to fill
    every clip slot, so no category landscape is mixed in (STEP 78 §0)."""
    script = script or {}
    vtype = script.get("type")
    place = place_queries(script.get("theme") or "")
    if vtype == "how_do_you_say":
        words = [str(it.get("english") or "").strip() for it in script.get("items") or []]
        return [f"{w} close up" for w in words if w][:THEME_QUERIES] + place
    if vtype in _LEVEL_TYPES:
        out = place or list(CALM_FOOTAGE)
        return (out + [q for q in CALM_FOOTAGE if q not in out])[:MAX_CLIPS]
    return []


#: At most this many object queries per how_do_you_say; its place and the category fill the rest.
THEME_QUERIES = 4


def build_queries(topic: str, category: str, count: int = 3, themes: List[str] = ()) -> List[str]:
    """`count` DISTINCT search queries for one video: the script's theme first (footage_themes),
    then the category's subjects.

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

    queries = list(dict.fromkeys(themes))[:count]
    for i in range(count - len(queries)):
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
                    key: str = None,
                    themes: List[str] = ()) -> Optional[Dict]:
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
    queries = build_queries(topic, category, count=want, themes=themes)
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

# Background standard — open places only

Replaces `CATEGORY_FOOTAGE` and `MOTION` in `src/topic_clips.py`.

---

## The rule

Every clip is an **open place seen wide, in natural daylight, with a horizon or
real depth**. Nothing else qualifies.

Refused, without exception:
- interiors of any kind — kitchens, offices, studios, lobbies, server rooms
- macro and close-up — a hand, a keyboard, a circuit board, a guitar string
- objects on a surface — blocks, an abacus, a mug, a notebook
- faces and people close enough to be looked at rather than seen
- night scenes, unless the sky is the subject

### Why it is a rule and not a preference

The topic is carried by the narration and the cards. Footage has one job:
hold the eye for fifty seconds without competing for it. A close-up of a
guitar string asks to be read. A valley does not — it is depth, movement and
light, and the text sits on top of it.

The measurement half of this stays as it is: the readability band already
solves per clip, and a fully bright frame needs only ~0.47 of the 0.75 it is
allowed. **Open and bright costs nothing in legibility.**

## The categories

The thematic link is a tint, not an illustration. `technology` gets wind farms
and satellite dishes, not a monitor.

```python
CATEGORY_FOOTAGE = {
    "business": [
        "aerial view of a city skyline at sunrise",
        "a harbour full of cargo ships from above",
        "motorway traffic flowing through open country",
        "a bridge spanning a wide river at dawn",
        "a container port seen from the air",
        "downtown towers above morning fog",
    ],
    "common_mistakes": [
        "waves erasing footprints on a wide beach",
        "a river carving a bend through open land",
        "shifting sand dunes under a clear sky",
        "a glacier edge breaking into the sea",
        "clouds reshaping over a mountain ridge",
        "tide filling a long empty estuary",
    ],
    "confusing_words": [
        "two roads dividing across open plains",
        "fog lifting off a wide pine valley",
        "a river fork seen from the air",
        "a signpost at a country crossroads",
        "twin peaks above a green valley",
        "a coastline splitting into two bays",
    ],
    "cultural": [
        "a temple courtyard at sunrise from above",
        "a hilltop village in afternoon light",
        "an open plaza with flags in the wind",
        "terraced rice fields in morning sun",
        "a wide festival crowd seen from a rooftop",
        "an ancient ruin on an open hillside",
    ],
    "everyday_expressions": [
        "a quiet street lined with trees in the wind",
        "a park in bright afternoon light",
        "a coastal path above the sea",
        "laundry lines across a sunlit alley from above",
        "a bicycle crossing a wide open square",
        "rain sweeping across open fields",
    ],
    "false_friends": [
        "mountains reflected in a still lake",
        "twin waterfalls in a green gorge",
        "a symmetrical coastline from the air",
        "clouds mirrored on a salt flat",
        "two rivers meeting in open country",
        "sunlight and shadow moving across dunes",
    ],
    "food_restaurant": [
        "rows of vines on a sunlit hillside",
        "an orchard in full bloom from above",
        "an open air market square in daylight",
        "fishing boats returning to a bright harbour",
        "wheat fields moving in the wind",
        "terraced farmland at golden hour",
    ],
    "grammar": [
        "a viaduct crossing a wide green valley",
        "terraced fields in geometric rows",
        "a long bridge over open water",
        "a lighthouse on an exposed headland",
        "planted forest rows seen from the air",
        "a canal running straight through farmland",
    ],
    "idioms": [
        "a storm cloud rolling over open fields",
        "ice cracking across a frozen lake",
        "birds scattering above an empty plain",
        "sunlight breaking through after rain",
        "a lone tree on a windswept hill",
        "waves hitting cliffs in heavy weather",
    ],
    "kids_animals": [
        "horses running across a green field",
        "ducklings swimming on an open pond",
        "a flock of birds over a wide meadow",
        "deer crossing a sunlit clearing",
        "dolphins moving through open sea",
        "sheep grazing on rolling hills",
    ],
    "kids_colors": [
        "a field of bright wildflowers in the wind",
        "hot air balloons rising over a valley",
        "an autumn forest from above",
        "a rainbow over open countryside",
        "tulip fields in rows at sunrise",
        "a turquoise lagoon seen from the air",
    ],
    "kids_numbers": [
        "birds landing one by one on open wires",
        "rows of trees passing in an aerial shot",
        "ripples spreading across a wide lake",
        "dunes repeating to the horizon",
        "waves arriving on a long empty beach",
        "cloud shadows crossing open farmland",
    ],
    "phrasal_verbs": [
        "a road winding up an open mountainside",
        "a river running through a wide canyon",
        "a trail climbing above the treeline",
        "a train crossing an open plain",
        "a paraglider rising over green hills",
        "a boat leaving a harbour into open sea",
    ],
    "pronunciation": [
        "wind moving across tall grass",
        "waves breaking along an open shore",
        "a wide canyon in afternoon light",
        "ripples spreading across still water",
        "clouds racing over an open ridge",
        "a valley opening below a mountain pass",
    ],
    "slang": [
        "a skatepark under open sky in daylight",
        "a rooftop view over a bright city",
        "an outdoor basketball court from above",
        "a wide beach boardwalk in summer",
        "city streets from a high vantage point",
        "a coastal highway in afternoon sun",
    ],
    "social": [
        "a crowded beach seen from above in summer",
        "an outdoor festival field in daylight",
        "people crossing a wide sunlit plaza",
        "a picnic meadow under open sky",
        "a lakeside gathering in golden hour",
        "a coastal town seen from the water",
    ],
    "spanish_specific": [
        "olive groves moving in the wind",
        "a Mediterranean cliff above clear water",
        "a wide Andalusian plaza at golden hour",
        "sunflower fields to the horizon",
        "a whitewashed hill town in bright sun",
        "a coastal road above the Mediterranean",
    ],
    "technology": [
        "wind turbines turning on open hills",
        "a solar farm seen from the air",
        "a satellite dish array in a desert",
        "power lines crossing wide open land",
        "a drone rising above a green valley",
        "a modern bridge over open water at dawn",
    ],
    "travel": [
        "an airplane flying over a wide river",
        "a kayak paddling across open sea",
        "a train winding through mountains",
        "waves breaking on a tropical beach",
        "a hot air balloon rising over a valley",
        "a road trip through desert canyons",
    ],
    "work_office": [
        "a city skyline at first light from above",
        "a long bridge full of morning traffic",
        "a river running through a bright city",
        "commuter trains crossing open ground",
        "a business district seen from a hilltop",
        "sunrise over a wide urban horizon",
    ],
}
```

`travel` is unchanged — it was already the standard.

## The motion axis

```python
MOTION = [
    "aerial drone shot",
    "slow motion",
    "timelapse",
    "wide establishing shot",
    "slow aerial push in",
]
```

Two removed and two added:

- **`cinematic close up` — out.** It is the opposite of the rule. Six of the
  twenty categories were pairing it with an already-close subject.
- **`handheld tracking shot` — out.** Camera shake behind fixed text reads as
  a rendering fault, not as style.
- `wide establishing shot` and `slow aerial push in` are the two phrasings
  that reliably return open landscape footage on Pexels.

The query space stays the same size: 20 categories × 6 themes × 5 motions =
600.

## The part that makes it a standard instead of a wish

**Nothing measures the clip today.** `fetch_query` takes the first Pexels
result that passes the size and duration checks, and that is the whole of the
selection. A better query table raises the odds; it does not decide anything.

Two gates at fetch time, both free, both on footage already downloaded:

1. **Motion window.** Measured over the 20 clips on disk, mean inter-frame
   difference ranges from **2.7 to 66.9** — a 25× spread with no floor and no
   ceiling. The ones near 3 read as a still photograph, which is the "flat
   background" complaint in one number. The ones near 67 compete with the text.
2. **Daylight floor.** 2 of those 20 sit at p95 luminance below 0.20 — the band
   never even activates on them because they are already dark. Under this
   standard they should not have been kept.

Both need a threshold chosen from a measured sample, not from taste. That is a
separate step and it is where I would go next.

## Out of scope

The readability band, its zone and its floor. Measured separately: the footage
is already bright (median p95 0.797) and the band never approaches its cap.
Brightness is not what is missing — open space is.

# Proposed background categories — awaiting approval

Nothing here has been generated. These are the prompts I would send, for
review first. Approve the list (or strike individual prompts) and generation
becomes mechanical: paste each block into `BACKGROUND_PROMPTS` in
`src/generate_backgrounds.py`, add a matching `photo_<category>` preset, run
the generator.

**Blocker before any of it runs:** `dall-e-3` was removed from the OpenAI API
on 2026-05-12. `src/generate_backgrounds.py` still names it and now refuses to
start rather than failing on a 404. Choosing the replacement is a spend
decision, so it is not made here — see [Cost](#cost).

---

## Why these six

The eight categories that exist — earth, city, ocean, nature, abstract,
clouds, sunset, galaxy — are generic cinematic wallpaper. None of them has
anything to do with what the videos are about. Meanwhile `content/topics/`
holds twenty topic files: business, work_office, technology, travel,
food_restaurant, cultural, spanish_specific, grammar, pronunciation,
confusing_words, false_friends, common_mistakes, idioms, slang, social,
everyday_expressions, phrasal_verbs, and three kids files.

Each proposal below maps to topics that actually get made, so a business video
can sit on something that reads as work rather than on a nebula.

| category | serves |
|---|---|
| `workspace` | business, work_office, technology |
| `travel_transit` | travel |
| `food_table` | food_restaurant, everyday_expressions |
| `latin_streets` | cultural, spanish_specific |
| `study_desk` | grammar, pronunciation, confusing_words, false_friends, common_mistakes |
| `rain_window` | social, idioms, slang, phrasal_verbs |

`latin_streets` is the one that exists for the audience rather than the topic:
the channel teaches English to Spanish speakers, and none of the current forty
images looks like anywhere they live.

No kids category is proposed — the kids profile uses clip backgrounds
(`background_mode: clips`, `assets/clips/kids`), so photos would not be used.

## Every prompt states where the dark band goes

The existing prompts ask only for "dark enough for white/yellow text
readability", and measurement says they did not get it. Contrast between the
headline and the background underneath it, WCAG ratio, for the eleven presets
currently enabled:

    photo_sunset  2.08     photo_clouds  2.65     photo_galaxy  2.69
    photo_city    3.27     photo_ocean_vibrant 3.46   photo_ocean 3.69

Large text wants 3.0 or better. Six of the eleven are at or under 3.7, because
a sunset or a cloudscape puts its brightest region across the middle of the
frame, which is exactly where the headline sits. Every prompt below therefore
pins the exposure explicitly: **brightness in the top and bottom thirds, deep
shadow across the horizontal middle band.** That is a compositional
instruction, not a preference, and it is the one thing worth checking when the
images come back.

Full table: `_audit/backgrounds/metrics.md` (regenerate with
`python3 tools/background_contact_sheet.py`).

---

## `workspace`

```
A modern desk at night lit only by a laptop screen, the glow falling on a
notebook and a coffee cup, the rest of the room in deep shadow, warm amber
desk lamp far in the background, the centre of the frame in near darkness,
brightness only at the top and bottom edges, cinematic photography, portrait
orientation, shallow depth of field, no people, no text, no readable screens
```

```
Empty modern office at night seen from inside, floor-to-ceiling windows
showing a distant city skyline of small cold lights, the room itself unlit and
dark, reflections on a polished dark floor, the middle of the frame in shadow,
moody architectural photography, portrait orientation, no people, no text
```

```
Overhead view of a dark wooden desk with a closed laptop, a pen and a folded
pair of glasses arranged on it, single soft light from the upper left, most of
the surface falling into deep shadow, rich dark tones, flat lay product
photography, portrait orientation, no text, no logos
```

```
Server room corridor in darkness, thin rows of blue and green indicator lights
receding into the distance, cold blue rim light on dark metal cabinets, the
centre of the corridor unlit, cinematic technology photography, portrait
orientation, moody, no people, no text
```

```
Dark conference room after hours, a long table catching a narrow band of light
from a window blind, the rest of the room in heavy shadow, dust visible in the
light beam, cold blue tones with one warm accent, cinematic photography,
portrait orientation, no people, no text
```

## `travel_transit`

```
Airport terminal window at night, a parked airplane silhouetted against dark
tarmac, runway lights as small points of colour, the glass reflecting the dark
interior, the middle of the frame deliberately dark, cinematic travel
photography, portrait orientation, no people, no text, no readable signage
```

```
View along an airplane wing at high altitude just after sunset, deep blue and
indigo sky above, dark cloud layer far below, a single navigation light glowing
red on the wingtip, the centre of the frame in deep blue shadow, cinematic
aerial photography, portrait orientation, no text
```

```
Empty train platform at night, curved rails catching thin reflections, a
distant tunnel mouth, overhead lamps pooling small circles of warm light,
the middle distance dark and empty, moody documentary photography, portrait
orientation, no people, no text, no readable signage
```

```
Open road at night photographed from a low angle, headlight trails as long
streaks of warm light along the edges, the centre of the road dark, a
silhouetted mountain ridge against a deep blue sky, long exposure photography,
portrait orientation, no text
```

```
Weathered leather suitcase and a rolled paper map on a dark wooden floor, a
single warm light from above, heavy shadow filling most of the frame, vintage
travel still life, portrait orientation, no text, no readable map labels
```

## `food_table`

```
Dark restaurant table from above, a single espresso cup and saucer on aged
wood, one shaft of warm light falling across the corner, the rest of the
surface in deep shadow, moody food photography, portrait orientation, rich
brown and amber tones, no people, no text
```

```
Café interior at night seen from a corner table, warm pendant lights glowing
small and distant, the foreground in near darkness, soft bokeh from the
window, cinematic atmosphere, portrait orientation, no people, no text, no
readable menus
```

```
Overhead view of a rustic dark stone kitchen surface with scattered whole
spices, dried chillies and a bowl, dramatic side lighting from the top of the
frame, the middle falling into shadow, rich saturated warm colour, editorial
food photography, portrait orientation, no text
```

```
Night market stall lit by a single warm bulb, baskets of produce in
silhouette, steam rising through the light, everything beyond the bulb in
darkness, the centre of the frame dark, atmospheric street photography,
portrait orientation, no people, no text, no readable signs
```

```
Dark ceramic plates and folded linen stacked on a shadowed table, a narrow
band of cool window light across the top of the frame, minimal and quiet,
fine art still life photography, portrait orientation, muted dark tones, no
text
```

## `latin_streets`

```
Narrow colonial street in a Latin American old town at dusk, pastel facades in
faded ochre and blue, wrought iron balconies, warm lamps just coming on, the
street itself in deep shadow, cobblestones catching thin reflections,
cinematic travel photography, portrait orientation, no people, no text, no
readable signs
```

```
Mexico City rooftop view at blue hour, dense low buildings with warm scattered
window lights, distant volcanic silhouette on the horizon, deep indigo sky
above, the middle of the frame dark, cinematic urban photography, portrait
orientation, no text
```

```
Cartagena-style courtyard at night, whitewashed arches in shadow, bougainvillea
spilling over a wall, a single warm lantern in the corner, the centre of the
courtyard unlit, moody architectural photography, portrait orientation, no
people, no text
```

```
Barcelona alley at night after rain, tall narrow buildings on both sides, wet
stone reflecting a few warm windows high above, laundry lines in silhouette,
the alley floor dark, cinematic street photography, portrait orientation, no
people, no text, no readable signs
```

```
Andean hillside town at night seen from across a valley, scattered warm house
lights climbing the dark slope, a deep starry sky above, the middle of the
frame in shadow, long exposure landscape photography, portrait orientation,
no text
```

## `study_desk`

```
Old library aisle at night, tall dark wooden shelves packed with books
receding into shadow, a single warm reading lamp at the far end, the middle of
the aisle unlit, dust in the air, cinematic photography, portrait orientation,
no people, no text, no readable spines
```

```
Open book on a dark desk lit by one warm lamp from the upper left, pages
softly out of focus, the rest of the frame falling into deep shadow, shallow
depth of field, intimate study photography, portrait orientation, no readable
text on the pages
```

```
Dark green chalkboard texture filling the frame, faint chalk dust and old
eraser marks, uneven light falling from the top edge, the centre darker and
softly vignetted, abstract surface photography, portrait orientation,
completely blank, no writing, no text, no symbols
```

```
Stack of worn hardcover books on a shadowed table, warm side light raking
across the cloth spines, deep black background behind, the middle of the frame
in shadow, rich dark still life photography, portrait orientation, no readable
titles, no text
```

```
Fountain pen and folded reading glasses on dark textured paper, single soft
light from above, heavy shadow across most of the surface, macro still life
photography, portrait orientation, muted warm tones, no text, no writing
```

## `rain_window`

```
Rain running down a dark window at night, city lights beyond thrown far out of
focus into soft coloured bokeh, the glass surface sharp, the centre of the
frame dominated by dark wet glass, cinematic photography, portrait
orientation, cool blue tones with warm accents, no text
```

```
Wet city street at night from a low angle, neon reflections stretched across
dark asphalt, rain falling through the light, the middle of the frame in deep
shadow, moody cinematic photography, portrait orientation, no people, no
text, no readable signs
```

```
Storm seen through a dark doorway, heavy rain lit from behind, the doorway
frame in near black silhouette on both sides, dramatic contrast, cinematic
photography, portrait orientation, no people, no text
```

```
Close-up of raindrops on a dark car window at night, streetlights as small
soft orbs beyond the glass, the majority of the frame deep blue-black,
shallow depth of field, atmospheric macro photography, portrait orientation,
no text
```

```
Foggy street at night lit by a single streetlamp, thick mist swallowing the
background, wet pavement reflecting a narrow pool of warm light, everything
outside that pool dark, cinematic noir photography, portrait orientation, no
people, no text
```

---

## Cost

Thirty images: six categories, five prompts each. One-time asset spend.
**It is not charged per video** — rendering re-reads whatever PNGs are on
disk and pays nothing to do it. Generate once, use forever.

Per-image prices at portrait 1024x1536, from the image generation guide:

| model | low | medium | high |
|---|---:|---:|---:|
| gpt-image-2 | $0.005 | $0.041 | $0.165 |
| gpt-image-1 | $0.016 | $0.063 | $0.250 |

Thirty images therefore costs:

| model / quality | 30 images |
|---|---:|
| gpt-image-2 low | **$0.15** |
| gpt-image-2 medium | **$1.23** |
| gpt-image-2 high | **$4.95** |
| gpt-image-1 high | **$7.50** |

One caveat on those figures: a second source quotes gpt-image-2 portrait at
$0.013 / $0.05 / $0.20 rather than $0.005 / $0.041 / $0.165. Budget against
the higher column and the worst case for 30 high-quality images is **$6.00**.
Confirm against the live calculator before a large run.

Recommended: **gpt-image-2 at medium, $1.23**, then inspect the contact sheet
and re-roll only the images whose dark band did not land. High quality buys
detail that a background sitting behind a headline at 35% overlay opacity
mostly throws away.

For reference, the forty images already on disk were `dall-e-3` at hd
1024x1792, which was **$0.120** each — about **$4.80** for the set. Both this
repo's estimate and `cost_tracker.py` record $0.080 for them, which was the
*standard* quality price at that size; the code asked for hd. No DALL-E entry
was ever actually logged: the images were generated 2026-03-09 and the cost
tracker landed 2026-03-11.

Migration will also need `PRICING` entries in `src/cost_tracker.py` for
whichever gpt-image model is chosen — `log_dalle` currently hardcodes
DALL-E keys.

## What 30 more images does and does not buy

Selection is uniform random over enabled presets with no memory of what came
before, so first repeat follows the birthday problem — it grows with the
square root of the library, which makes buying variety by the image expensive:

| distinct images | expected first repeat | at 2/day |
|---:|---:|---:|
| 40 (today) | ~8 videos | ~4 days |
| 70 (after these six) | ~10 videos | ~5 days |
| 200 | ~18 videos | ~9 days |
| 573 | ~30 videos | ~15 days |
| 2292 | ~60 videos | ~30 days |

So the six new categories move first repeat from about video 8 to about video
10. Reaching a month without a repeat means roughly 2300 images — about $94 at
gpt-image-2 medium, and 6.3 GB on disk at the current 2.8 MB average.

Two cheaper levers exist, and both are out of scope here, noted so the
comparison is honest:

1. **The 43 procedural presets already defined and switched off.** Zero
   marginal cost, no disk, and measurably better text contrast than the photo
   set (4.95:1 to 14.97:1, against 2.08:1 to 9.30:1). That is what the contact
   sheet from Task 1 is for.
2. **Giving selection a memory** — refusing the last N choices — which raises
   perceived variety without adding a single asset.

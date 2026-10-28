# Skipped scripts

Queued scripts whose topic already has a video. The queue guard blocked them as ALREADY PRODUCED
(one video per topic), so they could never be rendered from the queue. Claude's decision in STEP 78b
§2: move them here instead of deleting them. The guard and the panel do not read this folder.

| file | queued as | topic already produced |
|---|---|---|
| `bv001_familia.json` | how_do_you_say | basic_vocab/bv001 |
| `lv001_cocina.json` | level_test | level_vocab/lv001 |
| `sy001_restaurante.json` | say_it_level | say_it/sy001 |
| `sy002_cafeteria.json` | say_it_level | say_it/sy002 |
| `cm016_information.json` | true_false | common_mistakes/cm016 |
| `cu001_saludos.json` | vocabulary | cultural/cu001 |

The STEP 78 report counted 7: the seventh, a second how_do_you_say script, was rendered by the panel
between the two STEPs and is in `_done/`.

To bring one back, give it a topic that has no video yet (a new `topic_id`), then move it to
`content/queue/<type>/`; the guard will check it again.

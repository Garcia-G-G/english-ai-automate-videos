# STEP 77 §9 — the 156 level scripts, queued; one proof per new type

`python3 tools/level_migrate.py --copy choose_level fill_level true_false_level phrases_level`
derives `full_script`, `english_phrases` and `translations` exactly as the audio speaks them
(intro, tier lines, each answer, verdict, outro — `derive`, the function the earlier queues
used), rewords nothing (tested field by field), validates every script (validate_script,
length_spec with the §4 page layout) before writing any, and leaves the drafts in place.

| type | queued | skipped |
|---|---|---|
| choose_level | 39 (ec002–ec040) | ec001: already produced |
| fill_level | 39 (fc002–fc040) | fc001: already produced |
| true_false_level | 39 (tf002–tf040) | tf001: already produced |
| phrases_level | 39 (vf002–vf040) | vf001: already produced |

The 001s are in the topic history (one video each), so the guard would refuse them.

Two things the addendum did not foresee, both needed for the panel to hand these scripts out:
- Their topics were not in `content/topics/` (the queue guard refuses a topic nobody can draw):
  156 entries appended (grammar 78, quiz_facts 38, everyday_expressions 39, false_friends 1),
  as text, without reformatting the files.
- 38 true_false_level drafts use a new category, `quiz_facts`. Kept (it is Garcia's metadata),
  with its own topic file, 20 footage subjects (no subject shared with another category) and
  4 image scenes, as every category must have.

The queue guard reports no problem on any of the 156.

## Proof renders (through the panel's own job function; Claude reviews them)

| type | Short | TTS $ | frames+encode s | LUFS | TP | duration (with outro) |
|---|---|---|---|---|---|---|
| choose_level | elige_la_correcta_20261022_020511 (ec002) | 0.146 | 61.7 | −14.2 | −2.3 | 78.66 |
| fill_level | completa_la_frase_20261022_020722 (fc002) | 0.142 | 63.9 | −14.1 | −2.3 | 77.86 |
| true_false_level | verdadero_o_falso_20261022_020921 (tf002) | 0.117 | 81.5 | −14.2 | −2.5 | 84.52 |
| phrases_level | cómo_se_dice_20261022_021147 (vf002) | 0.077 | 53.7 | −14.2 | −2.3 | 55.62 |

Total TTS **$0.482** (≤ $0.30 each, ≤ $1.20 overall). All BT.709, keyframe every 2 s, gate PASS,
outro appended. Videos: `output/pending/<type>/` (the review queue) and copies in
`_audit/stills/STEP77/s9/<type>.mp4`; stills `s9/<type>_0..4.png`, `s9/<type>_sheet.png`
(gitignored).

Review: wrapped sentences at 42 px; pages split 7+3 or 6+4 at a tier, 5+5 for phrases_level;
the pencil writes in the blank / circles the option / points (true_false) and stands in the
margin while the viewer thinks; true_false's blurred «VERDADERO · FALSO» comes into focus;
phrases_level's grey bar gives way to the English; verdict note, then the CTA over the title.

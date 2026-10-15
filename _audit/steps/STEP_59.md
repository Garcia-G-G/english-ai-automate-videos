# STEP 59 — Clean up after STEP 58 while the owner reviews lv001 and sy001

The owner is watching the first two level Shorts by eye and ear (lv001 cocina, sy001
restaurante). `pronounce_level` waits for that verdict. Do not start it. This step is
the cleanup that does not depend on the verdict.

## 1. Push

`01594b5` is committed on `6a-layout` and not pushed (the VM has no GitHub credentials).
It is content only:
- 49 say_it_level lines that overflowed the 620 px column at 34 px are rewritten
  shorter, in 34 scripts;
- 32 intros no longer say «te digo la frase en español»;
- bv027 «Control remoto» and bv029 «Protector solar» are replaced by «Sillón» and
  «Bloqueador».

The derived fields were re-derived with `tools/level_migrate.py --rederive`.
`queue_guard` reports 0 problems on all 102 files, and the content tests pass, including
`test_every_queued_word_fits_its_column`. Push it, together with this STEP's own commits.

Regenerate `_audit/STEP58_length_report.md`. Expected result: 0 texts that do not fit,
for both types. If anything is still over, list it and I fix it.

## 2. Onset gate: keep the cleanest take, and calibrate it for eleven_v3

In lv001 the gate asked again 11 times, and 7 of 10 single English words came back
"dirty". After two re-asks it keeps the **last** take.

1. Keep the **cleanest** take: the lowest `e[0] - e.max()`, with no fragment and no
   doubled onset, never just the last one.
2. Check whether the gate is wrong on eleven_v3. Take lv001's English clips (every take,
   kept or not). For each one, log the three gate values: start-to-peak dB, fragment,
   doubled_onset. If the clips the gate calls dirty only fail the -30 dB rule and have
   no fragment or doubled onset, the threshold is miscalibrated for v3. In that case, make
   the threshold a per-model value, measured on these clips, and say what number you chose
   and why.
3. Ask again at most twice, as now. Report re-asks per video and their cost.

The owner's ear is the ground truth. If he hears a stutter in lv001, his note on which
word beats any number.

## 3. The 3.4 s dead_air in how_do_you_say (bv004): fix it

You found the cause: two pauses of about 1.7 s between the two takes, in en_2 and en_5.
The fix is in `src/tts_common.py`, and **you are authorized to change it in this step**:

- `clamp_take_gap` uses the **longest** internal pause as the gap between takes, not the
  first one. A 0.08 s micro-stop inside «black» must not be taken as the gap.
- When the cut fails, log ffmpeg's stderr, so «cut failed» says why.
- Add a regression test with a synthetic clip shaped like en_5: word, 0.08 s dip, word,
  1.7 s pause, word. The gap must come out ≤ the clamp.
- how_do_you_say audio of existing renders does not change. Only new generations do.

## 4. Readability numbers for the owner (measure, change nothing)

After the content fix, say_it_level pages render at these sizes (one size per column):

| size | 34 | 36 | 38 | 40 | 42 | 44 | 46 px |
|---|---|---|---|---|---|---|---|
| pages | 15 | 32 | 26 | 11 | 7 | 3 | 6 |

level_test renders all 100 pages at 46 px. Do not change the layout. The owner decides
after seeing sy001 on his phone. Two options are ready if he asks:
- (a) widen the text column to the left only, by moving the number and tier pill inward;
  the right edge stays clear of the Shorts buttons;
- (b) I shorten more lines.

## 5. One check on the pin

`test_how_do_you_say_renders_byte_identically` fails on my Linux VM (different
PIL/FreeType) with the current working tree. Run it on the Mac with the tree as it is.
The other session has uncommitted changes in `src/video/utils.py`. If the test fails
there too, say which change breaks it. Do not touch that file.

## Constraints

Only OpenAI and ElevenLabs are paid. Everything else is local and free. No MoviePy.
The ceiling is $0.30 per Short. No keys, `.env`, voice IDs or home paths in commits.
Commit messages carry no attribution lines. Do not commit the other session's
uncommitted files.

## Report back

- Push confirmation.
- The new length report: totals.
- For the onset gate: a table of the lv001 takes with the three values and the verdict
  of each, the threshold you chose and why, and re-asks plus cost before and after.
- For dead_air: the test, plus one fresh how_do_you_say render (bv004 colores) with QA
  PASS and no dead_air, with its duration and cost.
- The result of the pin test on the Mac.
- Test counts: pass / fail, naming any failure that is not yours.

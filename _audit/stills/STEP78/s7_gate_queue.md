# STEP 78 §7 — quality gate and queue

`src/video/series/gate.py`, on a rendered Short:
- duration 25–60 s (outro included); −14 LUFS ± 1 and true peak (loudness.gate);
- every `[[English]]` phrase heard in the local whisper transcript ($0), near its beat: its words
  in order, in a run of consecutive words (one miss allowed per four) — counting loose words let
  «I am cold» pass on the «I» and «cold» of the neighbouring options;
- frame 0 shows `hook_text` (its box against the same frame drawn without it);
- every readable box of the style, and the outro answer, inside the safe areas.

The four proofs: all PASS (hc_m001, hc_e011, hc_p019, hc_c001; every English phrase heard).

Queue: `series.queue_drafts()` copied the 108 validated drafts into
`content/queue/hecho_con_claude/`, the drafts kept.

| style | principiante | medio | difícil |
|---|---|---|---|
| mensajes | 9 | 9 | 9 |
| escena | 9 | 9 | 9 |
| poster | 9 | 9 | 9 |
| comic | 9 | 9 | 9 |

The panel's «Hecho con Claude» button now starts a job (`series.render_one`): pick by the filters,
render, gate; PASS → `output/pending/hecho_con_claude/` with its sidecar (title, caption as the
description, the 5 hashtags, the gate, the spend) and the script to `_done`; REJECT →
`output/rejected/hecho_con_claude/`, the script stays queued. The main queue guard leaves the series'
folder to the series (it has its own schema and picker).

Noted, not changed: the main guard reports 34 problems that predate this STEP — 11 true_false
duration, 2 educational lengths, and 7 queued scripts whose topic is already produced (2
how_do_you_say, 2 say_it_level, 1 level_test, 1 true_false, 1 vocabulary).

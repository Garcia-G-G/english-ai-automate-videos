# 6b — text grouping: closed, and why

**Status: closed 2026-08-17.** One commit landed (`4cb264c`). The second,
which would have addressed one-word cards, was measured and deliberately not
written. This document exists so nobody reopens it from the frame alone.

The frame that opened 6b was real:

```
'presentation o You have demonstrated remarkable skill.'
```

A stray Spanish `o` leading a group, and an English quotation cut in half.
That defect is fixed. What follows is the part that looked like a defect and
was not.

---

## What landed

`video/__init__.py` rebuilt `is_english` from `english_phrases` and skipped
any phrase longer than three words. That filter was added 2026-03-24
(`de81e7f`) as defence against a scraper that was filing Spanish as English;
the scraper was fixed at its root 2026-07-30 (`d14a28b`) and the filter was
never revisited.

Measured over 45 educational fixtures, it discarded **73%** of Whisper's
English flags (1557 → 416), which meant `subtitle_processor`'s English branch
— the code that keeps an English run whole and prefixes a Spanish word or two
onto it — never ran. Removing it took every group that cuts through a
language change to zero:

| | straddles | ES→EN prefix (intended) | EN→ES tail | 2+ transitions |
|---|---|---|---|---|
| before | 310 | 165 (53%) | 43 | 102 |
| after | 314 | **314 (100%)** | **0** | **0** |

`max_words_per_group` was re-measured rather than inherited, since it moved
4 → 8 in the same commit for the same reason. It stays at 8: bad straddles are
zero at 8, 6 and 4, and 4 pushes trailing orphans from 13.5% to 19.0%.

---

## What did not land, and why

### The leading orphan

255 groups still begin with a 1–2 character word. The obvious rule — never
start a group with one, pull it back to the previous group — was simulated
before being written:

| variant | leading orphan | trailing orphan | groups cutting a language change |
|---|---|---|---|
| none | 255 (23.0%) | 150 (13.5%) | **0** |
| pull back, unguarded | 137 (12.4%) | **277 (25.0%)** | **79** |
| pull back, guarded | 142 (12.8%) | 273 (24.6%) | **76** |

It does not remove orphans, it **relocates** them — from the head of one group
to the tail of the previous one — and it reintroduces 76–79 of the exact
straddles the commit above had just eliminated, because pulling a Spanish
connector onto the end of an English group *is* an EN→ES tail.

The `max_words` interaction that was expected to be the cost turned out to be
negligible, and the cause decomposition says why:

| cause of a leading orphan | count |
|---|---|
| English prefix — the branch put it there on purpose | 127 (50%) |
| other | 45 (18%) |
| after a segment boundary | 41 (16%) |
| after sentence punctuation | 33 (13%) |
| after a >0.35s pause | 5 (2%) |
| **previous group hit `max_words`** | **1 (0%)** |

Half are deliberate. Another 29% sit after a hard boundary and cannot be
pulled back without merging across a sentence — the one thing grouping already
gets right (0 straddles in ~1100 groups). And the remaining 45 are not defects
on inspection: `'actually'` → `'no significa actualmente'`, `'así que
currently'` → `'es lo que buscas'` are correct Spanish clause openers after an
isolated English phrase.

### The one-word card

This looked like the stronger defect — 152 groups (13.7%) holding a single
word for a median 0.44s — and both numbers were measured at the wrong stage.
`group_words` output is not what the renderer draws.
`timing_engine.compute_display_windows` runs afterward and already merges
short groups:

```
one-word groups BEFORE timing_engine : 152
one-word groups AFTER  timing_engine :  25   (merge absorbed 127)
```

The real rate is **2.9%**, and the real on-screen time is a median **1.00s**,
not 0.44s — 0.44s was the audio span, not the display window.

The merge also settles the population question. Every phonetic/notation
fragment — `-ED`, `-T`, `/d/.`, `/t/.`, `wan-tid.` — is absorbed before it can
become a card. The 25 survivors are all ordinary words.

**Two framings were considered, and both were rejected on measurement.**

**Duration framing.** A minimum on-screen time already exists:
`timing_engine.MIN_HOLD = 1.2s`, plus `TAIL_PAD = 0.35s` after the last word
and `_merge_short_groups`. It is overridden in one place, `timing_engine.py:169`:

```python
elif t_out > next_in:
    # Timestamps overlap — windows may not. Clamp.
    t_out = next_in
```

Letting the floor win against that clamp costs audio sync on essentially
every card it would extend:

| floor | cards short | extra needed (median) | **would overlap the next group speaking** |
|---|---|---|---|
| 0.8s | 5 / 849 | 0.22s | **5 of 5** |
| 1.0s | 15 / 849 | 0.18s | **14 of 15** |
| 1.2s | 65 / 849 | 0.15s | **60 of 65** |

There is no silence to extend into. These cards are short *precisely because*
their successor arrives immediately, so every second bought is a second of
text held over different words — the R1 desync inverted.

**Grouping framing.** It targets a population `timing_engine` already merges
away: 127 of the 152, including all the notation. What remains is 2.9% of
cards, all ordinary words, none under 0.56s.

---

## If you are reopening this

Bring a frame from a **rendered video**, not from `group_words` output, and
check its `display_start`/`display_end` rather than its audio span. Both of
the numbers that made this look urgent came from reading the wrong stage.

Measurement scripts are in `_audit/layout/`: `measure_grouping.py`,
`measure_grouping_counterfactual.py`, `measure_max_words.py`,
`measure_orphan_rule.py`, `measure_one_word_groups.py`.

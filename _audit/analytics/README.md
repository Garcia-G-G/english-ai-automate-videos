# Shorts analytics

`shorts_2026-10-16.csv`: lifetime figures read from YouTube Studio on 2026-10-16 (per-video Overview and
Reach tabs). `stayed_to_watch_pct` is Studio's «Se quedaron para mirar», the share of feed viewers who did
not swipe away. NA means Studio has no figure yet: it needs about 48 h and some volume.

Median by type (n with data):

| type | n | views | stayed % | avg view | search % |
|---|---|---|---|---|---|
| how_do_you_say | 6 | 1200 | 42.5 | 31 s | 9.0 |
| quiz | 12 | 122 | 31.1 | 21 s | 2.5 |
| vocabulary | 8 | 316 | 29.9 | 31 s | 2.9 |
| fill_blank | 6 | 272 | 27.5 | 20 s | 2.7 |
| pronunciation | 4 | 123 | 21.4 | 28 s | 2.4 |
| true_false | 9 | 150 | 18.1 | 15 s | 1.3 |
| educational | 6 | 201 | 11.2 | 17 s | 1.5 |

The two educational Shorts near 1K views (UupvOngc_S0, lR9-Jq7Ikl4) kept under 10% of viewers. YouTube showed them
widely at first and almost everyone swiped. Views alone mislead; stayed % is the number to compare.
Re-measure the level types after 2026-10-18, when Studio has their stayed %.

## 2026-10-18 — the level types, first read (`shorts_2026-10-18.csv`)

Read in Studio (overview tab, since publication) on 2026-10-18 17:00 UTC. Shorts uploaded on the 17th and 18th
have no retention yet (Studio needs ~48 h); only their views are known.

| type | n | stayed % (each) | median | avg view / length | search % |
|---|---|---|---|---|---|
| level_test | 2 | 39.2, 32.6 | 35.9 | 1:14 / 1:04 (116 %), 0:54 / 1:11 (76 %) | 8.8, 9.2 |
| say_it_level | 3 | 42.2, 39.1, 34.8 | 39.1 | 63–73 % | 4.5, 1.8, 6.6 |
| how_do_you_say (new) | 3 | 44.5, 40.3, 39.0 | 40.3 | 44–73 % | 2.7–5.4 |
| level types together | 5 | | **39.1** | | |

- The level types keep viewers almost as well as how_do_you_say (39.1 vs 40.3 now, 42.5 on the 16th) and far
  better than the old quiz (31.1) or true_false (18.1).
- They get fewer views (283–602 vs 778–1,009). The two weakest titles have no topic in them («¿Hasta qué número
  llegas? Vocabulario», «Dilo en inglés: 10 frases»). The level_test ROPA with the topic in caps
  («¿Sabes estas 10 palabras de ROPA en inglés?», 17 Oct) already has 876 views in about a day, level with the
  how_do_you_say uploaded the same day (COCINA 855, FRUTA 966).
- The shortest level video (CUERPO, 1:04) is the only one watched past its length (116 %, people replay it).
  The 71–81 s ones are watched 63–76 % through. n is small: treat as a lead, not a rule.
- true_false_level: none uploaded yet.

Re-measure ROPA (xy_32J75eIw) and the 18 Oct uploads after 2026-10-20.

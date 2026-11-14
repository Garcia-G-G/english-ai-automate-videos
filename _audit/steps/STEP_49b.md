# STEP 49b — Addendum: background footage for the three level categories

`src/topic_clips.py` raises `UnknownCategory` for a category with no footage table, and
`tests/test_topic_clips.py` requires the table's keys to equal `content/topics/`. So in
the same commit that moves `content/drafts/topics/{level_vocab,say_it,pron_level}.json`
into `content/topics/`, add their footage to `CATEGORY_FOOTAGE` from
`content/drafts/topics/footage_level_family.json` (20 subjects each, the same size as
every other category since 2026-10-14). Without it the first level_test render dies at
the background tier.

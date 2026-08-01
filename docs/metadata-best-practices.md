# Title, description and hashtag strategy

Researched 2026-08-01. Sources at the bottom. Every number in
`src/metadata_generator.py` traces to a line here.

---

## The one place the research contradicts the brief

**The instruction was "at least 10 hashtags". That is right for Instagram,
defensible for TikTok, and above the recommended range for YouTube.**

| platform | recommended | hard limit | what we ship |
|---|---|---|---|
| YouTube Shorts | **3–5** | **>15 ⇒ every hashtag ignored** | 10 |
| Instagram Reels | 5–15 | 30 | 12 |
| TikTok | 3–5, diminishing past 10–15 | 30 | 10 |

Two separate things are going on, and only one is a real constraint:

1. **The cliff is real and non-negotiable.** More than 15 hashtags and YouTube
   discards *all* of them — not the excess, all. `YOUTUBE_HASHTAG_HARD_CAP`
   enforces this and must never be raised.
2. **The 3–5 figure is a recommendation, not a rule.** 10 is legal and will not
   trigger the cliff. The cost is dilution: the first three are the ones
   YouTube renders as clickable links above the title, so tags 4–10 do
   progressively less.

We ship 10 on YouTube as instructed. If YouTube reach underperforms Instagram
on the same content, `PLATFORM_HASHTAGS["youtube"]` is the first dial to turn,
and dropping it to 5 is a one-line change.

---

## Titles

**YouTube Shorts — the title is a search surface.**
Put the keyword a learner would actually type in the first 40 characters
(`significado`, `cómo se dice`, or the English word itself). Keep it under
~70 so nothing truncates on mobile. **No hashtags in the title** except
`#Shorts`, which is required for the Shorts shelf — hashtags there consume the
space keywords need, and the description surfaces them anyway.

**TikTok / Instagram — the caption is the title.**
There is no separate field. The hook has to land in the visible portion before
the cut.

**Audience note that outranks all of the above:** the viewers search in
**Spanish** even though the subject is English. A fully-English title will not
be found by the people it is for. Hook in Spanish, keep the English term in
English.

## Descriptions

| platform | visible before cut | ideal total |
|---|---|---|
| TikTok | 80–120 chars | **150–300 chars** — measurably outperforms longer captions on reach |
| Instagram | ~80 chars before *Read More* | keyword-first opening line |
| YouTube | first line under the fold | one context sentence repeating the main keyword |

Instagram now indexes caption **keywords** more heavily than hashtags, so the
topic belongs in plain words in the first line rather than being carried by
tags.

## Hashtag mix

Tiered, not flat. Implemented as `BROAD → TYPE → category → NICHE` in
`_ensure_hashtags`:

- **broad** (2–3) — reach: `#LearnEnglish`, `#AprendeIngles`
- **type** (2–3) — what kind of video: `#EnglishQuiz`, `#CompletaLaFrase`
- **niche** (rest) — the audience that converts:
  `#InglesParaHispanohablantes`, `#EstudiaIngles`

Order matters: the first three are what YouTube renders above the title, and
on Instagram the earliest tags carry the most weight.

---

## Defects this work fixed

**Duplicate hashtag block, live on every published video.**
`adapt_for_platform` appends the tags to the description, and
`uploader.VideoMetadata.full_description` appended them *again*. Every video
published so far carries its hashtag block twice. `full_description` now checks
whether the first tag is already present before appending.

**Dedup bug in `_ensure_hashtags`.** `existing_lower` was snapshotted once and
never updated as tags were inserted, so a tag appearing in two tiers could be
emitted twice.

**The M3 contradiction, made worse before it was fixed.** The prompts stated a
hashtag count and then showed a worked example with far fewer — historically 3–4
against a stated 5–7 — and the model followed the example. Raising the rule to
12 without touching the examples would have widened that gap to 12-vs-3. Both
worked examples now show 12.

---

## Sources

- [YouTube Shorts Hashtags: Title vs Description Best Practices](https://hashtagtools.io/blog/youtube-shorts-hashtags-title-vs-description-2026)
- [YouTube Hashtags 2026: Tags vs Hashtags, Limits & Best Practices](https://hashtagtools.io/blog/youtube-hashtags-shorts-seo-guide-2026)
- [YouTube Description Best Practices 2026: Length, Limits, SEO Structure](https://touhfa.art/blog/seo/youtube-description-guide/)
- [Instagram Reels Hashtags 2026: How Many to Use + Best Practices](https://hashtagtools.io/blog/instagram-reels-hashtags-viral-strategy-2026)
- [Why Captions Matter More Than Hashtags on Instagram in 2026](https://lamplightcreatives.com/captions-vs-hashtags-instagram-2026/)
- [How Long Should a TikTok Caption Be in 2026?](https://monolit.sh/blog/how-long-should-tiktok-caption-be-2026-data-backed-answer-founders)
- [TikTok Caption Character Limit (2026)](https://kompozy.io/specs/tiktok-caption-character-limit)

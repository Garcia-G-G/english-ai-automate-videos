# STEP 80 §1b — title, description and hashtags at render time

`src/video_metadata.build(script, type)` → the sidecar's `metadata`: `title`, `alternatives`,
`description`, `hashtags` per platform, `source` (`llm` / `template` / `edited`), `checks`. Written
by every Shorts render (`admin.render_metadata`) and every series render (`series.render_one`).

- **Title**: `how_do_you_say` keeps `how_do_you_say_title()` exactly; `phrases_level` and the series
  use the script's title; other types: the LLM proposes 3, the code picks the first that is ≤ 70
  characters, ends in exactly one emoji, contains a Spanish search phrase («en inglés», «cómo se
  dice», «cómo decir»…), has no clickbait and no empty quotes, and is not already in
  `output/published/ledger.jsonl`; the other two are kept as alternatives.
- **Description**: the LLM's first line (≤ 120 characters, else the script's), the content as a
  searchable list — accepted only if every English word or phrase it names is one the script teaches,
  else built from the script («Manzana = apple · Pera = pear», the phrases, «Se dice: … · No: …»), a
  question that invites a comment, and the site line.
- **Hashtags**: YouTube `#[tema]eningles` (or `#vocabularioeningles`) · `#aprenderingles` ·
  `#inglesfacil` · `#inglesparahispanohablantes` · `#englishunlimited` + `#Shorts`; TikTok, Instagram
  and Facebook 4–5 through the existing `adapt_for_platform`; composed once, by `compose_description`.
- **One LLM call per video**, OpenAI `gpt-4o-mini` (logged by the cost tracker), and only inside a
  render Garcia launched — outside the panel's grant it is never asked. Any failure → the template.
- **Guards** before the sidecar: no empty quotes, no `{}` / `[[ ]]`, platform lengths, not an
  English-only title, not a published title; a refused result falls back to the template.
- **The panel**: «Revisar» shows the three fields filled in and editable, with «Usar alternativa»,
  «Regenerar» (the existing per-platform call) and «Guardar en el vídeo» (writes the sidecar); «Subir»
  starts from the sidecar's metadata and publishes it when nobody edited it in the session.

**Backfill ($0, no LLM)**: the six approved series videos (hc_c019, hc_e001, hc_m001, hc_m010, hc_p011,
hc_p019; they are in `approved/`, not `pending/`) have deterministic metadata in their sidecars now,
titled from their scripts («¿Le dices tu edad así a un nativo? 😬», «"Despite of": el "of" que sobra»…).

Not verified: no real LLM call (none may be from Claude); the first render Garcia launches is the
first one that asks it.

# STEP 80 §0 — two visible bugs

## 1. Titles with empty quotes

**Where they came from.** `metadata_generator._build_fallback_title` picked a template at random and
filled `'{word}'` with whatever `word` was — an empty string when the script had none. Two paths
reached it:
- `bit_vs_beat` (pronunciation, 11 Sep): a script with no `word` → «Llevas TODA tu vida diciendo '' MAL 😬».
- **hc_c010** (the series' first published Short, 23 Oct, YouTube and Facebook): a series sidecar
  has no `script_data`, so `script_for_upload` returned `{}`, and `hecho_con_claude` had no template
  of its own, so it fell to «educational» → «¿Sabías que '' NO significa lo que crees? 😱». The
  sidecar's own title («RETO: «llevo dos horas esperando»») was never used.

**Fixed.**
- A template is only used when every field it names has a value.
- `hecho_con_claude` has a safe template, and `generate_metadata` uses a series script's own
  `title` and `caption`.
- `script_for_upload` loads a series video's script by the `script_id` in its sidecar. The six
  approved series videos will go up with their own titles.
- **The guard**: `metadata_generator.metadata_problems` refuses empty quotes ('' "" «» ‘’ “”), a
  leftover `{…}` and `[[ ]]`. `generate_metadata` replaces a refused title or description, and the
  LLM's per-platform regeneration falls back when its result is refused.
- `tools/metadata_guard.py` runs it over everything queued and over the published ledger.

### The guard's run

Queued scripts checked: 547.

**Metadata generated now that fails the guard: 0.**


Scripts whose own field fails (the guard replaces it at render time): 0


## Published with a problem: 3 — edit by hand

| date | platform | field | text | why | link |
|---|---|---|---|---|---|
| 2026-09-11 | youtube | title | Llevas TODA tu vida diciendo '' MAL 😬 | empty quotes | https://youtube.com/shorts/oesG2Oj9xHc |
| 2026-10-23 | youtube | title | ¿Sabías que '' NO significa lo que crees? 😱 | empty quotes | https://youtube.com/shorts/xaXnas116LE |
| 2026-10-23 | facebook | title | ¿Sabías que '' NO significa lo que crees? 😱 | empty quotes | https://www.facebook.com/reel/1103130015808602/ |

## 2. Money rendered as LaTeX

Two «$» on one line of `st.markdown` (and of captions, expander and button labels, which Streamlit
renders as markdown too) are read as inline math. Escaped everywhere the panel shows money: `&#36;`
in the HTML cost line, `\$` in the markdown ones (`admin.py`: cost line, cost per video, batch
estimate; `manim_studio.py`: the four lesson cost labels). A test fails on any new bare `${` in
those two files.

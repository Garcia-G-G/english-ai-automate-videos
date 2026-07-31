# Dashboard metadata regeneration — diagnosis

Investigated 2026-07-31. Symptom: pressing a platform regenerate button on the
Upload page returns the same text, with no error and no visible change.

---

## Hypothesis A is true: the call fires and the result is discarded

Every press costs money and throws the answer away.

### Evidence the call is live

`regenerate_for_platform` IS reachable from the dashboard — `admin.py:1272`,
inside the platform button handler. (The earlier audit recorded this as
UNVERIFIED; it is now verified as wired.)

Invoked with the environment the dashboard actually has:

```
OPENAI_API_KEY present: True
call 1: 2.52s  "¿Qué significa 'fabric' en inglés? Aprende inglés fácil y rápido! 🌍"
call 2: 1.77s  "¿Qué significa 'fabric' en inglés? Aprende con este quiz divertido! | English Quiz"
differs: True
```

Two seconds of latency and different text on each call at `temperature=0.8`.
That is a live gpt-4o-mini round trip, not a local fallback.

**A false negative worth recording.** The first attempt at this measurement
ran without loading `.env`, so `os.environ.get("OPENAI_API_KEY")` returned
None and `regenerate_for_platform` silently took its fallback branch —
0.34 s, identical output both times. That looks exactly like "the call never
fires". The module reads `os.environ` directly and never calls `load_dotenv`
itself, so any harness that forgets it measures the wrong path. Same family as
`uploader.py` not loading `.env` (recorded-debt item 10).

### Why the cost log is empty

`output/costs/*.jsonl` contains no `metadata_*` entries, which initially looks
like proof the call never fired. It is not. `metadata_generator` does call
`get_tracker().log_openai_chat(...)` at `:178`, but `cost_tracker` only
persists through `pipeline.py` — recorded-debt item 2. The dashboard is a
separate Streamlit process, so its spend has never been written to disk.

**The cost log cannot answer this question**, and that is itself the finding:
every dashboard-initiated API call to date is unrecorded.

### The waste, quantified

One press, measured:

```
prompt tokens     181
completion tokens 150
cost per press    $0.000117
per 100 presses   $0.0117
per 1000 presses  $0.117
```

Small per press. The real cost is not the money — it is that the feature has
never worked, and every use of it produced a paid call whose result was
destroyed microseconds later.

---

## The mechanism

`admin.py:1249-1258` uses TWO different keys for one field:

```python
title_key  = f"meta_title_{video['name']}"   # storage
widget_key = f"ti_{video['name']}"           # the widget's own key

st.session_state[title_key] = st.text_input(
    "Title", value=st.session_state[title_key], key=widget_key)
```

A Streamlit widget with a `key` stores its value in
`st.session_state[key]`, and once that entry exists the `value=` argument is
IGNORED on every subsequent rerun.

So the sequence is:

1. Button handler calls the API and writes the result to
   `session_state[title_key]` — the storage key.
2. `st.rerun()`.
3. The `st.text_input` line executes. `widget_key` already holds the OLD text,
   so the widget returns the OLD text and ignores `value=`.
4. That return value is assigned straight back onto `session_state[title_key]`,
   **overwriting the regenerated value on the very next line.**

Simulated against the documented contract:

```
after first render : ORIGINAL TITLE
after button press : REGENERATED TITLE (paid for)
after rerun        : ORIGINAL TITLE
```

Manual EDITING works, which is why the bug reads as "regenerate does nothing"
rather than "the field is broken": typing updates `widget_key` first, so the
value that gets copied to storage is the edited one. Only writes that
originate outside the widget are lost.

---

## A second, independent failure — the bulk upload path

Fixing the widget does not make the upload correct.

| path | reads from | effect |
|---|---|---|
| single upload, `admin.py:1290` | `session_state[title_key]` | correct **once the widget is fixed** |
| **bulk upload, `admin.py:1386`** | `generate_metadata(script, …)` | **ignores the UI entirely** |

The bulk path regenerates metadata from the script at upload time and never
consults `session_state`. Anything typed or regenerated in the UI is silently
discarded, and the upload proceeds with different text than the operator
approved on screen.

That is worse than the display bug, because the screen shows the right thing
while the wrong thing is published.

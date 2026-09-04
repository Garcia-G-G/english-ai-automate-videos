# E1b — la privacidad se elige, no se hereda de un dataclass

**Va antes de E2.** Dos defaults, ninguno es rediseño.

---

## PROMPT

````
You are in ~/Downloads/english-ai-videos. HEAD is 6902167. E1 is landed.

Two unsafe defaults on the page whose button publishes irreversibly. Fix
both before starting E2.

1 · PRIVACY IS NEVER SET ON THE DASHBOARD PATH

src/uploader.py:73        privacy: str = "private"   (dataclass default)
src/uploader.py:693       VideoMetadata(title, description, hashtags or [])
                          — three positionals, so privacy stays "private"
src/uploader.py:704       privacy_status = "private"
                          → body["status"]["privacyStatus"] = "private"

No env var, no config.yaml key, nothing in .env.example, and
resolve_upload_metadata does not return it. Verified.

Meanwhile main.py:362 passes privacy="public".

So --batch publishes public and the dashboard publishes private. That is the
SIXTH main.py/admin.py divergence in this repo, and the most expensive one:
every video the dashboard has ever published went to an audience of zero.

The fix is NOT "flip the default to public". Privacy is per platform:

  - YouTube  → public is the point. Anything else defeats publishing.
  - TikTok   → SELF_ONLY is REQUIRED while the client is unaudited
               (uploader.py:460). Do not change this.
  - Instagram → decide and say which you chose and why.

Requirements:
  a. Privacy is resolved per platform, in ONE place both entry points use.
     Do not add a second resolution site — that is the divergence we are
     closing, not repeating.
  b. It is VISIBLE ON THE PAGE before the operator presses Upload. The
     operator must be able to see "YouTube: public / TikTok: private"
     without opening a file.
  c. main.py's privacy="public" stops being a separate literal and comes
     from the same resolver.

2 · UPLOAD TARGETS ARM THEMSELVES

reconcile_platform_target checks every connected platform as soon as the
page renders. You reported having to uncheck TikTok twice during P1.

A destination the operator did not choose must not be armed. Default all
upload-target checkboxes to UNCHECKED. The operator opts in per press.

This composes with (1): today a distracted press publishes to a platform
nobody selected, at a privacy nobody saw.

PROOF

  P1. The five artifacts published on 2026-08-24 are already handled — the
      operator uploaded them himself and is setting them public by hand. Do
      NOT touch them, do not re-upload, do not edit the ledger.

  P2. Upload one artifact to YouTube through the dashboard and show the API
      request body carrying privacyStatus: "public". The request body, not a
      log line saying so.

  P3. Screenshot of the Upload page showing the resolved privacy per platform
      before any press, and every target checkbox unchecked on first render.

  P4. grep proof that privacy is resolved in exactly one place and that
      main.py no longer holds its own literal.

  P5. Full test suite. Report the count. Add a test that pins YouTube to
      public and TikTok to SELF_ONLY, so this cannot silently regress — it
      already did once.

OUT OF SCOPE
  - E2 and the rest of Paso E. This is a default, not a restructure.
  - Republishing or changing anything already in the ledger.
  - The unaudited-TikTok situation itself.
````

---

## Por qué esto va delante de E2

Porque E2 mueve la página de subida de sitio. Arreglar un seguro **después** de mover el mueble significa arreglarlo dos veces, y mientras tanto el botón sigue armado.

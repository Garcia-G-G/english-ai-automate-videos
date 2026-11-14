# Panel 2.0 — English Unlimited

Claude built this front end. It is a local web app (Vite + React + TypeScript) over the
Python engine, in the «Mezcla» look: day 07:00–18:59 and night 19:00–06:59, New York time.

## Run it

**Demo, with no API.** Example data built from the real channel numbers:

```sh
cd panel
npm ci
npm run demo        # http://127.0.0.1:5173
```

**Real.** The API (STEP 85) serves the built app on http://127.0.0.1:8600:

```sh
npm run build       # writes panel/dist, which the API serves
./run_panel.sh      # from the repo root (STEP 85 §5)
```

During development, run `npm run dev` with the API running. Vite proxies `/api` and `/media` to 8600.

## What is where

| Path | What |
|---|---|
| `src/api/contract.ts` | **The contract.** Every shape the API must return, with comments. |
| `contract-fixtures/*.json` | The same shapes as JSON, for the API's contract tests. |
| `src/api/client.ts` | `fetch`, the paid-action token header, and the SSE stream. |
| `src/api/mock/` | Demo mode: the data and a fake API with a fake job. |
| `src/design/tokens.css` | Every colour, for both themes. |
| `src/design/app.css` | Components and motion. |
| `src/design/theme.ts` | The New York day/night rule, with its tests. |
| `src/lib/schedule.ts` | Free scheduling in Costa Rica time, with its tests. |
| `src/pages/` | Inicio, Revisar, and «muy pronto» placeholders for the rest. |

## Rules this app keeps

- **No business rule in TypeScript.** Priority, costs, XP and gates come from the API. The two exceptions are display-only:
  - the theme clock;
  - the schedule warnings, which repeat the API's checks so Garcia sees them while he picks.
- **A missing value shows «sin dato».** Never a guess, never a green tick without data.
- **Paid actions** (`/api/produce`, `/api/review/{id}/rerender`) send the `X-EU-Session` token from `<meta name="eu-session">` and `confirm: true`.
- **Only `transform` and `opacity` animate**, plus the theme crossfade. `prefers-reduced-motion` turns motion off.

## Checks

```sh
npm test            # vitest: theme, schedule, format, contract fixtures
npm run typecheck
npm run build       # initial JS ≈ 156 KB gzip (budget 220 KB)
```

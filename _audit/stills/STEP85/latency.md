# STEP 85 §7 latency (real HTTP to the running server, this Mac, real data, 2026-11-14)

Server: `run_panel.sh` (uvicorn, 127.0.0.1), measured with httpx, 300 calls per endpoint.

| What | Budget | Measured |
|---|---|---|
| `GET /api/meta`, p95 warm | <= 50 ms | 4.9 ms (p50 4.3, max 11) |
| `GET /api/home`, p95 warm | <= 150 ms | 5.8 ms (p50 4.5, max 7) |
| `GET /api/review`, p95 warm | <= 150 ms | 5.3 ms (p50 4.4, max 17) |
| `GET /api/home`, first request after start | <= 800 ms | 7 ms (caches are warmed before the first request) |
| `./run_panel.sh` with dist built, to first response | <= 2.5 s | 1.46 s |
| API process RSS, panel open | <= 300 MB after 2 h | 10-minute soak (SSE client + a GET every 2 s, 879 requests): 100 MB peak after warm-up, 31 MB at the end. Shortened; not a 2 h run. |

Without the start-up warm-up the first home request took about 1.0 s (the queue audit over 489 scripts is most of it).

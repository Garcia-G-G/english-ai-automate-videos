import type { Payload } from "./data";

// Hand-built sample matching src/senal.py build_payload; used by tests and later scene work.
export const fixture: Payload = {
  version: 1,
  read_at: "2026-11-07T08:00:00",
  data_until: "2026-11-05",
  platforms: ["youtube"],
  channel: {
    typical_daily: {
      how_do_you_say: [0, 153, 98, 41, 22, 15, 11, 9, 8, 6, 5, 4, 4, 3, 3],
      quiz: [0, 120, 80, 35, 20, 12, 9, 7, 6, 5, 4, 3, 3, 2, 2],
      all: [0, 140, 90, 38, 21, 14, 10, 8, 7, 5.5, 4.5, 3.5, 3.5, 2.5, 2.5],
    },
    typical_cum: {
      how_do_you_say: [0, 153, 251, 292, 314, 329, 340, 349, 357, 363, 368, 372, 376, 379, 382],
      quiz: [0, 120, 200, 235, 255, 267, 276, 283, 289, 294, 298, 301, 304, 306, 308],
      all: [0, 140, 230, 268, 289, 303, 313, 321, 328, 333.5, 338, 341.5, 345, 347.5, 350],
    },
    sources: { SHORTS: 0.91, YT_SEARCH: 0.06, EXT: 0.03 },
    median: { retention: 74.0, shares_per_1k: 1.2, subs_per_1k: 0.4 },
  },
  videos: [
    {
      id: "aB3dE5fGh1J", platform: "youtube", format: "how_do_you_say",
      published: "2026-11-01", age_days: 6,
      daily: [0, 410, 520, 380, 300, 260, 240], est_from: 5, views: 2110, retention: 81.5,
      sources: { SHORTS: 0.7, YT_SEARCH: 0.25, EXT: 0.05 },
      shares: 14, subs: 9, score: 2.4, state: "breakout", why: ["search", "retention"],
    },
    {
      id: "kL9mN0pQr2S", platform: "youtube", format: "quiz",
      published: "2026-10-27", age_days: 11,
      daily: [0, 95, 70, 30, 18, 14, 10, 9, 7, 6, 5, 5], est_from: null, views: 269, retention: 66.0,
      sources: { SHORTS: 0.93, YT_SEARCH: 0.04, EXT: 0.03 },
      shares: 1, subs: 0, score: 0.9, state: "normal", why: [],
    },
    {
      id: "tU4vW6xYz8A", platform: "youtube", format: "quiz",
      published: "2026-10-20", age_days: 18,
      daily: [0, 20, 11, 4, 2, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0], est_from: null, views: 40, retention: null,
      sources: {}, shares: 0, subs: 0, score: 0.3, state: "cold", why: [],
    },
  ],
  star: { youtube: "aB3dE5fGh1J" },
};

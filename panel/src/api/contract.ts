/**
 * The contract between the panel (this app) and the local API (Python, STEP 85).
 *
 * Every shape the app reads is defined here, once. The API returns exactly these
 * fields; the app never computes a business rule itself (priority, slots, costs,
 * XP): it only shows what the API says. A value the engine doesn't know is `null`,
 * and the app shows «sin dato» for it. Never a guess.
 *
 * Times are ISO-8601 strings with offset. Money is US dollars as a number.
 */

export type ThemeName = "day" | "night";

/** GET /api/meta — the frame around every page. Cheap; refreshed every 60 s. */
export interface Meta {
  version: string; // short git sha of the engine
  startedAt: string; // when the API process started
  ownerName: string; // config.yaml panel.owner_name, e.g. "Garcia"
  openrouter: { spentUsd: number; capUsd: number; perVideoAvgUsd: number | null; perVideoCapUsd: number };
  elevenlabsChars: number | null; // remaining characters, null if unreachable
  statsReadAt: string | null; // when YouTube stats were last read
  counts: { queue: number; review: number; upload: number; comments: number };
  streamlitUrl: string; // the old panel, for pages not yet rebuilt
  mock?: boolean; // true only in demo mode
}

/** GET /api/game — computed from the ledger and stats (panel_core/game.py). */
export interface Game {
  xp: number;
  level: number;
  levelXp: number; // XP inside the current level
  levelSize: number; // XP per level (1000)
  streakDays: number;
  streakIncludesToday: boolean;
  achievements: Achievement[]; // all of them, locked ones with unlockedAt = null
}
export interface Achievement {
  id: string;
  name: string; // «50 «Cómo se dice»»
  description: string; // one line, Spanish
  emoji: string;
  unlockedAt: string | null;
}

export interface Thumb {
  src: string; // 270×480 WebP
  src2x?: string; // 540×960 WebP
  placeholder?: string; // tiny blurred data: URI
}

export type Tone = "good" | "neutral" | "warn" | "bad";
export interface TagT { label: string; tone: Tone }

/** The family colours of the Tablero design, for drawn placeholders. */
export type Family = "casa" | "comida" | "cuerpo" | "animales" | "ropa" | "ciudad" | "emociones" | "clima" | "vida" | "reto" | "test";

export interface NextVideo {
  scriptId: string;
  type: string; // how_do_you_say …
  typeLabel: string; // «Cómo se dice»
  title: string; // full title
  topic: string; // the part to highlight, e.g. «MÁS ANIMALES»
  emoji: string;
  family: Family | null;
  slot: string | null; // «19:30», the slot it fills, Costa Rica time
  tags: TagT[]; // from the priority explanation
  words: string[]; // the English items
  facts: { durationS: number | null; costUsd: number | null; renderMin: number | null; repeated: number | null };
  thumb: Thumb | null; // frame 0 of the script (STEP 85b), null until drawn
  xp: number; // XP this video will earn when published
}

export interface Slot {
  time: string; // «08:30»
  state: "published" | "scheduled" | "free";
  title: string | null;
  emoji: string | null;
  views: number | null; // published only
  platforms: string[]; // scheduled: where
  fillsWith: string | null; // free: the script that will fill it
}

export interface Agenda {
  tz: string; // America/Costa_Rica
  today: Slot[];
  tomorrow: { slots: number; scripted: number };
}

export interface ViewsBlock {
  periodDays: number; // 28
  views: number;
  prevViews: number | null;
  daily: { date: string; views: number; uploads: number }[];
  totals: { views: number; subs: number; likes: number };
  dataUntil: string; // last day with data
}

export interface FormatRow { key: string; label: string; median: number; videos: number; color: string }

export interface Sequel { topic: string; emoji: string; parentViews: number }

/** GET /api/home — everything Inicio shows, in one call. */
export interface Home {
  daySentence: string; // «Hoy salen 4 vídeos y ya hay 3 en su sitio. Falta el de las 19:30.»
  next: NextVideo | null;
  agenda: Agenda;
  views: ViewsBlock;
  formats: FormatRow[]; // top 5, by median views
  formatsNote: string | null; // rule-based sentence, or null
  sequels: Sequel[];
}

export type StepKey = "guion" | "voz" | "montaje" | "sonido" | "control";
export const STEPS: { key: StepKey; label: string }[] = [
  { key: "guion", label: "Guion" },
  { key: "voz", label: "Voz" },
  { key: "montaje", label: "Montaje" },
  { key: "sonido", label: "Sonido" },
  { key: "control", label: "Control" },
];

/** GET /api/jobs/{id} */
export interface Job {
  id: string;
  scriptId: string;
  title: string;
  topic: string;
  startedAt: string;
  etaS: number | null;
  state: "running" | "done" | "failed";
  steps: Record<StepKey, number>; // 0..1 each
  log: string[]; // last lines, plain Spanish
  error: string | null;
}

/** POST /api/produce — body; needs the session token header and confirm: true. */
export interface ProduceRequest { scriptId?: string; confirm: true }
export interface ProduceResponse { jobId: string; etaS: number | null }

/** GET /api/events — Server-Sent Events. `event:` is the type, `data:` the JSON. */
export type ServerEvent =
  | { type: "job.step"; jobId: string; step: StepKey; progress: number; log?: string }
  | { type: "job.done"; jobId: string; artifact: string; reviewCount: number; xpGained: number }
  | { type: "job.failed"; jobId: string; reason: string }
  | { type: "counts"; counts: Meta["counts"] }
  | { type: "stats.refreshed" }
  | { type: "game"; game: Game }
  | { type: "achievement.unlocked"; achievement: Achievement };

export interface ApiError { error: string; detail?: string } // Spanish, shown to Garcia as is

/* ─────────────────────────── Revisar ─────────────────────────── */

export interface Check {
  key: "loudness" | "sync" | "vowels" | "motion" | "repeats" | "text" | string;
  label: string; // «Volumen»
  ok: boolean | null; // null = no data («sin dato», never a tick)
  detail: string | null; // «−14.1 LUFS»
}

export interface ReviewItem {
  id: string; // artifact id
  type: string;
  typeLabel: string;
  design: string | null; // «Tablero»
  items: number | null;
  title: string;
  description: string;
  hashtags: string[];
  durationS: number | null;
  costUsd: number | null;
  frame0: Thumb;
  strip: { label: string; src: string }[]; // 0 %, 25 %, 50 %, 75 %, final, fin
  videoUrl: string; // /media/… streamed by the API
  checks: Check[];
  gate: { passed: number; total: number; reason: string | null };
}

export interface Platform { key: string; label: string; mode: "auto" | "manual"; enabled: boolean; note: string | null }

/**
 * Garcia picks ANY time, today or any later day. The engine's usual slots are
 * only suggestions. Spacing and per-day limits are warnings, never blocks; the
 * only hard rule is that the time is at least `minLeadMin` in the future
 * (YouTube needs a future publishAt).
 */
export interface ScheduleInfo {
  tz: string; // America/Costa_Rica (no daylight saving: always −06:00)
  utcOffset: string; // "-06:00"
  slots: string[]; // the usual times, «08:30» …
  taken: { at: string; title: string }[]; // already scheduled or published, next 14 days
  minLeadMin: number; // 15
  spacingH: number; // 2.5 — a warning below this
  maxPerDay: number; // 4 — a warning above this
  next: string; // the next free usual slot (ISO), the default choice
}

/** GET /api/review */
export interface ReviewList { items: ReviewItem[]; schedule: ScheduleInfo; platforms: Platform[] }

/**
 * POST /api/review/{id}/approve — not a paid action (no token needed).
 * publishAt = null means «Aprobar» only: the video waits in «Por subir» with no time.
 */
export interface ApproveRequest { publishAt: string | null; platforms: string[]; title: string; description: string; hashtags: string[] }
export interface ApproveResponse { state: "scheduled" | "approved"; publishAt: string | null; results: { platform: string; ok: boolean; note: string | null }[]; warnings: string[] }

/** POST /api/review/{id}/reject */
export interface RejectRequest { reason: "audio" | "imagen" | "texto" | "otro"; note: string }

/** POST /api/review/{id}/rerender — paid: session token header + confirm. */
export interface RerenderRequest { confirm: true }

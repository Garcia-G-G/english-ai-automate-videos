// Mirrors build_payload in src/senal.py (spec §4). Version 1; extra fields are tolerated.
export type VideoState = "breakout" | "second_wind" | "cold" | "normal";
export type Sources = Record<string, number>;

export interface Video {
  id: string;
  platform: string;
  format: string;
  published: string;
  age_days: number;
  daily: number[]; // at most 15 values, days 0..14
  est_from: number | null; // daily[est_from..] are estimates
  views: number;
  retention: number | null;
  sources: Sources;
  shares: number;
  subs: number;
  score: number | null;
  state: VideoState;
  why: string[];
}

export interface Payload {
  version: 1;
  read_at: string;
  data_until: string;
  platforms: string[];
  channel: {
    typical_daily: Record<string, number[]>;
    typical_cum: Record<string, number[]>;
    sources: Sources;
    median: { retention: number; shares_per_1k: number; subs_per_1k: number };
  };
  videos: Video[];
  star: { youtube: string | null } & Record<string, string | null>;
}

export type ParseResult = { ok: true; data: Payload } | { ok: false; reason: string };

const MAX_DAILY = 15;
const STATES = ["breakout", "second_wind", "cold", "normal"];
const STALE_MS = 48 * 3600e3;

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const numArr = (v: unknown, max = Infinity): v is number[] => Array.isArray(v) && v.length <= max && v.every(isNum);
const numMap = (v: unknown): boolean => isObj(v) && Object.values(v).every(isNum);
const curveMap = (v: unknown): boolean => isObj(v) && "all" in v && Object.values(v).every((c) => numArr(c));

function videoProblem(v: unknown, i: number): string | null {
  if (!isObj(v)) return `videos[${i}] is not an object`;
  const at = `videos[${i}]`;
  for (const k of ["id", "platform", "format", "published"]) if (typeof v[k] !== "string") return `${at}.${k} is missing`;
  if (!numArr(v.daily, MAX_DAILY)) return `${at}.daily must be at most ${MAX_DAILY} numbers`;
  if (v.est_from !== null && !Number.isInteger(v.est_from)) return `${at}.est_from must be an integer or null`;
  for (const k of ["age_days", "views", "shares", "subs"]) if (!isNum(v[k])) return `${at}.${k} is missing`;
  if (v.retention !== null && !isNum(v.retention)) return `${at}.retention must be a number or null`;
  if (v.score !== null && !isNum(v.score)) return `${at}.score must be a number or null`;
  if (!numMap(v.sources)) return `${at}.sources is malformed`;
  if (!STATES.includes(v.state as string)) return `${at}.state is unknown`;
  if (!Array.isArray(v.why) || !v.why.every((w) => typeof w === "string")) return `${at}.why is malformed`;
  return null;
}

export function parsePayload(raw: unknown): ParseResult {
  const fail = (reason: string): ParseResult => ({ ok: false, reason });
  if (!isObj(raw)) return fail("the file is not a JSON object");
  if (raw.version !== 1) return fail(`unsupported version ${String(raw.version)}`);
  for (const k of ["read_at", "data_until"]) if (typeof raw[k] !== "string") return fail(`${k} is missing`);
  if (!Array.isArray(raw.platforms)) return fail("platforms is missing");
  const ch = raw.channel;
  if (!isObj(ch) || !curveMap(ch.typical_daily) || !curveMap(ch.typical_cum) || !numMap(ch.sources) || !numMap(ch.median))
    return fail("channel is missing or malformed");
  if (!Array.isArray(raw.videos)) return fail("videos is missing");
  for (let i = 0; i < raw.videos.length; i++) {
    const p = videoProblem(raw.videos[i], i);
    if (p) return fail(p);
  }
  const star = raw.star;
  if (!isObj(star) || !Object.values(star).every((s) => s === null || typeof s === "string")) return fail("star is missing or malformed");
  if (!("youtube" in star)) return fail("star.youtube is missing");
  return { ok: true, data: raw as unknown as Payload };
}

// NaN (unparseable read_at) counts as stale.
export const isStale = (p: Payload, now: Date): boolean => !(now.getTime() - Date.parse(p.read_at) <= STALE_MS);

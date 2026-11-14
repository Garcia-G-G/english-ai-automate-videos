/**
 * Demo data for `npm run demo` and the design proofs. Built from the channel's
 * real numbers on 14 Nov 2026 (views, formats, sequels, the daily curve until
 * 7 Nov). The agenda, the job and the XP/level/streak are illustrative: in the
 * real panel they come from the API. The app shows a «Datos de ejemplo» pill
 * whenever this file is in use.
 */
import type { Game, Home, Meta } from "../contract";

const DAILY: [string, number, number][] = [
  ["2026-10-11", 1, 0], ["2026-10-12", 2, 0], ["2026-10-13", 3205, 4], ["2026-10-14", 3153, 5], ["2026-10-15", 1402, 5],
  ["2026-10-16", 2678, 4], ["2026-10-17", 3711, 5], ["2026-10-18", 3717, 5], ["2026-10-19", 4886, 6], ["2026-10-20", 3730, 8],
  ["2026-10-21", 1750, 7], ["2026-10-22", 2077, 3], ["2026-10-23", 1408, 3], ["2026-10-24", 358, 0], ["2026-10-25", 129, 0],
  ["2026-10-26", 468, 6], ["2026-10-27", 1475, 4], ["2026-10-28", 2480, 5], ["2026-10-29", 1150, 0], ["2026-10-30", 1272, 5],
  ["2026-10-31", 1105, 0], ["2026-11-01", 155, 0], ["2026-11-02", 2104, 7], ["2026-11-03", 572, 5], ["2026-11-04", 251, 0],
  ["2026-11-05", 95, 0], ["2026-11-06", 3726, 5], ["2026-11-07", 428, 0],
];

export const demoMeta: Meta = {
  version: "demo",
  startedAt: "2026-11-14T20:21:00-06:00",
  ownerName: "Garcia",
  openrouter: { spentUsd: 6.58, capUsd: 15, perVideoAvgUsd: 0.11, perVideoCapUsd: 0.25 },
  elevenlabsChars: null,
  statsReadAt: "2026-11-14T03:33:14-06:00",
  counts: { queue: 491, review: 2, upload: 0, comments: 5 },
  streamlitUrl: "http://localhost:8502",
  mock: true,
};

export const demoGame: Game = {
  xp: 6720, level: 7, levelXp: 720, levelSize: 1000, streakDays: 23, streakIncludesToday: true,
  achievements: [
    { id: "first", name: "Primer vídeo", description: "Publicaste tu primer Short.", emoji: "🎬", unlockedAt: "2026-08-03T11:51:00-06:00" },
    { id: "v100", name: "100 vídeos", description: "Cien vídeos publicados.", emoji: "💯", unlockedAt: "2026-11-06T12:00:00-06:00" },
    { id: "views1k", name: "Primer millar", description: "Un vídeo pasó de 1,000 vistas.", emoji: "⭐", unlockedAt: "2026-10-14T09:00:00-06:00" },
    { id: "week10k", name: "Semana de 10,000", description: "10,000 vistas en 7 días.", emoji: "🔥", unlockedAt: "2026-10-19T20:00:00-06:00" },
    { id: "streak7", name: "Racha de 7", description: "Siete días seguidos publicando.", emoji: "📅", unlockedAt: "2026-10-28T08:30:00-06:00" },
    { id: "csd50", name: "50 «Cómo se dice»", description: "Cincuenta vídeos del formato que más rinde.", emoji: "🏆", unlockedAt: null },
    { id: "streak30", name: "Racha de 30", description: "Treinta días seguidos publicando.", emoji: "🗓️", unlockedAt: null },
    { id: "sequelwin", name: "La secuela gana", description: "Una secuela superó a su original.", emoji: "🚀", unlockedAt: null },
    { id: "noreject", name: "Semana limpia", description: "Siete días sin rechazar ningún vídeo.", emoji: "✨", unlockedAt: null },
  ],
};

export const demoHome: Home = {
  daySentence: "Hoy salen 4 vídeos y ya hay 3 en su sitio. Falta el de las 19:30.",
  next: {
    scriptId: "bv101_mas_animales",
    type: "how_do_you_say",
    typeLabel: "Cómo se dice",
    title: "¿Cómo se dicen MÁS ANIMALES en inglés?",
    topic: "MÁS ANIMALES",
    emoji: "🦒",
    family: "animales",
    slot: "19:30",
    tags: [
      { label: "★ Secuela de ANIMALES · 1,336", tone: "good" },
      { label: "Cómo se dice", tone: "neutral" },
      { label: "Tema básico", tone: "neutral" },
    ],
    words: ["kangaroo", "camel", "crocodile", "hippo", "frog", "bat", "gorilla", "rhino", "raccoon", "hedgehog"],
    facts: { durationS: 42, costUsd: 0.11, renderMin: 2, repeated: 0 },
    thumb: null,
    xp: 40,
  },
  agenda: {
    tz: "America/Costa_Rica",
    today: [
      { time: "08:30", state: "published", title: "¿Cómo se dice MÉDICO?", emoji: "🩺", views: 661, platforms: ["youtube", "facebook"], fillsWith: null },
      { time: "12:00", state: "published", title: "«YA LO RESOLVÍ»", emoji: "🧩", views: 496, platforms: ["youtube", "facebook"], fillsWith: null },
      { time: "16:00", state: "scheduled", title: "Test: LA FAMILIA", emoji: "👪", views: null, platforms: ["YouTube", "Facebook"], fillsWith: null },
      { time: "19:30", state: "free", title: null, emoji: null, views: null, platforms: [], fillsWith: "MÁS ANIMALES" },
    ],
    tomorrow: { slots: 4, scripted: 4 },
  },
  views: {
    periodDays: 28,
    views: 47488,
    prevViews: 1528,
    daily: DAILY.map(([date, views, uploads]) => ({ date, views, uploads })),
    totals: { views: 71097, subs: 126, likes: 1509 },
    dataUntil: "2026-11-07",
  },
  formats: [
    { key: "how_do_you_say", label: "Cómo se dice", median: 858, videos: 52, color: "#1F6FD1" },
    { key: "level_test", label: "Test de nivel", median: 502, videos: 9, color: "#FF6F4F" },
    { key: "phrases_level", label: "Frases", median: 405, videos: 14, color: "#12854F" },
    { key: "vocabulary", label: "Vocabulario", median: 318, videos: 8, color: "#2BB5A8" },
    { key: "say_it_level", label: "Dilo en inglés", median: 276, videos: 11, color: "#8A5CD6" },
  ],
  formatsNote: "«Cómo se dice» duplica a casi todo lo demás.",
  sequels: [
    { topic: "MÁS CASA", emoji: "🏠", parentViews: 1601 },
    { topic: "MÁS COMIDA", emoji: "🍎", parentViews: 1389 },
    { topic: "MÁS CARA", emoji: "🙂", parentViews: 1311 },
  ],
};

import type { ReviewList, ReviewItem } from "../contract";
import { nextDays } from "../../lib/schedule";

const strip = (k: string) => ["0 %", "25 %", "50 %", "75 %", "final", "fin"].map((label, i) => ({ label, src: `/demo/${k}_s${i}.webp` }));
const CHECKS = (loud: string): ReviewItem["checks"] => [
  { key: "loudness", label: "Volumen", ok: true, detail: loud },
  { key: "sync", label: "Voz y texto sincronizados", ok: true, detail: "desfase máx. 40 ms" },
  { key: "vowels", label: "Vocales del español", ok: true, detail: "ninguna «e» suena «i»" },
  { key: "motion", label: "Siempre hay movimiento", ok: true, detail: "quietud máx. 2.1 s" },
  { key: "repeats", label: "Palabras nuevas", ok: true, detail: "0 repetidas del canal" },
  { key: "text", label: "Título y texto limpios", ok: null, detail: null },
];

/** Built per request so the demo's «today» is always the viewer's today. */
export function demoReview(now = new Date()): ReviewList {
  const tz = "America/Costa_Rica";
  const [d0, d1] = nextDays(now, { tz }, 2).map((d) => d.date);
  const taken = [
    { at: `${d0}T08:30:00-06:00`, title: "¿Cómo se dice MÉDICO?" },
    { at: `${d0}T12:00:00-06:00`, title: "«YA LO RESOLVÍ»" },
    { at: `${d0}T16:00:00-06:00`, title: "Test: LA FAMILIA" },
    { at: `${d1}T08:30:00-06:00`, title: "MÁS PARTES DEL CUERPO" },
  ];
  const lastToday = new Date(`${d0}T19:30:00-06:00`).getTime() - now.getTime() > 15 * 60000;
  return {
    items: [
      {
        id: "mas_familia_demo", type: "how_do_you_say", typeLabel: "Cómo se dice", design: "Tablero", items: 5,
        title: "¿Cómo se dice MÁS FAMILIA en inglés? 👵 #Shorts",
        description: "Abuelo, abuela, bebé, niño y niña: ¿cuántas sabías en inglés? Dilo antes que yo 👀 Bonus: ¿cómo se dice «primo»? Escríbelo en los comentarios 👇\nMás rutas para aprender en learningroutes.com",
        hashtags: ["#AprendeInglés", "#InglésFácil", "#Familia", "#VocabularioEnInglés", "#Shorts"],
        durationS: 31, costUsd: 0.09,
        frame0: { src: "/demo/mas_familia_270.webp", src2x: "/demo/mas_familia_540.webp" },
        strip: strip("mas_familia"), videoUrl: "", checks: CHECKS("−14.1 LUFS"), gate: { passed: 5, total: 6, reason: null },
      },
      {
        id: "casa_demo", type: "how_do_you_say", typeLabel: "Cómo se dice", design: "Tablero", items: 10,
        title: "¿Cómo se dice CASA en inglés? 🏠 #Shorts",
        description: "Las 10 cosas de la casa en inglés. ¿Cuántas sabías?",
        hashtags: ["#AprendeInglés", "#Casa", "#Shorts"], durationS: 41, costUsd: 0.11,
        frame0: { src: "/demo/casa_270.webp", src2x: "/demo/casa_540.webp" },
        strip: [], videoUrl: "", checks: CHECKS("−13.9 LUFS"), gate: { passed: 5, total: 6, reason: null },
      },
    ],
    schedule: {
      tz, utcOffset: "-06:00", slots: ["08:30", "12:00", "16:00", "19:30"], taken, minLeadMin: 15, spacingH: 2.5, maxPerDay: 4,
      next: lastToday ? `${d0}T19:30:00-06:00` : `${d1}T12:00:00-06:00`,
    },
    platforms: [
      { key: "youtube", label: "YouTube", mode: "auto", enabled: true, note: "privado → público a la hora" },
      { key: "facebook", label: "Facebook", mode: "auto", enabled: true, note: "Reel programado" },
      { key: "tiktok", label: "TikTok", mode: "manual", enabled: false, note: "a mano" },
    ],
  };
}

/** A tiny in-browser stand-in for the API, used only in demo mode. */
import type { ApproveRequest, ApproveResponse, Game, Job, ProduceResponse, ReviewList, ServerEvent, StepKey } from "../contract";
import { STEPS } from "../contract";
import { demoGame, demoHome, demoMeta, demoReview } from "./data";

type Listener = (e: ServerEvent) => void;
const listeners = new Set<Listener>();
const jobs = new Map<string, Job>();
let meta = structuredClone(demoMeta);
let game: Game = structuredClone(demoGame);
let review: ReviewList | null = null;
const getReview = () => (review ??= demoReview());

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const emit = (e: ServerEvent) => listeners.forEach((l) => l(e));

export function mockSubscribe(l: Listener): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export async function mockGet(path: string): Promise<unknown> {
  await wait(120 + Math.random() * 120); // feel like a real local API
  if (path === "/api/meta") return meta;
  if (path === "/api/home") return demoHome;
  if (path === "/api/game") return game;
  if (path === "/api/review") return getReview();
  const job = path.match(/^\/api\/jobs\/(.+)$/);
  if (job && job[1]) {
    const j = jobs.get(job[1]);
    if (j) return j;
  }
  throw Object.assign(new Error("No encontrado"), { status: 404 });
}

const LOGS: Record<StepKey, string> = {
  guion: "Guion revisado: 10 palabras, 0 repetidas.",
  voz: "Voz: 10 de 10 frases, $0.08.",
  montaje: "Dibujando fotogramas 1,260 de 1,260.",
  sonido: "Sonido: −14.1 LUFS, sin sibilancias.",
  control: "Control de calidad: 6 de 6.",
};

export async function mockProduce(): Promise<ProduceResponse> {
  await wait(150);
  const id = `demo-${Date.now()}`;
  const next = demoHome.next!;
  const job: Job = {
    id, scriptId: next.scriptId, title: next.title, topic: next.topic, startedAt: new Date().toISOString(), etaS: 6,
    state: "running", steps: { guion: 0, voz: 0, montaje: 0, sonido: 0, control: 0 }, log: [], error: null,
  };
  jobs.set(id, job);
  void (async () => {
    for (const s of STEPS) {
      for (const p of [0.35, 0.7, 1]) {
        await wait(260);
        job.steps[s.key] = p;
        if (p === 1) job.log = [...job.log, LOGS[s.key]].slice(-3);
        emit({ type: "job.step", jobId: id, step: s.key, progress: p, log: p === 1 ? LOGS[s.key] : undefined });
      }
    }
    job.state = "done";
    meta = { ...meta, counts: { ...meta.counts, review: meta.counts.review + 1 } };
    emit({ type: "job.done", jobId: id, artifact: "como_se_dice_demo", reviewCount: meta.counts.review, xpGained: 40 });
    emit({ type: "counts", counts: meta.counts });
    const before = game.achievements.find((a) => a.id === "csd50");
    game = { ...game, xp: game.xp + 40, levelXp: game.levelXp + 40,
      achievements: game.achievements.map((a) => (a.id === "csd50" ? { ...a, unlockedAt: new Date().toISOString() } : a)) };
    emit({ type: "game", game });
    if (before && !before.unlockedAt) {
      await wait(500);
      emit({ type: "achievement.unlocked", achievement: game.achievements.find((a) => a.id === "csd50")! });
    }
  })();
  return { jobId: id, etaS: 6 };
}

/** Reset between tests. */
export function mockReset() {
  review = null;
  meta = structuredClone(demoMeta);
  game = structuredClone(demoGame);
  jobs.clear();
}

export async function mockApprove(id: string, body: ApproveRequest): Promise<ApproveResponse> {
  await wait(350);
  const r = getReview();
  const item = r.items.find((i) => i.id === id);
  review = { ...r, items: r.items.filter((i) => i.id !== id),
    schedule: body.publishAt ? { ...r.schedule, taken: [...r.schedule.taken, { at: body.publishAt, title: item?.title ?? id }] } : r.schedule };
  meta = { ...meta, counts: { ...meta.counts, review: Math.max(0, meta.counts.review - 1), upload: meta.counts.upload + (body.publishAt ? 0 : 1) } };
  emit({ type: "counts", counts: meta.counts });
  return { state: body.publishAt ? "scheduled" : "approved", publishAt: body.publishAt,
    results: body.platforms.map((p) => ({ platform: p, ok: true, note: null })), warnings: [] };
}

export async function mockReject(id: string): Promise<void> {
  await wait(250);
  const r = getReview();
  review = { ...r, items: r.items.filter((i) => i.id !== id) };
  meta = { ...meta, counts: { ...meta.counts, review: Math.max(0, meta.counts.review - 1) } };
  emit({ type: "counts", counts: meta.counts });
}

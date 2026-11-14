/**
 * How the app talks to the local API.
 *
 * - Reads are plain GETs on the same origin (the API serves this app).
 * - Paid actions (POST /api/produce, later re-render and drafts) carry the
 *   per-session token the API writes into <meta name="eu-session"> and an explicit
 *   `confirm: true`. Without both the API refuses: no other web page can make the
 *   panel spend.
 * - Live updates arrive over one EventSource on /api/events.
 * - Demo mode (VITE_MOCK=1, or ?demo in the URL) swaps all of it for mock/server.ts.
 */
import type { ApiError, ApproveRequest, ApproveResponse, ProduceRequest, ProduceResponse, RejectRequest, ServerEvent } from "./contract";
import { mockApprove, mockGet, mockProduce, mockReject, mockSubscribe } from "./mock/server";

export const isDemo: boolean =
  import.meta.env.VITE_MOCK === "1" || (typeof location !== "undefined" && new URLSearchParams(location.search).has("demo"));

export class ApiFailure extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

function sessionToken(): string {
  return document.querySelector<HTMLMetaElement>('meta[name="eu-session"]')?.content ?? "";
}

async function parse<T>(res: Response): Promise<T> {
  if (res.ok) return (await res.json()) as T;
  let msg = `El panel no respondió bien (HTTP ${res.status}).`;
  try {
    const body = (await res.json()) as ApiError;
    if (body.error) msg = body.error;
  } catch {
    /* not JSON: keep the generic message */
  }
  throw new ApiFailure(msg, res.status);
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  if (isDemo) return (await mockGet(path)) as T;
  const res = await fetch(path, { signal, headers: { Accept: "application/json" } });
  return parse<T>(res);
}

export async function produce(scriptId?: string): Promise<ProduceResponse> {
  if (isDemo) return mockProduce();
  const body: ProduceRequest = { confirm: true, ...(scriptId ? { scriptId } : {}) };
  const res = await fetch("/api/produce", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-EU-Session": sessionToken() },
    body: JSON.stringify(body),
  });
  return parse<ProduceResponse>(res);
}

async function postJSON<T>(path: string, body: unknown, paid = false): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (paid) headers["X-EU-Session"] = sessionToken();
  return parse<T>(await fetch(path, { method: "POST", headers, body: JSON.stringify(body) }));
}

/** Approve, with a time (scheduled) or without (waits in «Por subir»). Free: no token. */
export function approve(id: string, body: ApproveRequest): Promise<ApproveResponse> {
  if (isDemo) return mockApprove(id, body);
  return postJSON<ApproveResponse>(`/api/review/${encodeURIComponent(id)}/approve`, body);
}

export async function reject(id: string, body: RejectRequest): Promise<void> {
  if (isDemo) return mockReject(id);
  await postJSON<unknown>(`/api/review/${encodeURIComponent(id)}/reject`, body);
}

/** Re-render costs money: token + confirm, like produce. */
export async function rerender(id: string): Promise<ProduceResponse> {
  if (isDemo) return mockProduce();
  return postJSON<ProduceResponse>(`/api/review/${encodeURIComponent(id)}/rerender`, { confirm: true }, true);
}

const EVENT_TYPES: ServerEvent["type"][] = ["job.step", "job.done", "job.failed", "counts", "stats.refreshed", "game", "achievement.unlocked"];

/** One shared stream. Returns an unsubscribe function. Reconnects on its own. */
export function subscribe(onEvent: (e: ServerEvent) => void): () => void {
  if (isDemo) return mockSubscribe(onEvent);
  const es = new EventSource("/api/events");
  const handlers = EVENT_TYPES.map((type) => {
    const h = (m: MessageEvent<string>) => {
      try {
        onEvent({ type, ...JSON.parse(m.data) } as ServerEvent);
      } catch {
        /* a malformed event is dropped, never thrown into React */
      }
    };
    es.addEventListener(type, h as EventListener);
    return [type, h] as const;
  });
  return () => {
    handlers.forEach(([t, h]) => es.removeEventListener(t, h as EventListener));
    es.close();
  };
}

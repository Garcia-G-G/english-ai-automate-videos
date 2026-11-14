import { useSyncExternalStore } from "react";

/** A tiny store for UI-only state shared across the tree (Bubi's mood, toasts). */
export function createStore<T>(initial: T) {
  let state = initial;
  const subs = new Set<() => void>();
  return {
    get: () => state,
    set(next: T | ((s: T) => T)) {
      state = typeof next === "function" ? (next as (s: T) => T)(state) : next;
      subs.forEach((f) => f());
    },
    subscribe(f: () => void) {
      subs.add(f);
      return () => void subs.delete(f);
    },
  };
}

export function useStore<T>(store: ReturnType<typeof createStore<T>>): T {
  return useSyncExternalStore(store.subscribe, store.get, store.get);
}

export type BubiMood = "idle" | "wow" | "lo_lograste" | "bien_hecho";
export const bubiStore = createStore<{ mood: BubiMood; celebrate: number }>({ mood: "idle", celebrate: 0 });

export function setBubi(mood: BubiMood, ms?: number) {
  bubiStore.set((s) => ({ mood, celebrate: mood === "idle" || mood === "wow" ? s.celebrate : s.celebrate + 1 }));
  if (ms) setTimeout(() => bubiStore.get().mood === mood && bubiStore.set((s) => ({ ...s, mood: "idle" })), ms);
}

export interface ToastT { id: number; html: string; tone: "normal" | "bad"; leaving?: boolean }
export const toastStore = createStore<ToastT[]>([]);
let tid = 0;
/** `html` may contain <em> for the highlighted word; callers only pass our own strings. */
export function toast(html: string, opts: { tone?: "normal" | "bad"; ms?: number } = {}) {
  const id = ++tid;
  toastStore.set((l) => [...l.slice(-2), { id, html, tone: opts.tone ?? "normal" }]);
  const ms = opts.ms ?? 2600;
  setTimeout(() => toastStore.set((l) => l.map((t) => (t.id === id ? { ...t, leaving: true } : t))), ms);
  setTimeout(() => toastStore.set((l) => l.filter((t) => t.id !== id)), ms + 260);
}

export const reducedMotion = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

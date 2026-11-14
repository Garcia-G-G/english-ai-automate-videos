import { useQuery, type QueryClient } from "@tanstack/react-query";
import { apiGet } from "./client";
import type { Game, Home, Meta, ReviewList, ServerEvent } from "./contract";

export const keys = { meta: ["meta"] as const, home: ["home"] as const, game: ["game"] as const, review: ["review"] as const };

export const useMeta = () => useQuery({ queryKey: keys.meta, queryFn: ({ signal }) => apiGet<Meta>("/api/meta", signal), refetchInterval: 60_000 });
export const useHome = () => useQuery({ queryKey: keys.home, queryFn: ({ signal }) => apiGet<Home>("/api/home", signal), refetchInterval: 120_000 });
export const useReview = () => useQuery({ queryKey: keys.review, queryFn: ({ signal }) => apiGet<ReviewList>("/api/review", signal) });
export const useGame = () => useQuery({ queryKey: keys.game, queryFn: ({ signal }) => apiGet<Game>("/api/game", signal) });

/** Server events update the cache in place, so every screen shows them at once. */
export function applyEvent(qc: QueryClient, e: ServerEvent) {
  switch (e.type) {
    case "counts":
      qc.setQueryData<Meta>(keys.meta, (m) => (m ? { ...m, counts: e.counts } : m));
      break;
    case "game":
      qc.setQueryData<Game>(keys.game, e.game);
      break;
    case "stats.refreshed":
      void qc.invalidateQueries({ queryKey: keys.home });
      void qc.invalidateQueries({ queryKey: keys.meta });
      break;
    case "job.done":
      void qc.invalidateQueries({ queryKey: keys.home });
      void qc.invalidateQueries({ queryKey: keys.review });
      break;
    default:
      break;
  }
}

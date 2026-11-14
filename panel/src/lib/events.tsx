import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { subscribe } from "../api/client";
import type { ServerEvent } from "../api/contract";
import { applyEvent } from "../api/hooks";

type Listener = (e: ServerEvent) => void;
const Ctx = createContext<{ on: (l: Listener) => () => void } | null>(null);

/** Opens the one event stream for the whole app and fans it out. */
export function EventsProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const listeners = useRef(new Set<Listener>());
  useEffect(
    () =>
      subscribe((e) => {
        applyEvent(qc, e);
        listeners.current.forEach((l) => l(e));
      }),
    [qc],
  );
  const on = (l: Listener) => {
    listeners.current.add(l);
    return () => void listeners.current.delete(l);
  };
  return <Ctx.Provider value={{ on }}>{children}</Ctx.Provider>;
}

export function useServerEvent(handler: Listener) {
  const ctx = useContext(Ctx);
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => ctx?.on((e) => ref.current(e)), [ctx]);
}

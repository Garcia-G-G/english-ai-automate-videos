import { useEffect, useState } from "react";
import type { ThemeName } from "../api/contract";

/** Garcia's rule: night from 19:00 to 06:59 in New York, day from 07:00 to 18:59. */
export const THEME_TZ = "America/New_York";
export const NIGHT_FROM = 19;
export const DAY_FROM = 7;

const hourFmt = new Intl.DateTimeFormat("en-US", { timeZone: THEME_TZ, hour: "numeric", hourCycle: "h23" });

export function nyHour(at: Date): number {
  return Number(hourFmt.format(at)) % 24;
}

export function themeAt(at: Date): ThemeName {
  const h = nyHour(at);
  return h >= NIGHT_FROM || h < DAY_FROM ? "night" : "day";
}

/** When the automatic theme changes next, as «19:00» or «7:00» (New York). */
export function nextSwitchLabel(t: ThemeName): string {
  return t === "night" ? `${DAY_FROM}:00` : `${NIGHT_FROM}:00`;
}

export type ThemeMode = "auto" | ThemeName;
const KEY = "eu.themeMode";

export function readMode(): ThemeMode {
  try {
    const v = localStorage.getItem(KEY);
    return v === "day" || v === "night" ? v : "auto";
  } catch {
    return "auto";
  }
}
function writeMode(m: ThemeMode) {
  try {
    if (m === "auto") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, m);
  } catch {
    /* storage blocked: the mode lasts for this visit only */
  }
}

function apply(t: ThemeName) {
  const root = document.documentElement;
  if (root.dataset.theme === t) return;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
  if (root.dataset.theme && !reduce && doc.startViewTransition) {
    root.classList.add("theme-swap");
    doc.startViewTransition(() => {
      root.dataset.theme = t;
    });
    setTimeout(() => root.classList.remove("theme-swap"), 700);
  } else {
    root.dataset.theme = t;
  }
}

/** The theme in force, the mode, and a setter. Re-checks every minute and on return to the tab. */
export function useTheme() {
  const [mode, setModeState] = useState<ThemeMode>(readMode);
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const tick = () => setNow(new Date());
    const id = setInterval(tick, 60_000);
    const vis = () => document.visibilityState === "visible" && tick();
    document.addEventListener("visibilitychange", vis);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", vis);
    };
  }, []);
  const theme: ThemeName = mode === "auto" ? themeAt(now) : mode;
  useEffect(() => apply(theme), [theme]);
  const setMode = (m: ThemeMode) => {
    writeMode(m);
    setModeState(m);
  };
  return { theme, mode, setMode, until: nextSwitchLabel(theme) };
}

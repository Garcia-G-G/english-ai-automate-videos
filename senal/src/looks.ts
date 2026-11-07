// Three candidate art directions; the owner keeps one (brief Step 6).
export interface Look {
  fogDensity: number; // FogExp2 density; far ridges dissolve into the horizon colour
  crestWidth: number; // px
  ghostWidth: number; // px
  hairWidth: number; // px, curtain hairlines
  bloomIntensity: number;
  bloomThreshold: number;
  bloomRadius: number;
  grain: number; // film noise opacity 0..1
  vignette: number; // darkness 0..1
  background: [top: string, horizon: string, bottom: string];
}

export const LOOKS: Record<"a" | "b" | "c", Look> = {
  // a: crisp and minimal. Thin lines, clear air, only the breakout crests glow.
  a: {
    fogDensity: 0.018,
    crestWidth: 1.6,
    ghostWidth: 1,
    hairWidth: 0.7,
    bloomIntensity: 0.9,
    bloomThreshold: 0.9,
    bloomRadius: 0.55,
    grain: 0.12,
    vignette: 0.55,
    background: ["#05070f", "#0a1020", "#05070f"],
  },
  // b: night haze. Denser fog, wider glow, the landscape reads as light in mist.
  b: {
    fogDensity: 0.028,
    crestWidth: 2.2,
    ghostWidth: 1.2,
    hairWidth: 0.9,
    bloomIntensity: 3.2,
    bloomThreshold: 0.4,
    bloomRadius: 0.9,
    grain: 0.2,
    vignette: 0.7,
    background: ["#04060d", "#0d1a33", "#05070f"],
  },
  // c: editorial dusk. A faint warm horizon behind the cold lines, heavier grain, firmer frame.
  c: {
    fogDensity: 0.024,
    crestWidth: 1.9,
    ghostWidth: 1.1,
    hairWidth: 0.8,
    bloomIntensity: 1.4,
    bloomThreshold: 0.75,
    bloomRadius: 0.7,
    grain: 0.3,
    vignette: 0.8,
    background: ["#05070f", "#26171f", "#06060b"],
  },
};

export const DEFAULT_LOOK: keyof typeof LOOKS = "a";

export function lookFromQuery(search: string): Look {
  const k = new URLSearchParams(search).get("look");
  return LOOKS[k === "a" || k === "b" || k === "c" ? k : DEFAULT_LOOK];
}

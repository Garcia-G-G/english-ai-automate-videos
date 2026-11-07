// Three candidate art directions; the owner keeps one (brief Step 6).
export interface Look {
  view: { elevation: number; azimuth: number; fov: number }; // degrees; camera is fitted to the drawn ridges
  fogDepth: number; // linear fog reaches full past centre + fogDepth x box radius; smaller = denser
  fogColor: string;
  crestWidth: number; // px
  ghostWidth: number; // px
  hairWidth: number; // px, curtain hairlines
  curtain: number; // curtain opacity gain
  ghost: number; // ghost opacity gain
  bloomIntensity: number;
  bloomThreshold: number;
  bloomRadius: number;
  grain: number; // film noise opacity 0..1
  vignette: number; // darkness 0..1
  background: { top: string; horizon: string; bottom: string; at: number }; // at: horizon height 0 (top)..1
}

export const LOOKS: Record<"a" | "b" | "c", Look> = {
  // a, survey: high three-quarter view, hairline-thin lines, clear air, sparse curtain; only breakouts glint.
  a: {
    view: { elevation: 30, azimuth: -52, fov: 30 },
    fogDepth: 2.2,
    fogColor: "#070a14",
    crestWidth: 1.2,
    ghostWidth: 0.8,
    hairWidth: 0.5,
    curtain: 0.55,
    ghost: 0.9,
    bloomIntensity: 0.7,
    bloomThreshold: 0.95,
    bloomRadius: 0.35,
    grain: 0.08,
    vignette: 0.35,
    background: { top: "#05070f", horizon: "#070a14", bottom: "#05070f", at: 0.4 },
  },
  // b, mist: low raking angle, heavy lines, dense luminous curtain sinking into blue fog, wide bloom.
  b: {
    view: { elevation: 11, azimuth: -54, fov: 38 },
    fogDepth: 0.55,
    fogColor: "#10203f",
    crestWidth: 2.6,
    ghostWidth: 1.3,
    hairWidth: 1.1,
    curtain: 1.6,
    ghost: 0.7,
    bloomIntensity: 2.4,
    bloomThreshold: 0.35,
    bloomRadius: 0.95,
    grain: 0.18,
    vignette: 0.75,
    background: { top: "#03050b", horizon: "#0f1e3d", bottom: "#05070f", at: 0.55 },
  },
  // c, editorial: frontal telephoto, compressed depth, almost no curtain, strong ghosts, warm dusk band, heavy grain.
  c: {
    view: { elevation: 9, azimuth: -28, fov: 16 },
    fogDepth: 1.1,
    fogColor: "#1d1219",
    crestWidth: 1.8,
    ghostWidth: 1.2,
    hairWidth: 0.6,
    curtain: 0.3,
    ghost: 1.6,
    bloomIntensity: 1.3,
    bloomThreshold: 0.7,
    bloomRadius: 0.6,
    grain: 0.32,
    vignette: 0.9,
    background: { top: "#06060c", horizon: "#2a1922", bottom: "#05070f", at: 0.68 },
  },
};

export const DEFAULT_LOOK: keyof typeof LOOKS = "a";

export function lookFromQuery(search: string): Look {
  const k = new URLSearchParams(search).get("look");
  return LOOKS[k === "a" || k === "b" || k === "c" ? k : DEFAULT_LOOK];
}

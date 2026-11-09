// The owner's look: warm dusk, low camera, heavy grain, firm vignette.
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

export const DEFAULT_LOOK: Look = {
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
};

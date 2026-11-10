import { CatmullRomCurve3, Color, DataTexture, Group, LinearFilter, Sprite, SpriteMaterial, Vector3 } from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import type { Video } from "./data";
import { reducedMotion } from "./camera";
import type { Look } from "./looks";

export const HMAX = 7;
export const GAP = 1.6;
export const DAYS = 14;
const SPAN = 20; // dayX maps 0..DAYS onto -SPAN/2..SPAN/2
const SUBDIV = 6; // crest samples per day; the curtain gets one hairline per sample
const GHOST_BACK = 0.3; // ghost sits just behind its ridge
const LINE = new Color("#dfe6ff");
// Retention is a percentage and can exceed 100 on loops; null means no reading yet.
const NO_RETENTION = 0.2;
// setDim(1) leaves a faint trace so a focused ridge stands alone; REST_DIM keeps the resting verdict's 0.22 opacity.
const DIM_DEPTH = 0.985;
export const REST_DIM = 0.78 / DIM_DEPTH;

// A video this young is still growing: it gets a live edge and the full typical path ahead of it.
export const YOUNG_DAYS = 3;
const LEAD_DAYS = 0.5; // every crest rises from the ground this far before day 0
const EDGE_SIZE = 0.9; // live edge sprite, world units

export type LineRole = "crest" | "ghost" | "curtain" | "floor";

export interface RidgeObject {
  group: Group;
  crest: Vector3[];
  setDim(d: number): void;
  setGlow(g: number): void;
}

export const heightOf = (views: number, maxDaily: number): number =>
  maxDaily > 0 ? Math.pow(Math.max(0, views) / maxDaily, 0.55) * HMAX : 0;
export const ridgeZ = (index: number): number => 0 - index * GAP;
export const dayX = (day: number): number => (day / DAYS) * SPAN - SPAN / 2;

/**
 * Smooth path from the ground at -LEAD_DAYS through the daily samples, so even a 1-day video reads as a mountain.
 * Sample k*SUBDIV is exactly day k-1 (index-uniform spline). y clamped so an overshoot never goes underground.
 */
function smooth(values: number[], maxDaily: number, z: number): Vector3[] {
  if (!values.length) return [];
  const pts = [new Vector3(dayX(-LEAD_DAYS), 0, z), ...values.map((n, d) => new Vector3(dayX(d), heightOf(n, maxDaily), z))];
  const curve = new CatmullRomCurve3(pts, false, "centripetal");
  return curve.getPoints((pts.length - 1) * SUBDIV).map((p) => p.setY(Math.max(0, p.y)));
}

export function material(role: LineRole, opacity: number, extra: Partial<LineMaterial> = {}): LineMaterial {
  const m = new LineMaterial({ color: 0xffffff, vertexColors: true, transparent: true, opacity, depthWrite: false, ...extra });
  m.fog = true;
  m.userData = { role, base: opacity };
  return m;
}

const flat = (pts: Vector3[]): number[] => pts.flatMap((p) => [p.x, p.y, p.z]);
const tint = (k: number, n: number): number[] => Array.from({ length: n }, () => [LINE.r * k, LINE.g * k, LINE.b * k]).flat();

/** Index of the first crest sample that belongs to an estimated day, or Infinity. */
const estStart = (v: Video): number => (v.est_from === null ? Infinity : (v.est_from + 1) * SUBDIV); // +1: the ground lead

function crestLine(pts: Vector3[], k: number, mat: LineMaterial): Line2 | null {
  if (pts.length < 2) return null;
  const g = new LineGeometry();
  g.setPositions(flat(pts));
  g.setColors(tint(k, pts.length));
  return new Line2(g, mat);
}

/** Vertical hairlines from each crest sample to the ground, fading toward the floor. */
export function curtain(pts: Vector3[], k: number, mat: LineMaterial): LineSegments2 | null {
  if (!pts.length) return null;
  const g = new LineSegmentsGeometry();
  g.setPositions(pts.flatMap((p) => [p.x, p.y, p.z, p.x, 0, p.z]));
  g.setColors(pts.flatMap(() => [...tint(k, 1), ...tint(k * 0.08, 1)]));
  return new LineSegments2(g, mat);
}

export function buildRidge(v: Video, typicalDaily: number[], maxDaily: number, z: number): RidgeObject {
  const group = new Group();
  group.userData = { id: v.id };
  const crest = smooth(v.daily, maxDaily, z);
  const cut = Math.min(estStart(v), crest.length);
  const confirmed = crest.slice(0, cut + 1);
  const estimated = crest.slice(cut);

  const crestMat = material("crest", 1);
  const estMat = material("crest", 0.5);
  const curtainMat = material("curtain", curtainOpacity(v));
  const estCurtainMat = material("curtain", curtainOpacity(v) * 0.5);
  const young = v.age_days <= YOUNG_DAYS;
  // A young video's ghost runs the whole 0..DAYS path, quieter, to show where a typical video goes.
  const ghostMat = material("ghost", young ? 0.2 : 0.35, { dashed: true, dashSize: 0.25, gapSize: 0.2 });
  const floorMat = material("floor", 0.05); // zero baseline; applyLook scales it with the curtain gain, so it stays under the curtain
  const mats: (LineMaterial | SpriteMaterial)[] = [crestMat, estMat, curtainMat, estCurtainMat, ghostMat, floorMat];

  const ghost = crestLine(smooth(typicalDaily.slice(0, young ? DAYS + 1 : v.daily.length), maxDaily, z - GHOST_BACK), 0.8, ghostMat);
  ghost?.computeLineDistances();
  const parts = [
    ghost,
    crestLine(confirmed, 1, crestMat),
    crestLine(estimated, 1, estMat),
    curtain(crest.slice(0, cut), 1, curtainMat),
    curtain(crest.slice(cut), 1, estCurtainMat),
    // The video's own day axis 0..DAYS on the ground: the days it has not lived yet stay visible.
    crestLine([new Vector3(dayX(0), 0, z), new Vector3(dayX(DAYS), 0, z)], 0.45, floorMat),
  ];
  for (const p of parts) if (p) group.add(p);
  if (young && crest.length) {
    const edge = liveEdge(crest.at(-1)!);
    mats.push(edge.material);
    group.add(edge);
  }

  let dim = 0;
  let glow = 0;
  const apply = () => {
    for (const m of mats) {
      m.opacity = m.userData.base * (1 - DIM_DEPTH * dim);
      // Above 1 the crest crosses the bloom threshold; the ghost and curtain never glow.
      if (m.userData.role === "crest" || m.userData.role === "edge") m.color.setScalar(1 + 2.2 * glow);
    }
  };
  const ridge: RidgeObject = {
    group,
    crest,
    setDim: (d) => ((dim = d), apply()),
    setGlow: (g) => ((glow = g), apply()),
  };
  // Colour and dimming follow the engine's verdict, never the ridge's position.
  const bright = v.state === "breakout" || v.state === "second_wind";
  ridge.setDim(bright ? 0 : REST_DIM);
  ridge.setGlow(bright ? 1 : 0);
  return ridge;
}

let glowTexture: DataTexture | null = null;
/** Soft round falloff, built without a DOM so it also works in tests. */
export function softDot(): DataTexture {
  if (glowTexture) return glowTexture;
  const n = 64;
  const px = new Uint8Array(n * n * 4);
  for (let y = 0; y < n; y++)
    for (let x = 0; x < n; x++) {
      const r = Math.hypot(x - n / 2 + 0.5, y - n / 2 + 0.5) / (n / 2);
      const i = (y * n + x) * 4;
      px.fill(255, i, i + 3);
      px[i + 3] = Math.round(255 * Math.max(0, 1 - r) ** 2);
    }
  glowTexture = new DataTexture(px, n, n);
  glowTexture.magFilter = glowTexture.minFilter = LinearFilter; // Nearest (the default) shows square steps when enlarged
  glowTexture.needsUpdate = true;
  return glowTexture;
}

/** The glowing point at a young video's last crest sample; breathes gently unless motion is reduced. */
function liveEdge(at: Vector3): Sprite {
  const m = new SpriteMaterial({ map: softDot(), transparent: true, depthWrite: false, opacity: 0.9 });
  m.userData = { role: "edge", base: 0.9 };
  const s = new Sprite(m);
  s.position.copy(at);
  s.scale.setScalar(EDGE_SIZE);
  let still: boolean | null = null;
  s.onBeforeRender = () => {
    still ??= reducedMotion();
    if (!still) s.scale.setScalar(EDGE_SIZE * (1 + 0.12 * Math.sin(performance.now() / 700)));
  };
  return s;
}

const retentionOf = (v: Video): number => (v.retention === null ? NO_RETENTION : Math.max(0, v.retention / 100));
/** Curtain opacity before the look's gain: brighter the more of the video people watch. */
export const curtainOpacity = (v: Video): number => 0.55 * Math.min(retentionOf(v), 1);

/** Applies the look's widths and opacity gains; the floor follows the curtain gain so it never outshines it. */
export function applyLook(group: Group, look: Look): void {
  const width: Record<LineRole, number> = { crest: look.crestWidth, ghost: look.ghostWidth, curtain: look.hairWidth, floor: look.hairWidth };
  const gain: Record<LineRole, number> = { crest: 1, ghost: look.ghost, curtain: look.curtain, floor: look.curtain };
  group.traverse((o) => {
    const m = (o as { material?: LineMaterial }).material;
    const role = m?.userData.role as LineRole | undefined;
    if (!m || !role || !(role in gain)) return; // the live edge keeps its own size and opacity
    m.linewidth = width[role];
    m.userData.base *= gain[role]; // keeps setDim consistent with the look
    m.opacity *= gain[role];
  });
}

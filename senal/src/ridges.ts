import { CatmullRomCurve3, Color, Group, Vector3 } from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import type { Video } from "./data";

export const HMAX = 7;
export const GAP = 1.6;
export const DAYS = 14;
const SPAN = 20; // dayX maps 0..DAYS onto -SPAN/2..SPAN/2
const SUBDIV = 6; // crest samples per day; the curtain gets one hairline per sample
const GHOST_BACK = 0.3; // ghost sits just behind its ridge
const LINE = new Color("#dfe6ff");
// Retention is a percentage and can exceed 100 on loops; null means no reading yet.
const NO_RETENTION = 0.2;

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

/** Smooth path through the daily samples; y clamped so a spline overshoot never goes underground. */
function smooth(values: number[], maxDaily: number, z: number): Vector3[] {
  const pts = values.map((n, d) => new Vector3(dayX(d), heightOf(n, maxDaily), z));
  if (pts.length < 2) return pts;
  const curve = new CatmullRomCurve3(pts, false, "centripetal");
  return curve.getPoints((pts.length - 1) * SUBDIV).map((p) => p.setY(Math.max(0, p.y)));
}

function material(role: LineRole, opacity: number, extra: Partial<LineMaterial> = {}): LineMaterial {
  const m = new LineMaterial({ color: 0xffffff, vertexColors: true, transparent: true, opacity, depthWrite: false, ...extra });
  m.fog = true;
  m.userData = { role, base: opacity };
  return m;
}

const flat = (pts: Vector3[]): number[] => pts.flatMap((p) => [p.x, p.y, p.z]);
const tint = (k: number, n: number): number[] => Array.from({ length: n }, () => [LINE.r * k, LINE.g * k, LINE.b * k]).flat();

/** Index of the first crest sample that belongs to an estimated day, or Infinity. */
const estStart = (v: Video): number => (v.est_from === null ? Infinity : v.est_from * SUBDIV);

function crestLine(pts: Vector3[], k: number, mat: LineMaterial): Line2 | null {
  if (pts.length < 2) return null;
  const g = new LineGeometry();
  g.setPositions(flat(pts));
  g.setColors(tint(k, pts.length));
  return new Line2(g, mat);
}

/** Vertical hairlines from each crest sample to the ground, fading toward the floor. */
function curtain(pts: Vector3[], k: number, mat: LineMaterial): LineSegments2 | null {
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
  const keep = Math.min(retentionOf(v), 1);

  const crestMat = material("crest", 1);
  const estMat = material("crest", 0.5);
  const curtainMat = material("curtain", 0.55 * keep);
  const estCurtainMat = material("curtain", 0.55 * keep * 0.5);
  const ghostMat = material("ghost", 0.35, { dashed: true, dashSize: 0.25, gapSize: 0.2 });
  const floorMat = material("floor", 0.12); // zero baseline: quieter than any curtain
  const mats = [crestMat, estMat, curtainMat, estCurtainMat, ghostMat, floorMat];

  const ghost = crestLine(smooth(typicalDaily.slice(0, v.daily.length), maxDaily, z - GHOST_BACK), 0.8, ghostMat);
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

  let dim = 0;
  let glow = 0;
  const apply = () => {
    for (const m of mats) {
      m.opacity = m.userData.base * (1 - 0.78 * dim);
      // Above 1 the crest crosses the bloom threshold; the ghost and curtain never glow.
      if (m.userData.role === "crest") m.color.setScalar(1 + 2.2 * glow);
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
  ridge.setDim(bright ? 0 : 1);
  ridge.setGlow(bright ? 1 : 0);
  return ridge;
}

const retentionOf = (v: Video): number => (v.retention === null ? NO_RETENTION : Math.max(0, v.retention / 100));

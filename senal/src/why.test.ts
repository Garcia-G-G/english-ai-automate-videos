import { PerspectiveCamera, Points, Scene, Vector2 } from "three";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { fixture } from "./fixture";
import { buildRidge } from "./ridges";
import type { Stage } from "./scene";
import { DEFAULT_LOOK } from "./looks";
import { allocateParticles, createWhy, laneCounts, MIN_LANE } from "./why";

test("particles follow the real source proportions", () =>
  expect(allocateParticles({ SHORTS: 0.7, YT_SEARCH: 0.25, EXT: 0.05 }, 400)).toEqual({ SHORTS: 280, YT_SEARCH: 100, EXT: 20 }));

test("no sources means no particles", () => {
  const c = allocateParticles({}, 400);
  expect(c.SHORTS + c.YT_SEARCH + c.EXT).toBe(0);
});

test("largest remainder keeps the total exact", () => {
  const c = allocateParticles({ SHORTS: 0.334, YT_SEARCH: 0.333, EXT: 0.333 }, 10);
  expect(c.SHORTS + c.YT_SEARCH + c.EXT).toBe(10);
});

test("unknown sources do not take a share of the stream", () =>
  expect(allocateParticles({ SHORTS: 0.5, OTHER: 0.5 }, 100)).toEqual({ SHORTS: 100, YT_SEARCH: 0, EXT: 0 }));

test("every drawn lane keeps a legible floor; empty lanes stay empty", () => {
  const c = laneCounts({ SHORTS: 0.95, YT_SEARCH: 0.04, EXT: 0.01 }, 400);
  for (const k of ["SHORTS", "YT_SEARCH", "EXT"] as const) expect(c[k]).toBeGreaterThanOrEqual(MIN_LANE);
  expect(MIN_LANE).toBe(28);
  expect(laneCounts({ SHORTS: 1 }, 400)).toEqual({ SHORTS: 400, YT_SEARCH: 0, EXT: 0 });
});

let reduced = false;
beforeEach(() => {
  reduced = false;
  vi.stubGlobal("location", { search: "" });
  vi.stubGlobal("matchMedia", () => ({ matches: reduced }));
});
afterEach(() => vi.unstubAllGlobals());

function setup(why: string[], shares = 3, subs = 2) {
  const scene = new Scene();
  const stage = { scene, camera: new PerspectiveCamera(16), renderer: { getDrawingBufferSize: (v: Vector2) => v.set(800, 600) } } as unknown as Stage;
  const v = { ...fixture.videos[0], why, shares, subs };
  const ridge = buildRidge(v, fixture.channel.typical_daily.all, 520, 0);
  const w = createWhy(stage, DEFAULT_LOOK, fixture.star.youtube);
  w.show(v, ridge.crest, why[0] ?? null);
  w.update(0.5);
  const points: Points[] = [];
  scene.traverse((o) => o instanceof Points && points.push(o));
  // userData.heads: particles in a layer, not counting the trail points drawn behind each one.
  const heads = (name: string) => points.find((p) => p.name === name)!.userData.heads as number;
  return { w, points, heads };
}

test("every particle layer is never frustum culled", () => {
  const { points } = setup(["shares"]);
  expect(points.length).toBeGreaterThanOrEqual(3);
  for (const p of points) expect(p.frustumCulled).toBe(false);
});

test("sparks and subscriber points follow shares and subs, doubled when they are the reason", () => {
  expect(setup([], 3, 2).heads("sparks")).toBe(135);
  expect(setup([], 9, 2).heads("sparks")).toBe(200);
  expect(setup(["shares"], 3, 2).heads("sparks")).toBe(270);
  expect(setup([], 3, 2).heads("subs")).toBe(28);
  expect(setup(["subs"], 3, 2).heads("subs")).toBe(56);
  expect(setup([], 3, 20).heads("subs")).toBe(120);
});

test("the emphasized stream runs twice as wide and fast", () => {
  const plain = setup([]).points.find((p) => p.name === "stream")!.userData;
  const loud = setup(["search"]).points.find((p) => p.name === "stream")!.userData;
  expect(loud.width.YT_SEARCH).toBe(2 * plain.width.YT_SEARCH);
  expect(loud.speed.YT_SEARCH).toBe(2 * plain.speed.YT_SEARCH);
  expect(loud.speed.SHORTS).toBe(plain.speed.SHORTS);
});

test("reduced motion freezes every particle", () => {
  reduced = true;
  const { w, points } = setup(["shares"]);
  const before = points.map((p) => Array.from(p.geometry.getAttribute("position").array));
  w.update(0.5);
  w.update(1);
  expect(points.map((p) => Array.from(p.geometry.getAttribute("position").array))).toEqual(before);
});

test("hide removes the explanation from view", () => {
  const { w, points } = setup(["search"]);
  w.hide();
  for (let i = 0; i < 30; i++) w.update(0.1);
  for (const p of points) expect(p.visible).toBe(false);
});

import { Box3, type Material, type Object3D } from "three";
import { expect, test } from "vitest";
import { applyLook, buildRidge, dayX, heightOf, ridgeZ } from "./ridges";
import { fixture } from "./fixture";
import { DEFAULT_LOOK } from "./looks";

test("the busiest day reaches full height", () => expect(heightOf(500, 500)).toBe(7));

test("zero views sit on the ground", () => expect(heightOf(0, 500)).toBe(0));

test("days 0..14 span -10..10", () => {
  expect(dayX(0)).toBe(-10);
  expect(dayX(14)).toBe(10);
});

test("the newest ridge is at the front, older ones further back", () => {
  expect(ridgeZ(0)).toBe(0);
  expect(ridgeZ(2)).toBeCloseTo(-3.2);
});

test("a three-day video draws a crest that ends at day 2", () => {
  const v = { ...fixture.videos[0], daily: [0, 410, 520] };
  const r = buildRidge(v, fixture.channel.typical_daily.all, 520, 0);
  expect(r.crest.length).toBeGreaterThanOrEqual(3);
  expect(r.crest.at(-1)!.x).toBeCloseTo(dayX(2));
  expect(r.crest.at(-1)!.y).toBeCloseTo(7);
});

test("the crest never dips below the ground", () => {
  const v = { ...fixture.videos[0], daily: [0, 500, 0, 0, 500] };
  const r = buildRidge(v, fixture.channel.typical_daily.all, 500, 0);
  expect(Math.min(...r.crest.map((p) => p.y))).toBeGreaterThanOrEqual(0);
});

test("state, not position, decides which crest glows", () => {
  const crestOf = (state: "breakout" | "normal") => {
    const r = buildRidge({ ...fixture.videos[0], state }, fixture.channel.typical_daily.all, 520, ridgeZ(3));
    let m: { opacity: number; color: { r: number } } | undefined;
    r.group.traverse((o) => {
      const mat = (o as { material?: { userData: { role?: string; base?: number }; opacity: number; color: { r: number } } }).material;
      if (mat?.userData.role === "crest" && mat.userData.base === 1) m = mat;
    });
    return m!;
  };
  const hot = crestOf("breakout");
  const calm = crestOf("normal");
  expect(hot.opacity).toBeGreaterThan(calm.opacity);
  expect(hot.color.r).toBeGreaterThan(calm.color.r);
});

test("with no retention data the floor line stays subtler than every curtain under the look", () => {
  const v = { ...fixture.videos[0], retention: null, est_from: 5 }; // est_from gives both curtain materials
  const { group } = buildRidge(v, [], 100, 0);
  applyLook(group, DEFAULT_LOOK);
  const op: Record<string, number[]> = {};
  group.traverse((o) => {
    const m = (o as { material?: { userData: { role?: string }; opacity: number } }).material;
    if (m?.userData.role) (op[m.userData.role] ??= []).push(m.opacity);
  });
  expect(op.curtain.length).toBeGreaterThan(0);
  expect(Math.max(...op.floor)).toBeLessThan(Math.min(...op.curtain));
});

const withRole = (r: { group: Object3D }, role: string): Object3D[] => {
  const out: Object3D[] = [];
  r.group.traverse((o) => {
    if ((o as { material?: Material }).material?.userData.role === role) out.push(o);
  });
  return out;
};

test("every crest rises from the ground half a day before day 0", () => {
  const r = buildRidge(fixture.videos[0], fixture.channel.typical_daily.all, 520, 0);
  expect(r.crest[0].x).toBeCloseTo(dayX(-0.5));
  expect(r.crest[0].y).toBe(0);
  expect(r.crest.at(-1)!.x).toBeCloseTo(dayX(6));
});

test("a one-day video is a mountain, not a stroke: ground, then its value", () => {
  const v = { ...fixture.videos[0], age_days: 1, daily: [300, 520], est_from: null };
  const r = buildRidge(v, fixture.channel.typical_daily.all, 520, 0);
  expect(r.crest.length).toBeGreaterThan(3);
  expect(r.crest[0].y).toBe(0);
  expect(r.crest.at(-1)!.y).toBeCloseTo(7);
});

test("a video up to 3 days old gets a live edge at its last crest point and a full 0..14 ghost", () => {
  const v = { ...fixture.videos[0], age_days: 2, daily: [100, 300, 200], est_from: null };
  const r = buildRidge(v, fixture.channel.typical_daily.all, 520, 0);
  const [edge] = withRole(r, "edge");
  expect(edge.position.distanceTo(r.crest.at(-1)!)).toBeCloseTo(0);
  const ghost = new Box3().setFromObject(withRole(r, "ghost")[0]);
  expect(ghost.max.x).toBeCloseTo(dayX(fixture.channel.typical_daily.all.length - 1));
  expect(ghost.min.x).toBeCloseTo(dayX(-0.5));
});

test("an older video has no live edge and its ghost stops where its data stops", () => {
  const r = buildRidge(fixture.videos[0], fixture.channel.typical_daily.all, 520, 0);
  expect(withRole(r, "edge")).toHaveLength(0);
  expect(new Box3().setFromObject(withRole(r, "ghost")[0]).max.x).toBeCloseTo(dayX(6));
});

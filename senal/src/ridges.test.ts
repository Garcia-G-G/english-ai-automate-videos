import { expect, test } from "vitest";
import { buildRidge, dayX, heightOf, ridgeZ } from "./ridges";
import { fixture } from "./fixture";

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

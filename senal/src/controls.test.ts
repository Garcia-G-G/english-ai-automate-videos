import { Color } from "three";
import { expect, test } from "vitest";
import { filterByPeriod, filterByPlatform, nextIndex } from "./controls";
import { fixture } from "./fixture";
import { DEFAULT_LOOK, muted } from "./looks";
import { buildRidge } from "./ridges";

const today = new Date("2026-11-07T08:00:00Z");
const ago = (days: number) => ({ ...fixture.videos[0], published: new Date(today.getTime() - days * 86400e3).toISOString().slice(0, 10) });

test("arrows wrap and start from either end", () => {
  expect(nextIndex(null, "ArrowRight", 5)).toBe(0);
  expect(nextIndex(null, "ArrowLeft", 5)).toBe(4);
  expect(nextIndex(4, "ArrowRight", 5)).toBe(0);
  expect(nextIndex(0, "ArrowLeft", 5)).toBe(4);
  expect(nextIndex(2, "ArrowRight", 5)).toBe(3);
});

test("the period keeps a video published 13 or 14 days ago at 14 and drops 15", () => {
  expect(filterByPeriod([ago(13), ago(14), ago(15)], 14, today)).toHaveLength(2);
  expect(filterByPeriod([ago(15), ago(59), ago(61)], 60, today)).toHaveLength(2);
});

test("an unparseable publication date is dropped", () => expect(filterByPeriod([{ ...ago(1), published: "x" }], 60, today)).toHaveLength(0));

test("the platform filter keeps only that platform", () => {
  expect(filterByPlatform([fixture.videos[0], { ...fixture.videos[1], platform: "tiktok" }], "tiktok")).toHaveLength(1);
});

test("a surviving ridge keeps its colour whichever position or period it is drawn in", () => {
  const colour = (z: number) => {
    const r = buildRidge(fixture.videos[0], fixture.channel.typical_daily.all, 520, z);
    let c = -1;
    r.group.traverse((o) => {
      const m = (o as { material?: { userData: { role?: string; base?: number }; color: Color } }).material;
      if (m?.userData.role === "crest" && m.userData.base === 1) c = m.color.r;
    });
    return c;
  };
  expect(colour(0)).toBe(colour(-9.6));
});

test("stale data drains the colour of the fog and horizon", () => {
  const sat = (hex: string) => new Color(hex).getHSL({ h: 0, s: 0, l: 0 }).s;
  const m = muted(DEFAULT_LOOK);
  expect(sat(m.fogColor)).toBeLessThan(sat(DEFAULT_LOOK.fogColor) / 2);
  expect(sat(m.background.horizon)).toBeLessThan(sat(DEFAULT_LOOK.background.horizon) / 2);
});

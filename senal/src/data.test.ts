import { expect, test } from "vitest";
import { isStale, parsePayload } from "./data";
import { fixture } from "./fixture";

test("a valid payload parses", () => expect(parsePayload(fixture).ok).toBe(true));

test("version 2 is refused with a reason", () => {
  const r = parsePayload({ ...fixture, version: 2 });
  expect(r.ok).toBe(false);
  if (!r.ok) expect(r.reason).toContain("version");
});

test("missing videos array is refused", () => expect(parsePayload({ version: 1 }).ok).toBe(false));

test("non-object input is refused", () => expect(parsePayload(null).ok).toBe(false));

test("daily longer than 15 is refused", () => {
  const long = { ...fixture.videos[0], daily: new Array(16).fill(1) };
  expect(parsePayload({ ...fixture, videos: [long] }).ok).toBe(false);
});

test("a non-numeric daily value is refused", () => {
  const bad = { ...fixture.videos[0], daily: [1, "x"] };
  expect(parsePayload({ ...fixture, videos: [bad] }).ok).toBe(false);
});

test("an unknown state is refused", () => {
  const bad = { ...fixture.videos[0], state: "hot" };
  expect(parsePayload({ ...fixture, videos: [bad] }).ok).toBe(false);
});

test("a star pointing at a missing field is refused", () =>
  expect(parsePayload({ ...fixture, star: {} }).ok).toBe(false));

test("read 49 h ago is stale", () =>
  expect(isStale(fixture, new Date(Date.parse(fixture.read_at) + 49 * 3600e3))).toBe(true));

test("read 47 h ago is fresh", () =>
  expect(isStale(fixture, new Date(Date.parse(fixture.read_at) + 47 * 3600e3))).toBe(false));

test("typical_daily without an 'all' curve is refused", () => {
  const { all: _, ...rest } = fixture.channel.typical_daily;
  expect(parsePayload({ ...fixture, channel: { ...fixture.channel, typical_daily: rest } }).ok).toBe(false);
});

test("typical_cum without an 'all' curve is refused", () => {
  const { all: _, ...rest } = fixture.channel.typical_cum;
  expect(parsePayload({ ...fixture, channel: { ...fixture.channel, typical_cum: rest } }).ok).toBe(false);
});

test("an unparseable read_at is stale", () => expect(isStale({ ...fixture, read_at: "soon" }, new Date())).toBe(true));

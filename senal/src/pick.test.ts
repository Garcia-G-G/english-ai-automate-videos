import { describe, expect, it } from "vitest";
import { pickRidge } from "./pick";

const line = (y: number) => [
  { x: 0, y },
  { x: 100, y },
  { x: 200, y: y + 20 },
];

describe("pickRidge", () => {
  it("returns the ridge whose crest segment is nearest", () => {
    const crests = [line(100), line(200), line(300), line(400)];
    expect(pickRidge({ x: 50, y: 295 }, crests)).toBe(2);
  });

  it("measures distance to the segment, not only its vertices", () => {
    expect(pickRidge({ x: 150, y: 100 }, [line(300), line(100)])).toBe(1);
  });

  it("prefers the front (lower index) ridge on a tie", () => {
    expect(pickRidge({ x: 50, y: 150 }, [line(140), line(160)])).toBe(0);
    expect(pickRidge({ x: 50, y: 150 }, [line(160), line(140)])).toBe(0);
  });

  it("returns null beyond maxPx", () => {
    expect(pickRidge({ x: 50, y: 40 }, [line(80), line(0)])).toBeNull();
    expect(pickRidge({ x: 50, y: 40 }, [line(80)], 50)).toBe(0);
  });

  it("returns null for an empty list and ignores empty crests", () => {
    expect(pickRidge({ x: 0, y: 0 }, [])).toBeNull();
    expect(pickRidge({ x: 0, y: 0 }, [[], [{ x: 3, y: 4 }]])).toBe(1);
  });
});

import { describe, expect, it } from "vitest";
import { nyHour, themeAt } from "./theme";

// Instants given in UTC, so the test passes whatever the machine's own time zone is.
const at = (iso: string) => new Date(iso);

describe("theme by New York time", () => {
  it("switches at 19:00 and 07:00 in winter (EST, UTC−5)", () => {
    expect(themeAt(at("2026-11-14T23:59:00Z"))).toBe("day"); // 18:59 NY
    expect(themeAt(at("2026-11-15T00:00:00Z"))).toBe("night"); // 19:00 NY
    expect(themeAt(at("2026-11-15T11:59:00Z"))).toBe("night"); // 06:59 NY
    expect(themeAt(at("2026-11-15T12:00:00Z"))).toBe("day"); // 07:00 NY
  });

  it("switches at 19:00 and 07:00 in summer (EDT, UTC−4)", () => {
    expect(themeAt(at("2026-07-01T22:59:00Z"))).toBe("day"); // 18:59 NY
    expect(themeAt(at("2026-07-01T23:00:00Z"))).toBe("night"); // 19:00 NY
    expect(themeAt(at("2026-07-02T10:59:00Z"))).toBe("night"); // 06:59 NY
    expect(themeAt(at("2026-07-02T11:00:00Z"))).toBe("day"); // 07:00 NY
  });

  it("handles the daylight-saving switch days", () => {
    // 2026-03-08: clocks go 02:00 → 03:00 in New York.
    expect(nyHour(at("2026-03-08T06:59:00Z"))).toBe(1);
    expect(nyHour(at("2026-03-08T07:00:00Z"))).toBe(3);
    expect(themeAt(at("2026-03-08T11:00:00Z"))).toBe("day"); // 07:00 EDT
    // 2026-11-01: clocks go 02:00 → 01:00.
    expect(themeAt(at("2026-11-01T11:59:00Z"))).toBe("night"); // 06:59 EST
    expect(themeAt(at("2026-11-01T12:00:00Z"))).toBe("day"); // 07:00 EST
    // 2027 switch days.
    expect(themeAt(at("2027-03-14T11:00:00Z"))).toBe("day");
    expect(themeAt(at("2027-11-07T23:59:00Z"))).toBe("day");
    expect(themeAt(at("2027-11-08T00:00:00Z"))).toBe("night");
  });

  it("gives Costa Rica (UTC−6) the New York answer, not its own clock", () => {
    // 18:30 in Costa Rica on 14 Nov is 19:30 in New York: night already.
    expect(themeAt(at("2026-11-15T00:30:00Z"))).toBe("night");
  });
});

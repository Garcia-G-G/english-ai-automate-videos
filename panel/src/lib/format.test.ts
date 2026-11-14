import { describe, expect, it } from "vitest";
import { change, greeting, n, shortDate } from "./format";

describe("format", () => {
  it("formats numbers like the channel", () => expect(n(47488)).toBe("47,488"));
  it("reads ISO dates without a time-zone shift", () => expect(shortDate("2026-10-19")).toBe("19 oct"));
  it("describes change against the previous period", () => {
    expect(change(47488, 1528)).toEqual({ label: "×31", down: false });
    expect(change(145, 100)).toEqual({ label: "+45 %", down: false });
    expect(change(88, 100)).toEqual({ label: "−12 %", down: true });
    expect(change(10, null)).toBeNull();
    expect(change(10, 0)).toBeNull();
  });
  it("greets by Costa Rica time", () => {
    expect(greeting(new Date("2026-11-14T14:00:00Z"))).toBe("Buenos días"); // 08:00 CR
    expect(greeting(new Date("2026-11-14T20:00:00Z"))).toBe("Buenas tardes"); // 14:00 CR
    expect(greeting(new Date("2026-11-15T02:00:00Z"))).toBe("Buenas noches"); // 20:00 CR
  });
});

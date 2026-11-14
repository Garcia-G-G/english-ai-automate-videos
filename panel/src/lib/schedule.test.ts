import { describe, expect, it } from "vitest";
import type { ScheduleInfo } from "../api/contract";
import { checkTime, localParts, longLabel, nextDays, takenAt, toISO } from "./schedule";

const info: ScheduleInfo = {
  tz: "America/Costa_Rica",
  utcOffset: "-06:00",
  slots: ["08:30", "12:00", "16:00", "19:30"],
  taken: [
    { at: "2026-11-14T08:30:00-06:00", title: "MÉDICO" },
    { at: "2026-11-14T12:00:00-06:00", title: "YA LO RESOLVÍ" },
    { at: "2026-11-14T16:00:00-06:00", title: "Test FAMILIA" },
    { at: "2026-11-14T19:30:00-06:00", title: "MÁS ANIMALES" },
  ],
  minLeadMin: 15,
  spacingH: 2.5,
  maxPerDay: 4,
  next: "2026-11-15T08:30:00-06:00",
};
const now = new Date("2026-11-14T17:00:00-06:00");

describe("free scheduling", () => {
  it("builds Costa Rica times and reads them back", () => {
    const iso = toISO("2026-11-14", "21:15", info);
    expect(iso).toBe("2026-11-14T21:15:00-06:00");
    expect(localParts(iso, info)).toEqual({ date: "2026-11-14", time: "21:15" });
    expect(longLabel(iso, info)).toBe("sábado 14 nov a las 21:15");
  });

  it("lists today, tomorrow and the next days, across a month end", () => {
    const d = nextDays(new Date("2026-11-29T22:00:00-06:00"), info, 4);
    expect(d.map((x) => x.label)).toEqual(["Hoy", "Mañana", "mar 1 dic", "mié 2 dic"]);
    expect(d[2]?.date).toBe("2026-12-01");
  });

  it("uses Costa Rica's date even when it is already tomorrow in UTC", () => {
    expect(nextDays(new Date("2026-11-15T03:00:00Z"), info, 1)[0]?.date).toBe("2026-11-14");
  });

  it("blocks only times in the past or too soon", () => {
    expect(checkTime("2026-11-14T16:30:00-06:00", info, now).error).toMatch(/ya pasó/);
    expect(checkTime("2026-11-14T17:10:00-06:00", info, now).error).toMatch(/15 min/);
    expect(checkTime("2026-11-16T10:00:00-06:00", info, now)).toEqual({ error: null, warnings: [] });
  });

  it("warns, without blocking, about spacing and a fifth video", () => {
    const r = checkTime("2026-11-14T21:15:00-06:00", info, now);
    expect(r.error).toBeNull();
    expect(r.warnings).toEqual(["A 1 h 45 min de «MÁS ANIMALES» (lo normal: 2,5 h).", "Sería el 5.º vídeo de ese día (lo normal: 4)."]);
    expect(checkTime("2026-11-14T19:30:00-06:00", info, now).warnings[0]).toBe("A la misma hora que «MÁS ANIMALES».");
  });

  it("knows which usual slots are taken", () => {
    expect(takenAt("2026-11-14", "16:00", info)).toBe("Test FAMILIA");
    expect(takenAt("2026-11-15", "16:00", info)).toBeNull();
  });
});

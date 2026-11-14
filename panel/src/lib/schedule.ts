import type { ScheduleInfo } from "../api/contract";

/**
 * Free scheduling in Costa Rica time (UTC−06:00, no daylight saving).
 * Garcia can pick any day and any minute; the usual slots are suggestions.
 * Only one hard rule: the time must be at least `minLeadMin` ahead.
 */

const parts = (at: Date, tz: string) => {
  const f = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const p = Object.fromEntries(f.formatToParts(at).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, time: `${p.hour}:${p.minute}` };
};

/** The local date (yyyy-mm-dd) and time (HH:MM) of an instant, in the schedule's zone. */
export const localParts = (at: Date | string, info: Pick<ScheduleInfo, "tz">) => parts(typeof at === "string" ? new Date(at) : at, info.tz);

/** «2026-11-14» + «21:15» → «2026-11-14T21:15:00-06:00». */
export const toISO = (date: string, time: string, info: Pick<ScheduleInfo, "utcOffset">) => `${date}T${time}:00${info.utcOffset}`;

const DOW = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const DOW_LONG = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
const MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const dowOf = (date: string) => new Date(`${date}T12:00:00Z`).getUTCDay();
const addDays = (date: string, k: number) => {
  const d = new Date(`${date}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + k);
  return d.toISOString().slice(0, 10);
};

/** The next `count` days, starting today in the schedule's zone, with short Spanish labels. */
export function nextDays(now: Date, info: Pick<ScheduleInfo, "tz">, count = 7): { date: string; label: string }[] {
  const today = parts(now, info.tz).date;
  return Array.from({ length: count }, (_, k) => {
    const date = addDays(today, k);
    const [, m, d] = date.split("-").map(Number);
    const label = k === 0 ? "Hoy" : k === 1 ? "Mañana" : `${DOW[dowOf(date)]} ${d} ${MES[(m ?? 1) - 1]}`;
    return { date, label };
  });
}

/** «sábado 14 nov a las 21:15». */
export function longLabel(iso: string, info: Pick<ScheduleInfo, "tz">): string {
  const { date, time } = localParts(iso, info);
  const [, m, d] = date.split("-").map(Number);
  return `${DOW_LONG[dowOf(date)]} ${d} ${MES[(m ?? 1) - 1]} a las ${time}`;
}

const fmtGap = (min: number) => {
  const h = Math.floor(min / 60);
  const mm = Math.round(min % 60);
  return h ? `${h} h${mm ? ` ${mm} min` : ""}` : `${mm} min`;
};

/** The one error (blocks) and the warnings (inform) for a chosen time. */
export function checkTime(iso: string, info: ScheduleInfo, now: Date): { error: string | null; warnings: string[] } {
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return { error: "Esa fecha u hora no es válida.", warnings: [] };
  const lead = (at - now.getTime()) / 60000;
  if (lead < info.minLeadMin) {
    return { error: lead < 0 ? "Esa hora ya pasó. Elige una hora futura." : `Tiene que ser al menos ${info.minLeadMin} min en el futuro, para que YouTube lo acepte.`, warnings: [] };
  }
  const warnings: string[] = [];
  let closest: { gap: number; title: string } | null = null;
  for (const t of info.taken) {
    const gap = Math.abs(new Date(t.at).getTime() - at) / 60000;
    if (!closest || gap < closest.gap) closest = { gap, title: t.title };
  }
  if (closest && closest.gap < info.spacingH * 60) {
    warnings.push(closest.gap < 1 ? `A la misma hora que «${closest.title}».` : `A ${fmtGap(closest.gap)} de «${closest.title}» (lo normal: ${String(info.spacingH).replace(".", ",")} h).`);
  }
  const day = localParts(iso, info).date;
  const sameDay = info.taken.filter((t) => localParts(t.at, info).date === day).length + 1;
  if (sameDay > info.maxPerDay) warnings.push(`Sería el ${sameDay}.º vídeo de ese día (lo normal: ${info.maxPerDay}).`);
  return { error: null, warnings };
}

/** Which usual slots of a day are already taken, to show them as such. */
export function takenAt(date: string, time: string, info: ScheduleInfo): string | null {
  const hit = info.taken.find((t) => {
    const p = localParts(t.at, info);
    return p.date === date && p.time === time;
  });
  return hit ? hit.title : null;
}

/** Numbers the way the channel shows them: 1,601. Missing values are «sin dato». */
export const n = (v: number) => v.toLocaleString("en-US");
export const usd = (v: number | null) => (v === null ? "sin dato" : `$${v.toFixed(2)}`);
export const NA = "sin dato";

const MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
/** «19 oct» from an ISO date (yyyy-mm-dd), without time-zone surprises. */
export function shortDate(iso: string): string {
  const [, m, d] = iso.split("-").map(Number);
  return `${d} ${MES[(m ?? 1) - 1]}`;
}

/** «×31», «+45 %» or «−12 %»: the change against the previous period. */
export function change(now: number, prev: number | null): { label: string; down: boolean } | null {
  if (prev === null || prev <= 0) return null;
  const r = now / prev;
  if (r >= 2) return { label: `×${Math.round(r)}`, down: false };
  const pct = Math.round((r - 1) * 100);
  return { label: `${pct >= 0 ? "+" : "−"}${Math.abs(pct)} %`, down: pct < 0 };
}

const greet = new Intl.DateTimeFormat("en-US", { timeZone: "America/Costa_Rica", hour: "numeric", hourCycle: "h23" });
/** Greeting by Costa Rica time (Garcia's clock). */
export function greeting(at = new Date()): string {
  const h = Number(greet.format(at)) % 24;
  return h < 12 && h >= 5 ? "Buenos días" : h < 19 && h >= 12 ? "Buenas tardes" : "Buenas noches";
}
export function todayLabel(at = new Date()): string {
  return new Intl.DateTimeFormat("es", { timeZone: "America/Costa_Rica", weekday: "long", day: "numeric", month: "short" }).format(at);
}

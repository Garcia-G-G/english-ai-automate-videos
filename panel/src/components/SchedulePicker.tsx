import { useEffect, useMemo, useState } from "react";
import { CalendarDays, Clock, TriangleAlert } from "lucide-react";
import type { ScheduleInfo } from "../api/contract";
import { checkTime, localParts, longLabel, nextDays, takenAt, toISO } from "../lib/schedule";

/**
 * Pick ANY day and ANY minute (Garcia, 14 Nov). The usual slots are one tap,
 * but «Otra hora» and «Otro día» accept anything. Only a past or too-soon time
 * is refused; spacing and the per-day count are shown as warnings.
 */
export function SchedulePicker({ info, value, onChange }: { info: ScheduleInfo; value: string; onChange: (iso: string, ok: boolean) => void }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);
  const days = useMemo(() => nextDays(now, info, 7), [now, info]);
  const { date, time } = localParts(value, info);
  const check = checkTime(value, info, now);
  useEffect(() => onChange(value, check.error === null), [check.error]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (d: string, t: string) => {
    const iso = toISO(d, t, info);
    onChange(iso, checkTime(iso, info, now).error === null);
  };
  const inDays = days.some((d) => d.date === date);
  return (
    <div className="sched">
      <div className="sched-row" role="group" aria-label="Día">
        <CalendarDays aria-hidden="true" size={16} className="sched-ic" />
        {days.map((d) => (
          <button key={d.date} type="button" className={`pchip${d.date === date ? " on" : ""}`} aria-pressed={d.date === date} onClick={() => set(d.date, time)}>{d.label}</button>
        ))}
        <label className={`pchip pinput${!inDays ? " on" : ""}`}>
          <span>Otro día</span>
          <input type="date" value={date} min={days[0]?.date} onChange={(e) => e.target.value && set(e.target.value, time)} aria-label="Elegir otro día" />
        </label>
      </div>
      <div className="sched-row" role="group" aria-label="Hora">
        <Clock aria-hidden="true" size={16} className="sched-ic" />
        {info.slots.map((s) => {
          const who = takenAt(date, s, info);
          const past = checkTime(toISO(date, s, info), info, now).error !== null;
          return (
            <button key={s} type="button" className={`pchip${s === time ? " on" : ""}${who || past ? " dim" : ""}`} aria-pressed={s === time}
              title={who ? `Ocupado: ${who}` : past ? "Ya pasó" : undefined} onClick={() => set(date, s)}>
              {s}{who ? " · ocupado" : ""}
            </button>
          );
        })}
        <label className={`pchip pinput${!info.slots.includes(time) ? " on" : ""}`}>
          <span>Otra hora</span>
          <input type="time" step={300} value={time} onChange={(e) => e.target.value && set(date, e.target.value)} aria-label="Elegir otra hora" />
        </label>
      </div>
      <div className={`sched-sum${check.error ? " bad" : ""}`} aria-live="polite">
        {check.error ? (
          <><TriangleAlert size={16} aria-hidden="true" /> {check.error}</>
        ) : (
          <>Sale el <b>{longLabel(value, info)}</b> <small>(hora de Costa Rica)</small></>
        )}
      </div>
      {check.warnings.map((w) => <div key={w} className="sched-warn"><TriangleAlert size={14} aria-hidden="true" /> {w} <small>Puedes seguir igual.</small></div>)}
    </div>
  );
}

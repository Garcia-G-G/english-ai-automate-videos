import { useEffect, useRef, useState } from "react";
import { n, shortDate } from "../lib/format";
import { reducedMotion } from "../lib/store";

/** Counts up from 0 once, in 1.1 s with an ease-out cubic. Instant under reduced motion. */
export function CountUp({ to, format = n }: { to: number; format?: (v: number) => string }) {
  const [v, setV] = useState(() => (reducedMotion() ? to : 0));
  const from = useRef(0);
  useEffect(() => {
    if (reducedMotion()) return setV(to);
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const step = (t: number) => {
      const p = Math.min(1, (t - start) / 1100);
      const e = 1 - Math.pow(1 - p, 3);
      setV(Math.round(a + (to - a) * e));
      if (p < 1) raf = requestAnimationFrame(step);
      else from.current = to;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [to]);
  return <>{format(v)}</>;
}

interface Point { date: string; views: number; uploads: number }

/**
 * Daily views as an area with a drawn line. The SVG stretches to its box, so
 * every label lives in HTML on top of it (no squashed text).
 */
export function AreaChart({ data, height = 120 }: { data: Point[]; height?: number }) {
  if (data.length < 2) return <div className="na" style={{ height }}>sin dato</div>;
  const W = 1000;
  const H = 100;
  const max = Math.max(...data.map((d) => d.views), 1) * 1.12;
  const xy = data.map((d, i) => [(i / (data.length - 1)) * W, H - (d.views / max) * H] as const);
  const line = "M" + xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" L");
  const pi = data.reduce((b, d, i) => (d.views > (data[b]?.views ?? 0) ? i : b), 0);
  const [px, py] = xy[pi] ?? [0, 0];
  const first = data[0]!;
  const last = data[data.length - 1]!;
  return (
    <div style={{ position: "relative" }}>
      <svg className="chart" style={{ height }} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
        aria-label={`Vistas por día del ${shortDate(first.date)} al ${shortDate(last.date)}; pico de ${n(data[pi]!.views)} el ${shortDate(data[pi]!.date)}`}>
        <path className="ar" d={`${line} L${W},${H} L0,${H} Z`} />
        <path className="ln draw" d={line} pathLength={1} />
        {data.map((d, i) =>
          d.uploads > 0 ? <rect key={d.date} className="up" x={(i / (data.length - 1)) * W - 3} y={H + 4} width={6} height={Math.min(d.uploads, 8) * 1.6 + 2} rx={2} /> : null,
        )}
      </svg>
      <span className="peakdot" style={{ left: `${(px / W) * 100}%`, top: (py / H) * height }} />
      <span className="peak" style={{ left: `${Math.min(88, Math.max(12, (px / W) * 100))}%`, top: (py / H) * height }}>
        {n(data[pi]!.views)} · {shortDate(data[pi]!.date)}
      </span>
      <div className="axr" style={{ marginTop: 18 }}>
        <span>{shortDate(first.date)}</span>
        <span>▮ vídeos subidos ese día</span>
        <span>{shortDate(last.date)}</span>
      </div>
    </div>
  );
}

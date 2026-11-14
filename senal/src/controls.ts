import type { Video } from "./data";

export type Period = 14 | 28 | 60;
export const PERIODS: Period[] = [14, 28, 60];
const DAY_MS = 86400e3;

/** Previous or next index, wrapping; with nothing selected, Right starts at the first and Left at the last. */
export function nextIndex(current: number | null, key: "ArrowLeft" | "ArrowRight", count: number): number {
  const step = key === "ArrowRight" ? 1 : -1;
  if (current === null) return step === 1 ? 0 : count - 1;
  return (current + step + count) % count;
}

/** Whole days since publication (UTC midnight to midnight) at `today`. */
const daysSince = (v: Video, today: Date): number => Math.floor((today.getTime() - Date.parse(v.published)) / DAY_MS);

/** Keeps videos published at most `days` days before `today`; an unparseable date is dropped. */
export const filterByPeriod = (videos: Video[], days: Period, today: Date): Video[] => videos.filter((v) => daysSince(v, today) <= days);

export const filterByPlatform = (videos: Video[], p: string): Video[] => videos.filter((v) => v.platform === p);

export interface BarHandlers {
  onPlatform(platform: string): void;
  onPeriod(days: Period): void;
  onStar(): void;
  onNumbers(on: boolean): void;
}

const STYLE = `
#senal-bar{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);display:flex;gap:4px;padding:4px;border-radius:999px;background:rgba(5,7,15,.55);border:1px solid rgba(223,230,255,.12);backdrop-filter:blur(6px)}
#senal-bar button{all:unset;box-sizing:border-box;width:40px;height:40px;display:grid;place-items:center;border-radius:50%;color:#dfe6ff;opacity:.55;cursor:pointer;transition:opacity .15s}
#senal-bar button:hover{opacity:.9}
#senal-bar button[aria-pressed="true"]{opacity:1;background:rgba(223,230,255,.14)}
#senal-bar button:focus-visible{opacity:1;outline:2px solid #dfe6ff;outline-offset:2px}
#senal-bar svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
`;
const SVG = (inner: string) => `<svg viewBox="0 0 24 24" aria-hidden="true">${inner}</svg>`;
const ICON = {
  youtube: SVG('<rect x="3" y="6" width="18" height="12" rx="4"/><path d="M10 9.5v5l4.5-2.5z"/>'),
  other: SVG('<circle cx="12" cy="12" r="7"/>'),
  star: SVG('<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 17l-5.2 2.7 1-5.9-4.3-4.1 5.9-.8z"/>'),
  numbers: SVG('<path d="M7 5L5 19M15 5l-2 14M4 9h16M3.5 15h16"/>'),
};
const periodIcon = (n: number) => SVG(Array.from({ length: n }, (_, i) => `<path d="M${12 + (i - (n - 1) / 2) * 5} 6v12"/>`).join(""));

/** Icon-only bar; the buttons carry Spanish aria-labels and a visible focus ring. */
export function mountBar(root: HTMLElement, platforms: string[], on: BarHandlers): void {
  document.getElementById("senal-bar")?.remove();
  if (!document.getElementById("senal-bar-style")) {
    const s = Object.assign(document.createElement("style"), { id: "senal-bar-style", textContent: STYLE });
    document.head.append(s);
  }
  const bar = Object.assign(document.createElement("div"), { id: "senal-bar" });
  bar.setAttribute("role", "toolbar");
  bar.setAttribute("aria-label", "Controles de Señal");
  const button = (html: string, label: string, click: (b: HTMLButtonElement) => void, pressed?: boolean) => {
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = html;
    b.setAttribute("aria-label", label);
    if (pressed !== undefined) b.setAttribute("aria-pressed", String(pressed));
    b.addEventListener("click", () => click(b));
    bar.append(b);
    return b;
  };

  const platformButtons = platforms.map((p, i) =>
    button(p === "youtube" ? ICON.youtube : ICON.other, `Plataforma: ${p === "youtube" ? "YouTube" : p}`, () => {
      platformButtons.forEach((b, k) => b.setAttribute("aria-pressed", String(k === i)));
      on.onPlatform(p);
    }, i === 0),
  );
  let period = 0;
  const periodLabel = () => `Periodo: últimos ${PERIODS[period]} días. Pulsa para cambiar`;
  button(periodIcon(1), periodLabel(), (b) => {
    period = (period + 1) % PERIODS.length;
    b.innerHTML = periodIcon(period + 1);
    b.setAttribute("aria-label", periodLabel());
    on.onPeriod(PERIODS[period]);
  });
  button(ICON.star, "Ir al video destacado", () => on.onStar());
  button(ICON.numbers, "Modo cifras", (b) => {
    const next = b.getAttribute("aria-pressed") !== "true";
    b.setAttribute("aria-pressed", String(next));
    on.onNumbers(next);
  }, false);
  root.append(bar);
}

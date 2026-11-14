import type { Video } from "./data";

const STYLE = `
#senal-numbers{position:fixed;left:0;top:0;pointer-events:none;display:none;padding:8px 12px;border-radius:8px;background:rgba(5,7,15,.72);border:1px solid rgba(223,230,255,.14);color:#dfe6ff;font:500 14px/1.5 "Inter Variable",system-ui,sans-serif;font-variant-numeric:tabular-nums;white-space:nowrap}
#senal-numbers div:first-child{font-size:20px;font-weight:600}
`;
let box: HTMLDivElement | null = null;
let shownId: string | null = null;
let readAt: string | null = null;

const fmt = new Intl.NumberFormat("es");
const lines = (v: Video): string[] => [
  `${fmt.format(v.views)} vistas`,
  v.retention === null ? "Sin dato de % visto" : `${fmt.format(Math.round(v.retention * 10) / 10)} % visto`,
  `${v.age_days === 1 ? "1 día" : `${v.age_days} días`} desde que se publicó`,
  ...(readAt ? [`Datos leídos el ${new Date(readAt).toLocaleDateString("es", { day: "numeric", month: "long", year: "numeric" })}`] : []),
];

/** When set (stale data), numbers mode also shows the read date. */
export const setStaleRead = (iso: string | null): void => {
  readAt = iso;
  shownId = null;
};

/** Views, retention and age beside the chosen video; `anchor` is in CSS pixels from the page's top-left. Safe to call every frame. */
export function showNumbers(v: Video, anchor: { x: number; y: number }): void {
  if (!box) {
    document.head.append(Object.assign(document.createElement("style"), { textContent: STYLE }));
    box = Object.assign(document.createElement("div"), { id: "senal-numbers" });
    box.setAttribute("aria-hidden", "true"); // the hidden table carries the same numbers for screen readers
    document.body.append(box);
  }
  if (shownId !== v.id) {
    box.replaceChildren(...lines(v).map((t) => Object.assign(document.createElement("div"), { textContent: t })));
    shownId = v.id;
  }
  box.style.display = "block";
  const w = box.offsetWidth;
  const h = box.offsetHeight;
  const x = Math.min(Math.max(8, anchor.x + 14), innerWidth - w - 8);
  const y = Math.min(Math.max(8, anchor.y - h - 14), innerHeight - h - 8);
  box.style.transform = `translate(${x}px,${y}px)`;
}

export function hideNumbers(): void {
  if (box) box.style.display = "none";
}

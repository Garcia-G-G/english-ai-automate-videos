import type { Video } from "./data";

const STYLE = `#senal-table{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}`;

const cell = (tag: "th" | "td", text: string): HTMLTableCellElement => Object.assign(document.createElement(tag), { textContent: text });

/** Visually hidden table with the numbers behind every ridge, newest first; replaces the previous one. */
export function renderTable(root: HTMLElement, videos: Video[]): void {
  if (!document.getElementById("senal-table-style")) document.head.append(Object.assign(document.createElement("style"), { id: "senal-table-style", textContent: STYLE }));
  const table = Object.assign(document.createElement("table"), { id: "senal-table" });
  table.append(Object.assign(document.createElement("caption"), { textContent: "Videos recientes: vistas, porcentaje visto y edad" }));
  const head = table.createTHead().insertRow();
  for (const h of ["Plataforma", "Formato", "Publicado", "Edad en días", "Vistas", "Porcentaje visto"]) head.append(Object.assign(cell("th", h), { scope: "col" }));
  const body = table.createTBody();
  for (const v of videos) {
    const row = body.insertRow();
    row.append(cell("td", v.platform), cell("td", v.format.replaceAll("_", " ")), cell("td", v.published), cell("td", String(v.age_days)), cell("td", String(v.views)), cell("td", v.retention === null ? "sin dato" : `${v.retention} %`));
  }
  root.querySelector("#senal-table")?.remove();
  root.append(table);
}

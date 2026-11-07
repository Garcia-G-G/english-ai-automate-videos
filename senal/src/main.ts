import { parsePayload, type Payload } from "./data";
import { lookFromQuery, type Look } from "./looks";
import { buildRidge, DAYS, ridgeZ, type LineRole } from "./ridges";
import { createStage } from "./scene";
import { showError, showLoading } from "./states";

const root = document.getElementById("app")!;
const fail = (reason: string) =>
  showError(root, `No pude leer los datos de Señal: ${reason}. Pulsa «Actualizar estadísticas» en el panel.`);

async function load(): Promise<void> {
  const stop = showLoading(root);
  try {
    const res = await fetch("./senal.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const parsed = parsePayload(await res.json());
    stop();
    if (!parsed.ok) return fail(parsed.reason);
    draw(parsed.data, lookFromQuery(location.search));
  } catch (e) {
    stop();
    fail(e instanceof Error ? e.message : String(e));
  }
}

/** A still of every ridge published in the last DAYS days, newest at the front. */
function draw(p: Payload, look: Look): void {
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "display:block;width:100vw;height:100vh";
  root.replaceChildren(canvas);
  const stage = createStage(canvas, look);
  const recent = p.videos.filter((v) => v.age_days <= DAYS).sort((a, b) => a.age_days - b.age_days);
  const maxDaily = Math.max(1, ...recent.flatMap((v) => v.daily));
  const width: Record<LineRole, number> = { crest: look.crestWidth, ghost: look.ghostWidth, curtain: look.hairWidth };
  recent.forEach((v, i) => {
    const typical = p.channel.typical_daily[v.format] ?? p.channel.typical_daily.all;
    const r = buildRidge(v, typical, maxDaily, ridgeZ(i));
    r.group.traverse((o) => {
      const m = (o as { material?: { userData: { role?: LineRole }; linewidth: number } }).material;
      if (m?.userData.role) m.linewidth = width[m.userData.role];
    });
    stage.scene.add(r.group);
  });
  stage.render();
}

void load();

import { parsePayload } from "./data";
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
    // Task 4 draws the scene from parsed.data; for now a blank canvas.
    root.replaceChildren(document.createElement("canvas"));
  } catch (e) {
    stop();
    fail(e instanceof Error ? e.message : String(e));
  }
}

void load();

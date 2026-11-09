import { Vector3 } from "three";
import { createRig, reducedMotion, type Rig } from "./camera";
import { parsePayload, type Payload, type Video } from "./data";
import { DEFAULT_LOOK, type Look } from "./looks";
import { playOpening } from "./opening";
import { pickRidge } from "./pick";
import { applyLook, buildRidge, DAYS, REST_DIM, ridgeZ, type RidgeObject } from "./ridges";
import { createStage, type Stage } from "./scene";
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
    draw(parsed.data, DEFAULT_LOOK);
  } catch (e) {
    stop();
    fail(e instanceof Error ? e.message : String(e));
  }
}

const CLICK_SLOP_PX = 4; // a press that moves further is a drag, not a click

/** Every ridge published in the last DAYS days, newest at the front; hover lights one, click flies to it. */
function draw(p: Payload, look: Look): void {
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "display:block;width:100vw;height:100vh";
  root.replaceChildren(canvas);
  const stage = createStage(canvas, look);
  const recent = p.videos.filter((v) => v.age_days <= DAYS).sort((a, b) => a.age_days - b.age_days);
  const maxDaily = Math.max(1, ...recent.flatMap((v) => v.daily));
  const drawn: Vector3[] = [];
  const ridges: RidgeObject[] = recent.map((v, i) => {
    const typical = p.channel.typical_daily[v.format] ?? p.channel.typical_daily.all;
    const r = buildRidge(v, typical, maxDaily, ridgeZ(i));
    applyLook(r.group, look);
    // Frame the drawn crests and the ground under them, not the full 0..DAYS floor lines.
    for (const pt of r.crest) drawn.push(pt, pt.clone().setY(0));
    stage.scene.add(r.group);
    return r;
  });
  if (drawn.length) stage.frame(drawn);
  const rig = createRig(stage, canvas);
  const start = wire(canvas, stage.camera, recent, ridges, rig);

  let raf = 0;
  const loop = () => {
    stage.render();
    raf = requestAnimationFrame(loop);
  };
  loop();
  document.addEventListener("visibilitychange", () => {
    cancelAnimationFrame(raf);
    if (!document.hidden) loop();
  });

  const starAt = recent.findIndex((v) => v.id === p.star.youtube);
  const star = starAt < 0 ? null : starAt;
  void playOpening(ridges, rig, star, reducedMotion(), () => start(star)).then(() => start(null));
}

/** Hover, click and double-click all select through pickRidge. Inert until the returned start(selection) is called; later calls are ignored. */
function wire(canvas: HTMLCanvasElement, camera: Stage["camera"], videos: Video[], ridges: RidgeObject[], rig: Rig): (star: number | null) => void {
  // Engine verdict at rest: breakout and second wind lit, the rest dimmed (same rule as buildRidge).
  const lit = videos.map((v) => v.state === "breakout" || v.state === "second_wind");
  let ready = false;
  let hovered: number | null = null;
  let selected: number | null = null;

  /** One ridge glows and every other dims; null restores the resting verdict. */
  const emphasize = (focus: number | null) =>
    ridges.forEach((r, i) => {
      const on = focus === null ? lit[i] : i === focus;
      r.setDim(on ? 0 : focus === null ? REST_DIM : 1);
      r.setGlow(on ? 1 : 0);
    });

  /** Ridges in front of the selected one sit near the camera in its close-up and slash across it: hide them. */
  const clearFront = () => ridges.forEach((r, i) => (r.group.visible = selected === null || i >= selected));

  const pick = (e: MouseEvent): number | null => {
    const v = new Vector3();
    const w = canvas.clientWidth / 2;
    const h = canvas.clientHeight / 2;
    const screen = ridges.map((r) =>
      !r.group.visible ? [] : r.crest.flatMap((pt) => {
        v.copy(pt).project(camera);
        return v.z > 1 ? [] : [{ x: (v.x + 1) * w, y: (1 - v.y) * h }]; // behind the camera: skip
      }),
    );
    return pickRidge({ x: e.offsetX, y: e.offsetY }, screen);
  };

  const select = (i: number) => {
    selected = i;
    emphasize(i);
    clearFront();
    void rig.focus(ridges[i].crest);
  };
  // The stage only updates the overview on resize; keep whatever the user was looking at.
  addEventListener("resize", () => void (selected === null ? rig.overview(0) : rig.focus(ridges[selected].crest, 0)));

  canvas.addEventListener("pointermove", (e) => {
    if (!ready || e.buttons) return;
    const i = pick(e);
    if (i === hovered) return;
    hovered = i;
    canvas.style.cursor = i === null ? "" : "pointer";
    emphasize(i ?? selected);
  });
  canvas.addEventListener("pointerleave", () => {
    if (!ready || hovered === null) return;
    hovered = null;
    canvas.style.cursor = "";
    emphasize(selected);
  });
  let down = { x: 0, y: 0 };
  canvas.addEventListener("pointerdown", (e) => (down = { x: e.offsetX, y: e.offsetY }));
  canvas.addEventListener("click", (e) => {
    if (!ready || Math.hypot(e.offsetX - down.x, e.offsetY - down.y) > CLICK_SLOP_PX) return;
    const i = pick(e);
    if (i !== null) select(i);
  });
  canvas.addEventListener("dblclick", (e) => {
    if (!ready || pick(e) !== null) return;
    selected = null;
    clearFront();
    emphasize(hovered);
    void rig.overview();
  });
  return (star) => {
    if (ready) return;
    ready = true;
    selected = star;
    clearFront();
    if (star !== null) emphasize(star);
  };
}

void load();

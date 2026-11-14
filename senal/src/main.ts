import "@fontsource-variable/inter";
import { Vector3 } from "three";
import { createRig, reducedMotion, type Rig } from "./camera";
import { renderTable } from "./a11y";
import { filterByPeriod, filterByPlatform, mountBar, nextIndex, type Period } from "./controls";
import { isStale, parsePayload, type Payload, type Video } from "./data";
import { DEFAULT_LOOK, muted, type Look } from "./looks";
import { hideNumbers, setStaleRead, showNumbers } from "./numbers";
import { playOpening } from "./opening";
import { pickRidge } from "./pick";
import { applyLook, buildRidge, DAYS, disposeRidge, REST_DIM, ridgeZ, type RidgeObject } from "./ridges";
import { createStage } from "./scene";
import { showEmpty, showError, showLoading } from "./states";
import { createWhy } from "./why";

const root = document.getElementById("app")!;
const fail = (reason: string) =>
  showError(root, `No pude leer los datos de Señal: ${reason}. Pulsa «Actualizar estadísticas» en el panel.`);

async function load(): Promise<void> {
  const stop = showLoading(root);
  try {
    // ?data=<url> swaps the file for testing broken or stale payloads; the production build ignores it.
    const url = (import.meta.env.DEV && new URLSearchParams(location.search).get("data")) || "./senal.json";
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`el servidor respondió ${res.status}`);
    const parsed = parsePayload(await res.json().catch(() => null));
    stop();
    if (!parsed.ok) return fail(parsed.reason);
    draw(parsed.data, DEFAULT_LOOK);
  } catch (e) {
    stop();
    fail(e instanceof Error ? e.message : String(e));
  }
}

const CLICK_SLOP_PX = 4; // a press that moves further is a drag, not a click

/** Ridges for the chosen platform and period, newest at the front; hover lights one, click or arrows fly to it. */
function draw(p: Payload, baseLook: Look): void {
  const stale = isStale(p, new Date());
  const look = stale ? muted(baseLook) : baseLook;
  setStaleRead(stale ? p.read_at : null);
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "display:block;width:100vw;height:100vh";
  root.replaceChildren(canvas);
  const stage = createStage(canvas, look);
  const rig = createRig(stage, canvas);
  const why = createWhy(stage, look);
  const camera = stage.camera;
  // Ages are counted from the day the data was read, so a stale file does not empty its own landscape.
  const readAt = new Date(p.read_at);
  const today = Number.isNaN(readAt.getTime()) ? new Date() : readAt;

  let platform = p.platforms[0] ?? "youtube";
  let period: Period = DAYS;
  let videos: Video[] = [];
  let ridges: RidgeObject[] = [];
  let lit: boolean[] = [];
  let noStar = true;
  let ready = false;
  let hovered: number | null = null;
  let selected: number | null = null;
  let numbersButton = false;
  let altDown = false;

  /** One ridge glows and every other dims; null restores the resting verdict (every ridge equal when there is no star). */
  const emphasize = (focus: number | null) =>
    ridges.forEach((r, i) => {
      const on = focus === null ? !noStar && lit[i] : i === focus;
      r.setDim(on || (focus === null && noStar) ? 0 : focus === null ? REST_DIM : 1);
      r.setGlow(on ? 1 : 0);
    });

  /** Ridges in front of the selected one sit near the camera in its close-up and slash across it: hide them. */
  const clearFront = () => ridges.forEach((r, i) => (r.group.visible = selected === null || i >= selected));

  const starId = () => p.star[platform] ?? null;

  const build = () => {
    ridges.forEach(disposeRidge);
    const mine = filterByPlatform(p.videos, platform);
    videos = filterByPeriod(mine, period, today).sort((a, b) => a.age_days - b.age_days);
    // Scaled over every period so switching it only adds or removes ridges, never reshapes the survivors.
    const maxDaily = Math.max(1, ...mine.flatMap((v) => v.daily));
    const drawn: Vector3[] = [];
    ridges = videos.map((v, i) => {
      const typical = p.channel.typical_daily[v.format] ?? p.channel.typical_daily.all;
      const r = buildRidge(v, typical, maxDaily, ridgeZ(i));
      applyLook(r.group, look);
      // Frame the drawn crests and the ground under them, not the full 0..DAYS floor lines.
      for (const pt of r.crest) drawn.push(pt, pt.clone().setY(0));
      stage.scene.add(r.group);
      return r;
    });
    if (drawn.length) stage.frame(drawn);
    lit = videos.map((v) => v.state === "breakout" || v.state === "second_wind");
    noStar = starId() === null;
    why.setStar(starId());
    emphasize(null);
    renderTable(root, videos);
    showEmpty(root, videos.length ? null : "No hay videos en este periodo. Prueba con otro periodo o plataforma.");
  };

  const overview = () => {
    selected = null;
    hovered = null;
    clearFront();
    emphasize(null);
    why.hide();
    void rig.overview();
  };
  const select = (i: number) => {
    selected = i;
    hovered = null; // numbers follow the selection, not a stale hover
    emphasize(i);
    clearFront();
    why.show(videos[i], ridges[i].crest, videos[i].why[0] ?? null);
    void rig.focus(ridges[i].crest);
  };
  const goStar = () => {
    const i = videos.findIndex((v) => v.id === starId());
    if (i < 0) overview();
    else select(i);
  };

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
    if (ready && pick(e) === null) overview();
  });

  addEventListener("keydown", (e) => {
    if (!ready || e.ctrlKey || e.metaKey) return;
    if (e.key === "Alt") {
      e.preventDefault(); // keeps Windows from focusing the browser menu
      altDown = true;
    } else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && videos.length) {
      e.preventDefault();
      select(nextIndex(selected, e.key, videos.length));
    } else if (e.key === "Escape") overview();
    else if (e.key === " " && !(e.target instanceof HTMLButtonElement)) {
      e.preventDefault(); // a focused bar button keeps Space for itself
      goStar();
    }
  });
  addEventListener("keyup", (e) => e.key === "Alt" && (altDown = false));
  addEventListener("blur", () => (altDown = false));

  const tip = new Vector3();
  /** Numbers sit at the top of whichever ridge is under the pointer, else the selected one. */
  const syncNumbers = () => {
    const i = hovered ?? selected;
    if (i === null || !(numbersButton || altDown)) return hideNumbers();
    const top = ridges[i].crest.reduce((a, q) => (q.y > a.y ? q : a));
    tip.copy(top).project(camera);
    showNumbers(videos[i], { x: ((tip.x + 1) / 2) * canvas.clientWidth, y: ((1 - tip.y) / 2) * canvas.clientHeight });
  };

  build();
  let raf = 0;
  let last = performance.now();
  const loop = () => {
    const now = performance.now();
    why.update((now - last) / 1000);
    last = now;
    syncNumbers();
    stage.render();
    raf = requestAnimationFrame(loop);
  };
  loop();
  document.addEventListener("visibilitychange", () => {
    cancelAnimationFrame(raf);
    if (document.hidden) return;
    last = performance.now();
    loop();
  });

  /** Called only once the opening timeline has finished (before the star flight or after it), so the bar never rebuilds ridges that are still animating; a rebuild during the flight cancels it. */
  const start = (star: number | null) => {
    if (ready) return;
    ready = true;
    mountBar(root, p.platforms, {
      onPlatform: (next) => ((platform = next), build(), overview()),
      onPeriod: (days) => ((period = days), build(), overview()),
      onStar: goStar,
      onNumbers: (on) => (numbersButton = on),
    });
    selected = star;
    clearFront();
    if (star === null) return;
    emphasize(star); // the opening's own flight is already under way
    why.show(videos[star], ridges[star].crest, videos[star].why[0] ?? null);
  };
  const starAt = videos.findIndex((v) => v.id === starId());
  const star = starAt < 0 ? null : starAt;
  void playOpening(ridges, rig, star, reducedMotion(), () => start(star)).then(() => start(null));
}

void load();

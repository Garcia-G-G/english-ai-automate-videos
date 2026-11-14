import gsap from "gsap";
import type { Vector3 } from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Stage } from "./scene";

export interface Rig {
  flyTo(target: Vector3, from: Vector3, seconds?: number): Promise<void>;
  overview(seconds?: number): Promise<void>;
  /** Fly to a close-up fitted to one ridge's crest and the ground under it. */
  focus(crest: Vector3[], seconds?: number): Promise<void>;
  cancel(): void;
  /** Count of user presses and wheel turns on the canvas; lets a sequence notice the user took over. */
  readonly inputs: number;
}

const FLIGHT_S = 1.6;
// Fraction of the frustum the selected crest may fill; tighter than the overview's 0.86 so one video reads large.
export const CLOSE_MARGIN = 0.62;

/** System "reduce motion", or `?reduced=1` to force it while testing. */
export const reducedMotion = (): boolean =>
  new URLSearchParams(location.search).get("reduced") === "1" || matchMedia("(prefers-reduced-motion: reduce)").matches;

export function createRig(stage: Stage, dom: HTMLElement): Rig {
  const { camera } = stage;
  let tween: gsap.core.Tween | null = null;
  let settle: (() => void) | null = null;
  const cancel = () => {
    tween?.kill();
    tween = null;
    settle?.(); // a cancelled flight still resolves: the caller only waits for the camera to be free
    settle = null;
  };
  let inputs = 0;
  const takeOver = () => (inputs++, cancel());
  // Registered before OrbitControls so the user's drag or wheel always wins over a flight.
  dom.addEventListener("pointerdown", takeOver);
  dom.addEventListener("wheel", takeOver, { passive: true });
  const controls = new OrbitControls(camera, dom);
  controls.target.copy(stage.home.target);
  controls.update();

  const flyTo = (target: Vector3, from: Vector3, seconds = FLIGHT_S): Promise<void> => {
    cancel();
    const p0 = camera.position.clone();
    const t0 = controls.target.clone();
    const place = (k: number) => {
      camera.position.lerpVectors(p0, from, k);
      controls.target.lerpVectors(t0, target, k);
      controls.update();
    };
    if (reducedMotion() || seconds <= 0) return Promise.resolve(place(1));
    return new Promise((resolve) => {
      const s = { k: 0 };
      settle = resolve;
      tween = gsap.to(s, {
        k: 1,
        duration: seconds,
        ease: "power2.inOut",
        onUpdate: () => place(s.k),
        onComplete: () => ((tween = null), (settle = null), resolve()),
      });
    });
  };

  return {
    flyTo,
    overview: (seconds) => flyTo(stage.home.target, stage.home.position, seconds),
    focus: (crest, seconds) => {
      const v = stage.fit([...crest, ...crest.map((p) => p.clone().setY(0))], CLOSE_MARGIN);
      return flyTo(v.target, v.position, seconds);
    },
    cancel,
    get inputs() {
      return inputs;
    },
  };
}


import gsap from "gsap";
import { Box3, Vector3 } from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Stage } from "./scene";

export interface Rig {
  flyTo(target: Vector3, from: Vector3, seconds?: number): Promise<void>;
  overview(): Promise<void>;
  cancel(): void;
}

const FLIGHT_S = 1.6;

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
  // Registered before OrbitControls so the user's drag or wheel always wins over a flight.
  dom.addEventListener("pointerdown", cancel);
  dom.addEventListener("wheel", cancel, { passive: true });
  const controls = new OrbitControls(camera, dom);
  controls.target.copy(stage.home.target);
  controls.update();
  // stage refits to the overview on resize; keep the orbit centre with it.
  addEventListener("resize", () => {
    cancel();
    controls.target.copy(stage.home.target);
    controls.update();
  });

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
    overview: () => flyTo(stage.home.target, stage.home.position),
    cancel,
  };
}

/**
 * Camera offset from a crest's centre for a close look: the overview's azimuth side (-28 deg) a little higher,
 * far enough that fov 16 holds the whole 0..14 day crest and its peak.
 */
export const CLOSE_OFFSET = new Vector3(-19, 8, 36);

/** Where to look and where to stand to frame one crest. */
export function framing(crest: Vector3[]): { target: Vector3; from: Vector3 } {
  const target = new Box3().setFromPoints(crest).getCenter(new Vector3());
  return { target, from: target.clone().add(CLOSE_OFFSET) };
}

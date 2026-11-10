import gsap from "gsap";
import type { Material } from "three";
import type { Rig } from "./camera";
import type { RidgeObject } from "./ridges";

const GROUND_S = 0.6;
const GROW_S = 0.8; // one ridge rising
const STAGGER_S = 1.6; // spread from the oldest ridge's start to the newest's; total ~3 s

const materials = (r: RidgeObject, floor: boolean): Material[] => {
  const out: Material[] = [];
  r.group.traverse((o) => {
    const m = (o as { material?: Material }).material;
    if (m && (m.userData.role === "floor") === floor) out.push(m);
  });
  return out;
};

/**
 * Ground fades in, ridges rise oldest to newest (invisible until their turn, fading in as they grow),
 * then the camera flies to the star unless the user grabbed the camera meanwhile. Reduced motion: final state at once.
 * onFly runs just before the flight to the star, so the caller can select it as the camera leaves.
 */
export async function playOpening(ridges: RidgeObject[], rig: Rig, star: number | null, reduced: boolean, onFly?: () => void): Promise<void> {
  const starCrest = star === null ? undefined : ridges[star]?.crest;
  const fly = (seconds?: number) => {
    if (!starCrest) return;
    onFly?.();
    return rig.focus(starCrest, seconds);
  };
  if (reduced) return fly(0);

  const inputs = rig.inputs;
  const tl = gsap.timeline();
  // Debug knob: `?slow=3` plays the opening three times slower so it can be recorded.
  const slow = Number(new URLSearchParams(location.search).get("slow"));
  if (slow > 0) tl.timeScale(1 / slow);
  tl.from(ridges.flatMap((r) => materials(r, true)), { opacity: 0, duration: GROUND_S, ease: "none" });
  // ridges[0] is the newest (front), so the oldest goes first.
  const each = ridges.length > 1 ? STAGGER_S / (ridges.length - 1) : 0;
  [...ridges].reverse().forEach((r, k) => {
    const at = GROUND_S + k * each;
    // from() tweens render their start values at once, so a ridge stays hidden until `at`.
    tl.from(materials(r, false), { opacity: 0, duration: GROW_S * 0.6, ease: "none" }, at);
    tl.fromTo(r.group.scale, { y: 0.001 }, { y: 1, duration: GROW_S, ease: "power2.out" }, at);
  });
  await tl.then();
  if (rig.inputs === inputs) await fly();
}

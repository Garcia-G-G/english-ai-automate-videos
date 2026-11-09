import gsap from "gsap";
import type { Material } from "three";
import { framing, type Rig } from "./camera";
import type { RidgeObject } from "./ridges";

const GROUND_S = 0.6;
const GROW_S = 0.8; // one ridge rising
const STAGGER_S = 1.6; // spread from the oldest ridge's start to the newest's; total ~3 s

/** Ground fades in, ridges rise oldest to newest, then the camera flies to the star. Reduced motion: final state at once. */
export async function playOpening(ridges: RidgeObject[], rig: Rig, star: number | null, reduced: boolean): Promise<void> {
  const fly = () => {
    if (star === null || !ridges[star]) return Promise.resolve();
    const { target, from } = framing(ridges[star].crest);
    return rig.flyTo(target, from, reduced ? 0 : undefined);
  };
  if (reduced) return fly();

  const floors: Material[] = [];
  for (const r of ridges)
    r.group.traverse((o) => {
      const m = (o as { material?: Material }).material;
      if (m?.userData.role === "floor") floors.push(m);
    });
  const tl = gsap.timeline();
  tl.from(floors, { opacity: 0, duration: GROUND_S, ease: "none" });
  // ridges[0] is the newest (front), so the oldest goes first.
  const each = ridges.length > 1 ? STAGGER_S / (ridges.length - 1) : 0;
  [...ridges].reverse().forEach((r, k) => {
    r.group.scale.y = 0.001;
    tl.to(r.group.scale, { y: 1, duration: GROW_S, ease: "power2.out" }, GROUND_S + k * each);
  });
  await tl.then();
  await fly();
}

type P = { x: number; y: number };

/** Distance from p to the segment ab. */
function segDist(p: P, a: P, b: P): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.min(1, Math.max(0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2)) : 0;
  return Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy);
}

/**
 * Index of the ridge whose on-screen crest polyline is nearest the pointer, or null beyond maxPx.
 * Ties go to the lower index (the front ridge). Hover and click both select through this.
 */
export function pickRidge(pointer: P, crestsOnScreen: P[][], maxPx = 18): number | null {
  let best: number | null = null;
  let bestD = maxPx;
  crestsOnScreen.forEach((pts, i) => {
    for (let k = 0; k < pts.length; k++) {
      const d = segDist(pointer, pts[k], pts[k + 1] ?? pts[k]);
      if (d < bestD || (d === bestD && best === null)) [best, bestD] = [i, d];
    }
  });
  return best;
}

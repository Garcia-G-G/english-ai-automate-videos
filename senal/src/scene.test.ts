import { PerspectiveCamera, Vector3 } from "three";
import { expect, test } from "vitest";
import { fitCamera } from "./scene";

test.each([
  [{ elevation: 38, azimuth: -18, fov: 30 }, 16 / 9],
  [{ elevation: 13, azimuth: -34, fov: 36 }, 4 / 3],
  [{ elevation: 22, azimuth: 0, fov: 18 }, 16 / 9],
])("the fitted camera keeps every drawn point in frame and fills it (%o)", (view, aspect) => {
  const corners = [0, 1, 2, 3, 4, 5, 6, 7].map((i) => new Vector3(i & 1 ? 7 : -10, i & 2 ? 7 : 0, i & 4 ? 0 : -35));
  const cam = new PerspectiveCamera(30, aspect);
  fitCamera(cam, corners, view);
  cam.updateMatrixWorld();
  const ndc = corners.map((c) => c.clone().project(cam));
  for (const p of ndc) {
    expect(Math.abs(p.x)).toBeLessThanOrEqual(0.9);
    expect(Math.abs(p.y)).toBeLessThanOrEqual(0.9);
  }
  const spanX = Math.max(...ndc.map((p) => p.x)) - Math.min(...ndc.map((p) => p.x));
  const spanY = Math.max(...ndc.map((p) => p.y)) - Math.min(...ndc.map((p) => p.y));
  expect(Math.max(spanX, spanY)).toBeGreaterThan(1.6); // fills one axis to ~the margin
  expect(Math.abs(Math.max(...ndc.map((p) => p.x)) + Math.min(...ndc.map((p) => p.x)))).toBeLessThan(0.1); // centred
});

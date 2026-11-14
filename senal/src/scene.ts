import { BloomEffect, BlendFunction, EffectComposer, EffectPass, NoiseEffect, RenderPass, VignetteEffect } from "postprocessing";
import { Box3, CanvasTexture, Color, Fog, HalfFloatType, MathUtils, PerspectiveCamera, Scene, Sphere, SRGBColorSpace, Vector3, WebGLRenderer } from "three";
import type { Look } from "./looks";

export interface View {
  position: Vector3;
  target: Vector3;
}

export interface Stage {
  renderer: WebGLRenderer;
  scene: Scene;
  camera: PerspectiveCamera;
  composer: EffectComposer;
  /** The fitted overview: where the camera sits and what it looks at. Updated on every resize; the camera is not moved. */
  home: View;
  /** Where the camera would sit to fit these points, from the look's azimuth and elevation. Does not move the camera. */
  fit(points: Vector3[], margin?: number): View;
  frame(points: Vector3[]): void;
  render(): void;
  dispose(): void;
}

const MARGIN = 0.86; // fraction of the frustum the drawn box may fill

/**
 * Places the camera on the look's elevation/azimuth so the drawn points fill the frame with a margin.
 * Returns the camera-to-target distance. Two passes re-centre the perspective-skewed projection.
 */
export function fitCamera(camera: PerspectiveCamera, points: Vector3[], view: Look["view"], margin = MARGIN): number {
  const el = MathUtils.degToRad(view.elevation);
  const az = MathUtils.degToRad(view.azimuth);
  const dir = new Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el));
  const r = new Vector3().crossVectors(new Vector3(0, 1, 0), dir).normalize();
  const u = new Vector3().crossVectors(dir, r);
  camera.fov = view.fov;
  camera.updateProjectionMatrix();
  const tanV = Math.tan(MathUtils.degToRad(camera.fov / 2)) * margin;
  const tanH = tanV * camera.aspect;
  const target = new Box3().setFromPoints(points).getCenter(new Vector3());
  let d = 0;
  for (let pass = 0; pass < 3; pass++) {
    const rel = points.map((c) => c.clone().sub(target));
    d = Math.max(...rel.map((p) => p.dot(dir) + Math.max(Math.abs(p.dot(r)) / tanH, Math.abs(p.dot(u)) / tanV)));
    // Shift the target by the midpoint of the projected extents so margins come out even.
    const sx = rel.map((p) => p.dot(r) / (d - p.dot(dir)));
    const sy = rel.map((p) => p.dot(u) / (d - p.dot(dir)));
    const mx = (Math.max(...sx) + Math.min(...sx)) / 2;
    const my = (Math.max(...sy) + Math.min(...sy)) / 2;
    target.addScaledVector(r, mx * d).addScaledVector(u, my * d);
  }
  camera.position.copy(target).addScaledVector(dir, d);
  camera.near = Math.max(0.1, d / 50);
  camera.far = d * 4;
  camera.lookAt(target);
  camera.updateProjectionMatrix();
  return d;
}

/** Vertical gradient: dark sky, a soft horizon band where the fog lives, dark floor. */
function gradient({ top, horizon, bottom, at }: Look["background"]): CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 2;
  c.height = 512;
  const g = c.getContext("2d")!;
  const fill = g.createLinearGradient(0, 0, 0, c.height);
  fill.addColorStop(0, top);
  fill.addColorStop(at, horizon);
  fill.addColorStop(1, bottom);
  g.fillStyle = fill;
  g.fillRect(0, 0, c.width, c.height);
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace;
  return t;
}

export function createStage(canvas: HTMLCanvasElement, look: Look): Stage {
  const renderer = new WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  const scene = new Scene();
  const bg = gradient(look.background);
  scene.background = bg;
  const fog = new Fog(new Color(look.fogColor), 1, 100);
  scene.fog = fog;

  const camera = new PerspectiveCamera(look.view.fov, 1, 0.1, 200);
  camera.position.set(-2, 16, 26);
  camera.lookAt(0, 1, -10);
  let framed: Vector3[] | null = null;
  const home: View = { position: camera.position.clone(), target: new Vector3(0, 1, -10) };
  const scratch = camera.clone();
  const fitView = (points: Vector3[], margin?: number): View & { d: number } => {
    scratch.aspect = camera.aspect;
    const d = fitCamera(scratch, points, look.view, margin);
    const target = scratch.getWorldDirection(new Vector3()).multiplyScalar(d).add(scratch.position);
    return { position: scratch.position.clone(), target, d };
  };
  const refit = () => {
    if (!framed) return;
    const { position, target, d } = fitView(framed);
    home.position.copy(position);
    home.target.copy(target);
    // Clip planes and fog follow the overview so a close-up sees the same landscape.
    camera.fov = scratch.fov;
    camera.near = scratch.near;
    camera.far = scratch.far;
    camera.updateProjectionMatrix();
    const radius = new Box3().setFromPoints(framed).getBoundingSphere(new Sphere()).radius;
    fog.near = d - radius * 0.4; // the front ridge stays clear
    fog.far = d + radius * look.fogDepth;
  };

  const composer = new EffectComposer(renderer, { frameBufferType: HalfFloatType, multisampling: 4 });
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new BloomEffect({
    mipmapBlur: true,
    intensity: look.bloomIntensity,
    luminanceThreshold: look.bloomThreshold,
    luminanceSmoothing: 0.2,
    radius: look.bloomRadius,
  });
  const noise = new NoiseEffect({ blendFunction: BlendFunction.OVERLAY, premultiply: false });
  noise.blendMode.opacity.value = look.grain;
  const vignette = new VignetteEffect({ offset: 0.3, darkness: look.vignette });
  composer.addPass(new EffectPass(camera, bloom, vignette, noise));

  const resize = () => {
    const w = canvas.clientWidth || innerWidth;
    const h = canvas.clientHeight || innerHeight;
    renderer.setSize(w, h, false);
    composer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    refit();
  };
  resize();

  const render = () => composer.render();
  const onResize = () => (resize(), render());
  addEventListener("resize", onResize);

  return {
    renderer,
    scene,
    camera,
    composer,
    home,
    fit: (points, margin) => {
      const { position, target } = fitView(points, margin);
      return { position, target };
    },
    frame(points) {
      framed = points;
      refit();
      camera.position.copy(home.position);
      camera.lookAt(home.target);
    },
    render,
    dispose() {
      removeEventListener("resize", onResize);
      composer.dispose();
      bg.dispose();
      renderer.dispose();
    },
  };
}

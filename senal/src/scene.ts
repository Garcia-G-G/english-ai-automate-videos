import { BloomEffect, BlendFunction, EffectComposer, EffectPass, NoiseEffect, RenderPass, VignetteEffect } from "postprocessing";
import { CanvasTexture, Color, FogExp2, HalfFloatType, PerspectiveCamera, Scene, SRGBColorSpace, WebGLRenderer } from "three";
import type { Look } from "./looks";

export interface Stage {
  renderer: WebGLRenderer;
  scene: Scene;
  camera: PerspectiveCamera;
  composer: EffectComposer;
  render(): void;
  dispose(): void;
}

/** Vertical gradient: dark sky, a soft horizon band where the fog lives, dark floor. */
function gradient([top, horizon, bottom]: Look["background"]): CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 2;
  c.height = 512;
  const g = c.getContext("2d")!;
  const fill = g.createLinearGradient(0, 0, 0, c.height);
  fill.addColorStop(0, top);
  fill.addColorStop(0.42, horizon);
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
  scene.fog = new FogExp2(new Color(look.background[1]), look.fogDensity);

  const camera = new PerspectiveCamera(30, 1, 0.1, 200);
  camera.position.set(-2, 16, 26);
  camera.lookAt(0, 1, -10);

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
    render,
    dispose() {
      removeEventListener("resize", onResize);
      composer.dispose();
      bg.dispose();
      renderer.dispose();
    },
  };
}

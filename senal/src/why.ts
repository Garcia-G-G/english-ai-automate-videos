import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  CatmullRomCurve3,
  Color,
  DoubleSide,
  LineBasicMaterial,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  Points,
  RingGeometry,
  ShaderMaterial,
  Vector2,
  Vector3,
} from "three";
import { reducedMotion } from "./camera";
import type { Video } from "./data";
import { DEFAULT_LOOK } from "./looks";
import { curtainOpacity, softDot } from "./ridges";
import type { Stage } from "./scene";

export type Source = "SHORTS" | "YT_SEARCH" | "EXT";
const SOURCES: Source[] = ["SHORTS", "YT_SEARCH", "EXT"];
const HUE: Record<Source, Color> = { SHORTS: new Color("#3987e5"), YT_SEARCH: new Color("#199e70"), EXT: new Color("#d95926") };
const GOLD = new Color("#ffc45e");
const WHITE = new Color("#f4f6ff");
const RING = new Color("#dfe6ff");
const EMPHASIS_SOURCE: Record<string, Source> = { search: "YT_SEARCH", external: "EXT" };

// Streams: base -> peak along the crest. Lanes sit side by side (z across the ridge, y above the crest) so each colour reads alone.
const STREAM_TOTAL = 380;
const STREAM_TRAIL = 6; // points per particle: the head plus a fading tail
const LANE: Record<Source, { z: number; y: number }> = { SHORTS: { z: 0, y: 0.04 }, YT_SEARCH: { z: 0.42, y: 0.16 }, EXT: { z: -0.42, y: 0.28 } };
const LANE_WIDTH = 0.11; // half-spread of a lane, world units
const STREAM_SPEED = 0.2; // fraction of the path per second: a particle climbs in ~5 s
const STREAM_SIZE = 0.13;
const HEAD_GAIN = 1.15; // above 1 the heads cross the bloom threshold

// Shares: one burst of sparks per share from the peak, capped.
const SPARKS_PER_SHARE = 45;
const SPARKS_MAX = 200;
const SPARK_TRAIL = 3;
const SPARK_CYCLE = 2.6; // seconds between a burst and its repeat
const SPARK_SIZE = 0.15;

// Subscribers: white points that rise from the peak and stay hovering above it.
const SUBS_PER_SUB = 14;
const SUBS_MAX = 120;
const SUB_RISE = 2.4; // seconds
const SUB_SPREAD = 1.4; // seconds over which the points leave the peak
const SUB_SIZE = 0.1;

const RING_PERIOD = 2.2;
const FADE_RATE = 5; // per second, the whole explanation fading in and out
const STILL_T = 4; // reduced motion: everything is frozen at this moment, sparks mid-flight and subscribers hovering
const PATH_SAMPLES = 256;

export interface Why {
  show(v: Video, crest: Vector3[], emphasis: string | null): void;
  hide(): void;
  update(dt: number): void;
}

/** Splits `total` across the three drawn sources in their real proportions; largest remainder keeps the sum exact. */
export function allocateParticles(sources: Record<string, number>, total: number): Record<Source, number> {
  const w = SOURCES.map((k) => Math.max(0, sources[k] ?? 0));
  const sum = w.reduce((a, b) => a + b, 0);
  const out = { SHORTS: 0, YT_SEARCH: 0, EXT: 0 };
  if (sum <= 0) return out;
  const exact = w.map((x) => (x / sum) * total);
  const n = exact.map(Math.floor);
  let left = total - n.reduce((a, b) => a + b, 0);
  for (const i of SOURCES.map((_, i) => i).sort((a, b) => exact[b] - n[b] - (exact[a] - n[a]))) if (left-- > 0) n[i]++;
  SOURCES.forEach((k, i) => (out[k] = n[i]));
  return out;
}

const VERT = /* glsl */ `
attribute vec3 tint;
attribute float psize;
uniform float uScale;
varying vec3 vTint;
void main() {
  vTint = tint;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = max(1.0, psize * uScale / -mv.z);
  gl_Position = projectionMatrix * mv;
}`;
const FRAG = /* glsl */ `
uniform sampler2D uMap;
uniform float uOpacity;
varying vec3 vTint;
void main() {
  gl_FragColor = vec4(vTint * texture2D(uMap, gl_PointCoord).a * uOpacity, 1.0);
}`;

/** Soft round additive sprites; tint carries both colour and brightness so black means invisible. */
function layer(name: string, capacity: number, material: ShaderMaterial): { points: Points; pos: Float32Array; tint: Float32Array; size: Float32Array } {
  const g = new BufferGeometry();
  const pos = new Float32Array(capacity * 3);
  const tint = new Float32Array(capacity * 3);
  const size = new Float32Array(capacity);
  g.setAttribute("position", new BufferAttribute(pos, 3));
  g.setAttribute("tint", new BufferAttribute(tint, 3));
  g.setAttribute("psize", new BufferAttribute(size, 1));
  g.setDrawRange(0, 0);
  const points = new Points(g, material);
  points.name = name;
  points.frustumCulled = false; // positions change every frame; the bounding sphere is never recomputed
  points.visible = false;
  return { points, pos, tint, size };
}

const smooth = (a: number, b: number, x: number): number => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};
const rand = (i: number, salt: number): number => {
  const s = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453;
  return s - Math.floor(s);
};

export function createWhy(stage: Stage, starId: string | null = null): Why {
  const material = new ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    uniforms: { uMap: { value: softDot() }, uOpacity: { value: 0 }, uScale: { value: 300 } },
    transparent: true,
    depthWrite: false,
    blending: AdditiveBlending,
  });
  const stream = layer("stream", STREAM_TOTAL * STREAM_TRAIL, material);
  const sparks = layer("sparks", SPARKS_MAX * 2 * SPARK_TRAIL, material);
  const subs = layer("subs", SUBS_MAX * 2, material);
  const ringMats = [0, 1].map(() => new MeshBasicMaterial({ color: RING, transparent: true, opacity: 0, depthWrite: false, blending: AdditiveBlending, side: DoubleSide }));
  const ringGeo = new RingGeometry(0.94, 1, 96).rotateX(-Math.PI / 2);
  const rings = ringMats.map((m) => Object.assign(new Mesh(ringGeo, m), { visible: false }));
  const curtainMat = new LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0, depthWrite: false, blending: AdditiveBlending });
  const glow = new LineSegments(new BufferGeometry(), curtainMat);
  glow.visible = false;
  for (const o of [stream.points, sparks.points, subs.points, glow, ...rings]) stage.scene.add(o);

  // Per-show state.
  let path: Vector3[] = [];
  let peak = new Vector3();
  let src: Source[] = [];
  let phase = new Float32Array(0);
  let width: Record<Source, number> = { SHORTS: LANE_WIDTH, YT_SEARCH: LANE_WIDTH, EXT: LANE_WIDTH };
  let speed: Record<Source, number> = { SHORTS: STREAM_SPEED, YT_SEARCH: STREAM_SPEED, EXT: STREAM_SPEED };
  let nSparks = 0;
  let nSubs = 0;
  let isStar = false;
  let glowOpacity = 0;
  let alpha = 0;
  let target = 0;
  let t = 0; // seconds since show
  let still = false;

  const at = (u: number, out: Vector3): Vector3 => {
    const f = Math.min(Math.max(u, 0), 1) * (path.length - 1);
    const i = Math.min(Math.floor(f), path.length - 2);
    return out.lerpVectors(path[i], path[i + 1], f - i);
  };

  const p = new Vector3();
  const writeStream = (dt: number) => {
    let w = 0;
    for (let h = 0; h < src.length; h++) {
      const s = src[h];
      const v = speed[s] * (0.8 + 0.45 * rand(h, 1));
      phase[h] = (phase[h] + v * dt) % 1;
      const s1 = rand(h, 2) - 0.5;
      const s2 = rand(h, 3) - 0.5;
      for (let k = 0; k < STREAM_TRAIL; k++, w++) {
        const u = phase[h] - k * v * 0.045; // a faster particle draws a longer tail
        at(u, p);
        const turb = rand(h, 4) * 6.283;
        stream.pos[w * 3] = p.x;
        stream.pos[w * 3 + 1] = p.y + LANE[s].y + s2 * 1.2 * width[s] + 0.03 * Math.sin(t * 1.6 + turb + u * 8);
        stream.pos[w * 3 + 2] = p.z + LANE[s].z + s1 * 2 * width[s] + 0.035 * Math.sin(t * 2.1 + turb + u * 11);
        const env = u < 0 ? 0 : smooth(0, 0.06, u) * (1 - smooth(0.86, 1, u));
        const b = env * (k === 0 ? HEAD_GAIN : 0.45 * (1 - k / STREAM_TRAIL) ** 1.6);
        stream.tint[w * 3] = HUE[s].r * b;
        stream.tint[w * 3 + 1] = HUE[s].g * b;
        stream.tint[w * 3 + 2] = HUE[s].b * b;
        stream.size[w] = STREAM_SIZE * (1 - 0.11 * k);
      }
    }
  };

  const writeSparks = () => {
    const bursts = Math.ceil(nSparks / SPARKS_PER_SHARE);
    let w = 0;
    for (let i = 0; i < nSparks; i++) {
      const offset = (Math.floor(i / SPARKS_PER_SHARE) * SPARK_CYCLE) / Math.max(bursts, 1);
      const life = 1.1 + 0.7 * rand(i, 5);
      const theta = rand(i, 6) * 6.283;
      const tilt = 0.3 + rand(i, 7) * 1.0; // 17 to 75 degrees off vertical: a fountain, not a column
      const sp = 1.8 + 1.8 * rand(i, 8);
      const vx = Math.sin(tilt) * Math.cos(theta) * sp;
      const vy = Math.cos(tilt) * sp;
      const vz = Math.sin(tilt) * Math.sin(theta) * sp;
      for (let k = 0; k < SPARK_TRAIL; k++, w++) {
        const a = (((t - offset) % SPARK_CYCLE) + SPARK_CYCLE) % SPARK_CYCLE - k * 0.035;
        const alive = t >= offset && a >= 0 && a < life;
        const drag = (1 - Math.exp(-2.2 * a)) / 2.2; // fast out of the peak, slowing like an ember
        sparks.pos[w * 3] = peak.x + vx * drag;
        sparks.pos[w * 3 + 1] = peak.y + 0.05 + vy * drag - 0.9 * a * a; // gravity: embers arc and fall back along the slopes
        sparks.pos[w * 3 + 2] = peak.z + vz * drag;
        const b = alive ? 2.2 * (1 - a / life) ** 2 * (k === 0 ? 1 : 0.5 / k) : 0;
        sparks.tint[w * 3] = GOLD.r * b;
        sparks.tint[w * 3 + 1] = GOLD.g * b;
        sparks.tint[w * 3 + 2] = GOLD.b * b;
        sparks.size[w] = SPARK_SIZE * (1 - 0.2 * k);
      }
    }
  };

  const writeSubs = () => {
    for (let i = 0; i < nSubs; i++) {
      const k = Math.min(1, Math.max(0, (t - (i / nSubs) * SUB_SPREAD) / SUB_RISE));
      const e = 1 - (1 - k) ** 3; // ease out: leaves quickly, settles softly
      const bob = rand(i, 9) * 6.283;
      subs.pos[i * 3] = peak.x + e * (rand(i, 10) - 0.5) * 4 + 0.05 * Math.sin(t * 0.5 + bob);
      // The close-up leaves about 2 units above the peak; the points hover inside it.
      subs.pos[i * 3 + 1] = peak.y + 0.15 + e * (0.3 + 1.0 * rand(i, 11)) + 0.07 * Math.sin(t * 0.9 + bob);
      subs.pos[i * 3 + 2] = peak.z + e * (rand(i, 12) - 0.5) * 1.0;
      const b = (k > 0 ? smooth(0, 0.15, k) : 0) * (0.8 + 0.25 * Math.sin(t * 1.3 + bob * 2));
      subs.tint[i * 3] = WHITE.r * b;
      subs.tint[i * 3 + 1] = WHITE.g * b;
      subs.tint[i * 3 + 2] = WHITE.b * b;
      subs.size[i] = SUB_SIZE * (0.8 + 0.4 * rand(i, 13));
    }
  };

  const writeRings = () =>
    rings.forEach((r, j) => {
      const k = still ? 0.45 : ((t / RING_PERIOD + j / 2) % 1);
      r.scale.setScalar(0.4 + 2 * k);
      (r.material as MeshBasicMaterial).opacity = alpha * (still ? 0.5 * (j === 0 ? 1 : 0) : 0.8 * (1 - k) ** 1.5);
    });

  const dirty = () => {
    for (const l of [stream, sparks, subs]) {
      const g = l.points.geometry;
      for (const a of ["position", "tint", "psize"]) g.getAttribute(a).needsUpdate = true;
    }
  };

  const setVisible = (on: boolean) => {
    stream.points.visible = sparks.points.visible = subs.points.visible = on;
    glow.visible = on && glowOpacity > 0;
    rings.forEach((r) => (r.visible = on && isStar));
  };

  return {
    show(v, crest, emphasis) {
      still = reducedMotion();
      t = still ? STILL_T : 0;
      const top = crest.reduce((best, q, i) => (q.y > crest[best].y ? i : best), 0);
      peak = crest[top]?.clone() ?? new Vector3();
      path = crest.length >= 2 ? new CatmullRomCurve3(crest.slice(0, Math.max(top, 1) + 1)).getSpacedPoints(PATH_SAMPLES - 1) : [];

      const loud = emphasis ? EMPHASIS_SOURCE[emphasis] : undefined;
      width = { SHORTS: LANE_WIDTH, YT_SEARCH: LANE_WIDTH, EXT: LANE_WIDTH };
      speed = { SHORTS: STREAM_SPEED, YT_SEARCH: STREAM_SPEED, EXT: STREAM_SPEED };
      if (loud) (width[loud] *= 2), (speed[loud] *= 2);
      const counts = path.length ? allocateParticles(v.sources, STREAM_TOTAL) : allocateParticles({}, 0);
      src = SOURCES.flatMap((s) => Array<Source>(counts[s]).fill(s));
      phase = Float32Array.from(src, (_, h) => rand(h, 0)); // spread along the path from the first frame

      nSparks = Math.min(SPARKS_MAX, v.shares * SPARKS_PER_SHARE) * (emphasis === "shares" ? 2 : 1);
      nSubs = Math.min(SUBS_MAX, v.subs * SUBS_PER_SUB) * (emphasis === "subs" ? 2 : 1);
      stream.points.geometry.setDrawRange(0, src.length * STREAM_TRAIL);
      sparks.points.geometry.setDrawRange(0, nSparks * SPARK_TRAIL);
      subs.points.geometry.setDrawRange(0, nSubs);
      stream.points.userData = { heads: src.length, width: { ...width }, speed: { ...speed } };
      sparks.points.userData = { heads: nSparks };
      subs.points.userData = { heads: nSubs };

      isStar = v.id === starId;
      rings.forEach((r) => r.position.set(peak.x, 0.01, peak.z));

      // Retention as the reason: an additive copy of the curtain brings it to 1.8x its own brightness.
      glowOpacity = emphasis === "retention" ? 0.8 * curtainOpacity(v) * DEFAULT_LOOK.curtain : 0;
      glow.geometry.dispose();
      glow.geometry = new BufferGeometry()
        .setAttribute("position", new BufferAttribute(Float32Array.from(crest.flatMap((q) => [q.x, q.y, q.z, q.x, 0, q.z])), 3))
        .setAttribute("color", new BufferAttribute(Float32Array.from(crest.flatMap(() => [RING.r, RING.g, RING.b, 0, 0, 0])), 3));

      alpha = still ? 1 : 0;
      target = 1;
      setVisible(true);
      this.update(0);
    },
    hide() {
      target = 0;
      if (still) alpha = 0;
    },
    update(dt) {
      if (!stream.points.visible) return;
      const step = still ? 0 : Math.min(dt, 0.1); // a long pause (hidden tab) never jumps the particles
      t += step;
      alpha += (target - alpha) * Math.min(1, step * FADE_RATE);
      if (target === 0 && alpha < 0.01) return setVisible(false);
      material.uniforms.uOpacity.value = alpha;
      // World size to pixels: half the buffer height times the projection focal term (fov 16 is narrow, so this matters).
      material.uniforms.uScale.value = stage.renderer.getDrawingBufferSize(new Vector2()).y * 0.5 * stage.camera.projectionMatrix.elements[5];
      curtainMat.opacity = glowOpacity * alpha;
      if (path.length) writeStream(step);
      writeSparks();
      writeSubs();
      writeRings();
      dirty();
    },
  };
}

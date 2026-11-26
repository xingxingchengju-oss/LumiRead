import {
  Box3,
  CanvasTexture,
  Color,
  DoubleSide,
  Material,
  Mesh,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  Object3D,
  PlaneGeometry,
  PMREMGenerator,
  Scene,
  Vector3,
  type WebGLRenderer,
} from "three";
import { type Chapter, type Part, type Wear } from "./product";

export function studioEnvironment(gl: WebGLRenderer) {
  const room = new Scene();
  room.background = new Color(0x111219);
  const panel = new PlaneGeometry();
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext("2d")!;
  ctx.translate(64, 64);
  const glow = ctx.createRadialGradient(0, 0, 4, 0, 0, 65);
  glow.addColorStop(0, "#fff");
  glow.addColorStop(0.72, "#f1f1f1");
  glow.addColorStop(1, "#000");
  ctx.fillStyle = glow;
  ctx.fillRect(-64, -64, 128, 128);
  const diffusion = new CanvasTexture(canvas);
  const lamps: MeshBasicMaterial[] = [];
  function softbox(
    x: number,
    y: number,
    z: number,
    width: number,
    height: number,
    rgb: [number, number, number],
  ) {
    const lamp = new MeshBasicMaterial({
      color: new Color(...rgb),
      map: diffusion,
      side: DoubleSide,
      toneMapped: false,
    });
    lamps.push(lamp);
    const card = new Mesh(panel, lamp);
    card.position.set(x, y, z);
    card.scale.set(width, height, 1);
    card.lookAt(0, 0, 0);
    room.add(card);
  }
  softbox(-2.0, 3.2, 1.7, 6.2, 1.25, [13, 14, 16]);
  softbox(2.9, 1.2, 1.8, 1.65, 3.9, [7.4, 6.7, 5.8]);
  softbox(-1, 1.6, -3.1, 6.0, 1.05, [11, 12, 15]);
  softbox(-0.4, 0.1, 3.9, 3.6, 0.34, [5.1, 5.4, 5.7]);
  softbox(-2.4, -1.2, -1.0, 2.7, 0.8, [1.25, 1.1, 1.0]);
  const pmrem = new PMREMGenerator(gl);
  const light = pmrem.fromScene(room, 0);
  panel.dispose();
  diffusion.dispose();
  lamps.forEach((m) => m.dispose());
  pmrem.dispose();
  return light;
}

export type Shell = "temple-left" | "temple-right" | "shell";
export function prepareModel(asset: Object3D, clip: boolean) {
  const root = asset.clone(true);
  const hits: Mesh[] = [];
  const tags = new Map<Object3D, string>(),
    anchors = new Map<string, Object3D>(),
    roles = new Map<string, Object3D>();
  const copies = new Map<string, Material>(),
    lenses = new Set<Material>(),
    lamps = new Set<MeshStandardMaterial>();
  const shells: {
    mat: Material;
    side: Shell;
    opacity: number;
    depthWrite: boolean;
  }[] = [];
  const inside: { mesh: Mesh; side: Shell }[] = [];
  root.traverse((node) => {
    if (node.userData.anchor) anchors.set(node.userData.anchor, node);
    if (node.userData.role) roles.set(node.userData.role, node);
    if (!(node instanceof Mesh)) return;
    let raw: string | undefined;
    for (
      let parent: Object3D | null = node;
      parent && !raw;
      parent = parent.parent
    )
      raw = parent.userData.part;
    if (!raw) return;
    hits.push(node);
    tags.set(node, raw);
    const side = clip
      ? raw === "clip-core"
        ? "shell"
        : null
      : raw === "battery"
        ? "temple-left"
        : ["board", "imu", "radio"].includes(raw)
          ? "temple-right"
          : null;
    if (side) {
      inside.push({ mesh: node, side });
      node.visible = false;
    }
    const shell = clip
      ? raw === "shell"
      : raw === "temple-left" || raw === "temple-right";
    if (!shell && raw !== "lens" && raw !== "led") return;
    function clone(original: Material) {
      const key = raw + original.uuid;
      const known = copies.get(key);
      if (known) return known;
      const mat = original.clone();
      copies.set(key, mat);
      if (shell) {
        shells.push({
          mat,
          side: raw as Shell,
          opacity: mat.opacity,
          depthWrite: mat.depthWrite,
        });
        // Keep one shader variant through the entire cutaway.
        mat.transparent = true;
        mat.forceSinglePass = true;
      }
      if (raw === "lens") {
        lenses.add(mat);
        mat.depthWrite = false;
        if (mat instanceof MeshPhysicalMaterial) {
          mat.ior = 1.54;
          mat.metalness = 0;
          mat.roughness = 0.038;
          mat.iridescence = clip ? 0 : 0.38;
          mat.iridescenceIOR = 1.34;
          mat.iridescenceThicknessRange = [220, 360];
        }
      }
      if (
        raw === "led" &&
        mat instanceof MeshStandardMaterial &&
        mat.name.includes("Sea-glass")
      ) {
        mat.emissive.set(0x74ffd6);
        mat.emissiveIntensity = 0;
        lamps.add(mat);
      }
      return mat;
    }
    node.material = Array.isArray(node.material)
      ? node.material.map(clone)
      : clone(node.material);
  });
  root.updateMatrixWorld(true);
  const bounds = new Box3().setFromObject(root).expandByScalar(0.08);
  if (clip) {
    // Include the module's raised position during installation.
    bounds.max.y += 0.23;
    bounds.max.z += 0.1;
  }
  const atRest = new Map(
    [...anchors].map(([id, node]) => [
      id,
      node.getWorldPosition(new Vector3()),
    ]),
  );
  let currentShell: Shell | null = null,
    currentWeight = -1;
  function section(shell: Shell | null, weight: number) {
    if (shell === currentShell && weight === currentWeight) return;
    currentShell = shell;
    currentWeight = weight;
    for (const item of inside)
      item.mesh.visible = item.side === shell && weight > 0.01;
    for (const s of shells) {
      const t = s.side === shell ? weight : 0;
      s.mat.depthWrite = t > 0.001 ? false : s.depthWrite;
      s.mat.opacity = s.opacity * (1 - t) + 0.055 * t;
    }
  }
  return {
    root,
    bounds,
    hits,
    tags,
    anchors,
    roles,
    atRest,
    lenses,
    lamps,
    copies,
    section,
  };
}
export type Model = ReturnType<typeof prepareModel>;
export type Pose = {
  target: Vector3;
  yaw: number;
  pitch: number;
  roll: number;
  distance: number;
  x: number;
  y: number;
};
export function cameraPose(
  model: Model,
  chapter: Chapter,
  wear: Wear,
  part: Part | undefined,
  width: number,
  height: number,
): Pose {
  const mobile = width <= 700,
    clip = wear === "clip",
    hero = chapter === "top" && !part;
  const anchor = (id: string) =>
    model.atRest.get(id)?.clone() ?? new Vector3(0, 0, -0.38);
  const center = (x = 0, y = 0, z = -0.45) => new Vector3(x, y, z);
  const frame = (
    target: Vector3,
    yaw: number,
    pitch: number,
    span: number,
    tall: number,
    roll = 0,
  ): Pose => {
    const boardCenter =
      !mobile && (part === "temple-right" || part === "temple-left");
    const fx = hero ? (mobile ? 0.96 : 0.85) : mobile ? 0.92 : 0.54;
    const fy = hero ? 0.53 : mobile ? 0.35 : 0.72;
    const distance =
      Math.max(span / ((fx * width) / height), tall / fy) /
      (2 * Math.tan(Math.PI / 15)); // Half the 24° vertical field of view.
    return {
      target,
      yaw,
      pitch,
      roll,
      distance,
      x: mobile ? (hero ? 0.45 : 0.5) : hero || boardCenter ? 0.5 : 0.32,
      y: hero ? (mobile ? 0.52 : 0.5) : mobile ? 0.215 : 0.5,
    };
  };
  if (!part || part === "lens") {
    if (hero)
      return frame(
        center(0, 0, -0.43),
        mobile ? 0.55 : 0.54,
        mobile ? 0.34 : 0.23,
        mobile ? 1.82 : 1.81,
        0.67,
        mobile ? -0.105 : -0.045,
      );
    if (chapter === "explore" || part === "lens")
      return clip
        ? frame(center(-0.15, 0.045, -0.32), -0.65, 0.34, 1.65, 0.68)
        : frame(center(0, 0.015, -0.29), 0.31, 0.17, 1.65, 0.68);
    if (chapter === "sensing")
      return clip
        ? frame(anchor("tof"), -0.1, 0.2, 0.63, 0.36)
        : frame(center(0, 0.055, -0.045), 0.12, 0.13, 1.49, 0.61);
    if (chapter === "construction")
      return clip
        ? frame(anchor("clip-core"), -0.18, 0.32, 0.6, 0.36)
        : frame(center(-0.36, 0.06, -0.49), -1.94, 0.39, 1.36, 0.72);
    return frame(
      center(0, 0, -0.38),
      clip ? -0.38 : 0.55,
      0.23,
      1.78,
      0.77,
      -0.035,
    );
  }
  const a = anchor(part),
    side = Math.sign(a.x) || 1;
  switch (part) {
    case "eye":
      return frame(a, 2.73, 0.19, 0.22, 0.16);
    case "tof":
    case "light":
    case "camera":
      return frame(a, side * 0.18, 0.16, clip ? 0.24 : 0.27, 0.18);
    case "temple-right":
    case "board":
      return frame(anchor("board"), -1.55, 0.17, 0.51, 0.3);
    case "temple-left":
    case "battery":
      return frame(anchor("battery"), 1.53, 0.21, 0.52, 0.3);
    case "imu":
      return frame(a, -1.56, 0.14, 0.19, 0.14);
    case "touch":
      return frame(a, -1.49, 0.18, 0.35, 0.22);
    case "radio":
      return frame(a, clip ? 0.3 : -1.5, 0.16, clip ? 0.28 : 0.22, 0.18);
    case "clip-core":
      return frame(a, -0.15, 0.35, 0.55, 0.31);
    case "charge":
      return frame(a, clip ? 0.34 : 1.26, -0.83, 0.28, 0.18);
    case "clamp":
      return frame(a, 2.82, 0.52, 0.46, 0.3);
    case "button":
      return frame(a, 0.23, 0.86, 0.35, 0.24);
  }
}
export function mixPose(output: Pose, a: Pose, b: Pose, t: number) {
  output.target.lerpVectors(a.target, b.target, t);
  output.yaw =
    a.yaw + Math.atan2(Math.sin(b.yaw - a.yaw), Math.cos(b.yaw - a.yaw)) * t;
  for (const key of ["pitch", "roll", "distance", "x", "y"] as const)
    output[key] = a[key] + (b[key] - a[key]) * t;
  return output;
}
export const copyPose = (p: Pose): Pose => ({ ...p, target: p.target.clone() });
export function ease(v: number) {
  const t = Math.max(0, Math.min(1, v));
  return t * t * (3 - 2 * t);
}

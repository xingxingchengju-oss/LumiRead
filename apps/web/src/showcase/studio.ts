import {
  Color,
  DoubleSide,
  Material,
  Mesh,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  Object3D,
  PlaneGeometry,
  PMREMGenerator,
  Scene,
  Vector3,
  type WebGLRenderer,
} from "three";
import {
  exposedTemple,
  isPart,
  type Chapter,
  type Part,
  type Selection,
  type Wear,
} from "./product";

export function studioEnvironment(gl: WebGLRenderer) {
  const room = new Scene();
  room.background = new Color(0x787b80);
  const panel = new PlaneGeometry();
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
  softbox(-2.5, 3.3, 2.3, 5.5, 1.15, [7.0, 7.2, 7.6]);
  softbox(3.5, 1.2, 1.2, 1.0, 4.0, [4.6, 4.3, 3.9]);
  softbox(0.5, 1.9, -3.5, 5.0, 0.72, [6.5, 7.0, 7.8]);
  softbox(-0.65, 0.62, 3.6, 3.25, 0.19, [4.0, 3.8, 3.5]);
  const pmrem = new PMREMGenerator(gl);
  const light = pmrem.fromScene(room, 0.035);
  panel.dispose();
  lamps.forEach((m) => m.dispose());
  pmrem.dispose();
  return light;
}

function taggedPart(mesh: Object3D) {
  for (let item: Object3D | null = mesh; item; item = item.parent) {
    if (isPart(item.userData.part)) return item.userData.part;
  }
}

export function prepareModel(asset: Object3D) {
  const root = asset.clone(true);
  const hits: Mesh[] = [];
  const tags = new Map<Object3D, Part>();
  const anchors = new Map<Part, Object3D>();
  const roles = new Map<string, Object3D>();
  const optics = new Set<Material>();
  const inside: { mesh: Mesh; part: Part }[] = [];
  const shells = new Map<
    Material,
    {
      part: Part;
      opacity: number;
      transparent: boolean;
      depthWrite: boolean;
      transmission: number;
    }
  >();
  const copies = new Map<string, Material>();
  root.traverse((node) => {
    if (isPart(node.userData.anchor)) anchors.set(node.userData.anchor, node);
    if (typeof node.userData.role === "string")
      roles.set(node.userData.role, node);
    if (!(node instanceof Mesh)) return;
    const part = taggedPart(node);
    if (!part) return;
    hits.push(node);
    tags.set(node, part);
    if (part === "board" || part === "battery")
      inside.push({ mesh: node, part });
    if (part !== "lens" && part !== "temple-right" && part !== "temple-left")
      return;
    const copy = (original: Material) => {
      const key = part + original.uuid;
      const existing = copies.get(key);
      if (existing) return existing;
      const m = original.clone();
      copies.set(key, m);
      if (part === "lens") optics.add(m);
      else
        shells.set(m, {
          part,
          opacity: m.opacity,
          transparent: m.transparent,
          depthWrite: m.depthWrite,
          transmission: m instanceof MeshPhysicalMaterial ? m.transmission : 0,
        });
      return m;
    };
    node.material = Array.isArray(node.material)
      ? node.material.map(copy)
      : copy(node.material);
  });
  root.updateMatrixWorld(true);
  const atRest = new Map(
    [...anchors].map(([id, node]) => [
      id,
      node.getWorldPosition(new Vector3()),
    ]),
  );
  return {
    root,
    hits,
    tags,
    anchors,
    atRest,
    roles,
    optics,
    inside,
    shells,
    copies,
  };
}
export type Model = ReturnType<typeof prepareModel>;

export function opticsAndInterior(model: Model, wear: Wear, part?: Part) {
  model.optics.forEach((mat) => {
    mat.visible = wear !== "open";
  });
  const side = exposedTemple(part);
  model.inside.forEach(({ mesh, part: component }) => {
    mesh.visible = side === exposedTemple(component);
  });
  model.shells.forEach((original, mat) => {
    const seeInside = original.part === side;
    if (mat instanceof MeshPhysicalMaterial)
      mat.transmission = seeInside ? 0 : original.transmission;
    const transparent = seeInside || original.transparent;
    if (mat.transparent !== transparent) {
      mat.transparent = transparent;
      mat.needsUpdate = true;
    }
    mat.depthWrite = seeInside ? false : original.depthWrite;
  });
}

export type Pose = {
  target: Vector3;
  yaw: number;
  pitch: number;
  roll: number;
  width: number;
  height: number;
};
const pose = (
  target: Vector3,
  yaw: number,
  pitch: number,
  width: number,
  height: number,
  roll = 0,
): Pose => ({ target, yaw, pitch, roll, width, height });
const center = (x = 0, y = 0, z = -0.57) => new Vector3(x, y, z);
const anchor = (model: Model, id: Part) =>
  model.atRest.get(id)?.clone() ?? center();

export function cameraPose(
  model: Model,
  chapter: Chapter,
  wear: Wear,
  selected: Selection | null,
  compact: boolean,
): Pose {
  const clip = wear === "clip";
  const id = selected?.part;
  if (clip && (id === "lens" || (!id && chapter === "explore")))
    return pose(center(0, 0.01, -0.66), -1.16, 0.38, 2.02, 0.88);
  if (id === "lens")
    return pose(center(0, 0.035, -0.23), 0.2, 0.14, 1.64, 0.71);
  if (!id) {
    if (chapter === "explore")
      return pose(center(0, 0.04, -0.3), 0.23, 0.15, 1.77, 0.77);
    if (chapter === "sensing")
      return clip
        ? pose(anchor(model, "tof"), 0.13, 0.13, 0.82, 0.43)
        : pose(center(0, 0.055, -0.06), 0.09, 0.08, 1.57, 0.68);
    if (chapter === "construction")
      return clip
        ? pose(anchor(model, "clamp"), -2.42, 0.48, 1.06, 0.57)
        : pose(center(0, 0.005, -0.63), 0.8, 0.34, 1.99, 0.91);
    if (compact && chapter === "top")
      return pose(center(0, 0, -0.61), 0.52, 0.25, 1.89, 0.79, -0.1);
    return pose(center(0, -0.012, -0.58), 0.45, 0.095, 1.86, 0.73);
  }
  let target = anchor(model, id);
  if (
    selected?.point &&
    (id === "rim" || id === "ear" || id === "hinge" || id === "nose")
  )
    target = new Vector3(...selected.point);
  const side = target.x < 0 ? -1 : 1;
  switch (id) {
    case "camera":
    case "led":
      return pose(target, 0.18 * side, 0.12, clip ? 0.29 : 0.34, 0.22);
    case "tof":
    case "light":
      return pose(target, 0.16 * side, 0.085, clip ? 0.27 : 0.34, 0.21);
    case "rim":
      return pose(target, 0.32 * side, 0.17, 0.9, 0.52);
    case "nose":
      return pose(target, 2.85 * side, 0.13, 0.59, 0.4);
    case "hinge":
      return pose(target, 1.17 * side, 0.19, 0.43, 0.29);
    case "ear":
      return pose(target, 1.7 * side, 0.24, 0.68, 0.39);
    case "board":
    case "battery":
    case "temple-left":
    case "temple-right": {
      const inner = exposedTemple(id) === "temple-right" ? "board" : "battery";
      return pose(anchor(model, inner), 1.44 * side, 0.36, 0.74, 0.41);
    }
    case "clamp":
    case "pad":
      return pose(target, 2.7 * side, 0.45, 0.48, 0.31);
    case "button":
      return pose(target, 0.32 * side, 0.8, 0.46, 0.3);
    case "shell":
      return pose(target, 0.33 * side, 0.18, 0.76, 0.4);
  }
}

export function shortenAngle(from: number, to: number) {
  return from + Math.atan2(Math.sin(to - from), Math.cos(to - from));
}
export function copyPose(p: Pose): Pose {
  return { ...p, target: p.target.clone() };
}
export function ease(t: number) {
  const n = Math.min(1, Math.max(0, t));
  return n * n * (3 - 2 * n);
}

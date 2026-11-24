import {
  Component,
  Suspense,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import {
  MathUtils,
  OrthographicCamera,
  Raycaster,
  Vector2,
  Vector3,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import {
  exposedTemple,
  markers,
  parts,
  type Chapter,
  type Part,
  type Selection,
  type Wear,
} from "./product";
import {
  cameraPose,
  copyPose,
  ease,
  opticsAndInterior,
  prepareModel,
  shortenAngle,
  studioEnvironment,
  type Pose,
} from "./studio";

type Props = {
  frameUrl: string;
  clipUrl: string;
  wear: Wear;
  chapter: Chapter;
  selected: Selection | null;
  rotate: boolean;
  reduced: boolean;
  sleep: boolean;
  select: (item: Selection) => void;
  pause: () => void;
  ready: () => void;
  fail: () => void;
};
type Flight = { from: Pose; to: Pose; started: number };
type Markers = RefObject<Map<Part, HTMLButtonElement>>;
const fineParts: Part[] = ["camera", "led", "tof", "light", "button"];
const clipParts: Part[] = [...fineParts, "shell", "clamp", "pad", "lens"];

function Studio(props: Props & { pins: Markers }) {
  const { gl, scene, camera, size, invalidate } = useThree();
  const cam = camera as OrthographicCamera;
  const surface = gl.domElement.closest<HTMLElement>(".lr-surface");
  const compact = window.innerWidth <= 700;
  const [frameFile, clipFile] = useLoader(GLTFLoader, [
    props.frameUrl,
    props.clipUrl,
  ]);
  const frame = useMemo(() => prepareModel(frameFile.scene), [frameFile]);
  const clip = useMemo(() => prepareModel(clipFile.scene), [clipFile]);
  const module = clip.roles.get("clip-module"),
    jaw = clip.roles.get("clip-jaw");
  const rest = useMemo(
    () => ({ position: module?.position.clone(), jaw: jaw?.rotation.x ?? 0 }),
    [module, jaw],
  );
  const current = useRef<Pose | null>(null);
  const flight = useRef<Flight | null>(null);
  const mounted = useRef(0);
  const installation = useRef({ from: 0, to: 0, started: 0 });
  const firstFrame = useRef(true);
  const changingView = useRef(false);
  const live = useRef(props);
  live.current = props;
  const vectors = useMemo(
    () => ({
      point: new Vector3(),
      projected: new Vector3(),
      direction: new Vector3(),
      pixel: new Vector2(),
      ray: new Raycaster(),
    }),
    [],
  );
  const { ready, fail } = props;

  useLayoutEffect(() => {
    const light = studioEnvironment(gl);
    scene.environment = light.texture;
    scene.environmentIntensity = 0.95;
    const lost = (e: Event) => {
      e.preventDefault();
      fail();
    };
    gl.domElement.addEventListener("webglcontextlost", lost);
    return () => {
      gl.domElement.removeEventListener("webglcontextlost", lost);
      surface?.removeAttribute("aria-busy");
      scene.environment = null;
      light.dispose();
    };
  }, [gl, scene, fail, surface]);
  useEffect(
    () => () => {
      for (const model of [frame, clip])
        model.copies.forEach((material) => material.dispose());
    },
    [frame, clip],
  );

  useLayoutEffect(() => {
    const model = props.wear === "clip" ? clip : frame;
    const goal = cameraPose(
      model,
      props.chapter,
      props.wear,
      props.selected,
      compact,
    );
    if (!current.current || props.reduced) {
      current.current = goal;
      flight.current = null;
    } else {
      goal.yaw = shortenAngle(current.current.yaw, goal.yaw);
      const attaching = props.wear === "clip" && installation.current.to === 0;
      flight.current = {
        from: copyPose(current.current),
        to: goal,
        started:
          performance.now() + (attaching ? (1 - mounted.current) * 680 : 0),
      };
    }
    opticsAndInterior(frame, props.wear, props.selected?.part);
    changingView.current = true;
    surface?.setAttribute("aria-busy", "true");
    invalidate();
  }, [
    frame,
    clip,
    compact,
    surface,
    props.wear,
    props.selected,
    props.chapter,
    props.reduced,
    invalidate,
  ]);
  useLayoutEffect(() => {
    installation.current = {
      from: mounted.current,
      to: props.wear === "clip" ? 1 : 0,
      started: performance.now(),
    };
    invalidate();
  }, [props.wear, invalidate]);
  useEffect(() => {
    invalidate();
  }, [props.rotate, props.sleep, size, invalidate]);

  useEffect(() => {
    const canvas = gl.domElement;
    const ray = vectors.ray;
    const world = new Vector3(),
      projected = new Vector3(),
      intoScene = new Vector3();
    // The lens meshes remain raycastable even with their material hidden in open-frame mode.
    function pick(x: number, y: number): Selection | null {
      const p = live.current;
      const isClip = p.wear === "clip";
      const model = isClip ? clip : frame;
      if (!model.root.visible) return null;
      const bounds = canvas.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return null;
      vectors.pixel.set(
        ((x - bounds.left) / bounds.width) * 2 - 1,
        1 - ((y - bounds.top) / bounds.height) * 2,
      );
      ray.setFromCamera(vectors.pixel, cam);
      const ghost = !isClip && exposedTemple(p.selected?.part);
      const hit = ray
        .intersectObjects(model.hits, false)
        .find((h) => h.object.visible && model.tags.get(h.object) !== ghost);
      let part = hit && model.tags.get(hit.object);
      if (part && fineParts.includes(part)) return { part };
      // A small screen-space tolerance makes the recessed windows tappable on a phone.
      // Only consider anchors at the first visible surface along the pointer ray.
      cam.getWorldDirection(intoScene);
      let nearest = bounds.width < 600 ? 15 : 10;
      for (const id of fineParts) {
        const node = model.anchors.get(id);
        if (!node) continue;
        node.getWorldPosition(world);
        projected.copy(world).project(cam);
        if (projected.z < -1 || projected.z > 1) continue;
        if (hit && world.sub(hit.point).dot(intoScene) > 0.035) continue;
        if (!hit && intoScene.z > -0.18) continue;
        const pixels = Math.hypot(
          ((projected.x - vectors.pixel.x) * bounds.width) / 2,
          ((projected.y - vectors.pixel.y) * bounds.height) / 2,
        );
        if (pixels < nearest) {
          nearest = pixels;
          part = id;
        }
      }
      if (!part) return null;
      if (isClip && !clipParts.includes(part)) part = "lens";
      return { part, point: hit?.point.toArray() };
    }

    let gesture: {
      id: number;
      x: number;
      y: number;
      lastX: number;
      lastY: number;
      dragged: boolean;
      scroll: boolean;
    } | null = null;
    let hoverTime = 0;
    const down = (e: PointerEvent) => {
      if (!e.isPrimary || e.button !== 0) return;
      gesture = {
        id: e.pointerId,
        x: e.clientX,
        y: e.clientY,
        lastX: e.clientX,
        lastY: e.clientY,
        dragged: false,
        scroll: false,
      };
      canvas.setPointerCapture(e.pointerId);
    };
    const move = (e: PointerEvent) => {
      if (!gesture || e.pointerId !== gesture.id) {
        if (e.pointerType === "mouse" && performance.now() - hoverTime > 65) {
          hoverTime = performance.now();
          const hovered = pick(e.clientX, e.clientY);
          canvas.style.cursor = hovered ? "pointer" : "grab";
          canvas.title = hovered ? parts[hovered.part].name : "拖动旋转";
        }
        return;
      }
      if (gesture.scroll) return;
      const dx = e.clientX - gesture.x,
        dy = e.clientY - gesture.y;
      if (!gesture.dragged) {
        if (Math.hypot(dx, dy) < 6) return;
        if (e.pointerType === "touch" && Math.abs(dy) > Math.abs(dx)) {
          gesture.scroll = true;
          return;
        }
        gesture.dragged = true;
        live.current.pause();
        flight.current = null;
      }
      const p = current.current;
      if (p) {
        p.yaw -= (e.clientX - gesture.lastX) * 0.009;
        p.pitch = MathUtils.clamp(
          p.pitch + (e.clientY - gesture.lastY) * 0.006,
          -1.02,
          1.13,
        );
        invalidate();
      }
      gesture.lastX = e.clientX;
      gesture.lastY = e.clientY;
      canvas.style.cursor = "grabbing";
    };
    const up = (e: PointerEvent) => {
      if (gesture?.id !== e.pointerId) return;
      const click =
        !gesture.dragged &&
        !gesture.scroll &&
        Math.hypot(e.clientX - gesture.x, e.clientY - gesture.y) < 7;
      gesture = null;
      if (canvas.hasPointerCapture(e.pointerId))
        canvas.releasePointerCapture(e.pointerId);
      canvas.style.cursor = "grab";
      if (click) {
        const picked = pick(e.clientX, e.clientY);
        if (picked) live.current.select(picked);
      }
    };
    const cancel = () => {
      gesture = null;
      canvas.style.cursor = "grab";
    };
    const key = (e: KeyboardEvent) => {
      if (
        e.target !== surface ||
        !current.current ||
        !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)
      )
        return;
      e.preventDefault();
      live.current.pause();
      flight.current = null;
      const p = current.current;
      if (e.key === "ArrowLeft" || e.key === "ArrowRight")
        p.yaw += e.key === "ArrowLeft" ? -0.16 : 0.16;
      else
        p.pitch = MathUtils.clamp(
          p.pitch + (e.key === "ArrowUp" ? 0.13 : -0.13),
          -1.02,
          1.13,
        );
      invalidate();
    };
    surface?.addEventListener("keydown", key);
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", cancel);
    canvas.addEventListener("lostpointercapture", cancel);
    return () => {
      surface?.removeEventListener("keydown", key);
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointercancel", cancel);
      canvas.removeEventListener("lostpointercapture", cancel);
    };
  }, [cam, gl, frame, clip, vectors, invalidate, surface]);

  useFrame((_, delta) => {
    const p = current.current;
    if (!p || props.sleep || !size.width || !size.height) return;
    const dt = Math.min(delta, 0.08);
    let moving = false;
    const travel = flight.current;
    if (travel) {
      const t = ease((performance.now() - travel.started) / 480);
      p.target.lerpVectors(travel.from.target, travel.to.target, t);
      for (const k of ["yaw", "pitch", "roll", "width", "height"] as const)
        p[k] = MathUtils.lerp(travel.from[k], travel.to[k], t);
      if (t === 1) flight.current = null;
      else moving = true;
    } else if (props.rotate) {
      p.yaw += dt * ((2 * Math.PI) / 80);
      moving = true;
    }

    const goal = props.wear === "clip" ? 1 : 0;
    const mount = installation.current;
    // A component close-up belongs to the chosen glasses, even mid-removal.
    if (props.selected && props.selected.part !== "lens") mount.from = mount.to;
    const duration = Math.max(1, Math.abs(mount.to - mount.from) * 900);
    const progress = MathUtils.clamp(
      (performance.now() - mount.started) / duration,
      0,
      1,
    );
    mounted.current =
      props.reduced || progress === 1
        ? goal
        : MathUtils.lerp(mount.from, mount.to, progress);
    const a = mounted.current;
    moving ||= a !== goal;
    clip.root.visible = goal === 1 || a > 0;
    frame.root.visible = !clip.root.visible;
    if (module && rest.position && jaw) {
      const lift = 1 - ease((a - 0.18) / 0.65);
      module.position.copy(rest.position);
      module.position.y += 0.25 * lift;
      module.position.z += 0.13 * lift;
      jaw.rotation.x =
        rest.jaw + 0.38 * ease(a / 0.19) * (1 - ease((a - 0.7) / 0.3));
      clip.root.updateMatrixWorld(true);
    }
    const inside = exposedTemple(props.selected?.part);
    frame.shells.forEach((orig, mat) => {
      const target = orig.part === inside ? 0.095 : orig.opacity;
      if (Math.abs(target - mat.opacity) <= 0.002) {
        mat.opacity = target;
        return;
      }
      mat.opacity = props.reduced
        ? target
        : MathUtils.lerp(mat.opacity, target, 1 - Math.exp(-dt * 13));
      moving = true;
    });

    const c = Math.cos(p.pitch);
    cam.position
      .set(Math.sin(p.yaw) * c, Math.sin(p.pitch), Math.cos(p.yaw) * c)
      .multiplyScalar(4)
      .add(p.target);
    cam.lookAt(p.target);
    cam.rotateZ(p.roll);
    cam.zoom = Math.min(size.width / p.width, size.height / p.height);
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld();
    cam.getWorldDirection(vectors.direction);
    const model = clip.root.visible ? clip : frame;
    props.pins.current.forEach((button, id) => {
      const node = model.anchors.get(id);
      if (!node) {
        button.hidden = true;
        return;
      }
      node.getWorldPosition(vectors.point);
      vectors.projected.copy(vectors.point).project(cam);
      const { x, y, z } = vectors.projected;
      let visible = Math.abs(x) < 0.98 && Math.abs(y) < 0.97 && Math.abs(z) < 1;
      if (id === "lens" || fineParts.includes(id))
        visible &&= vectors.direction.z < -0.18;
      if (id === "temple-left") visible &&= vectors.direction.x < -0.12;
      if (id === "temple-right") visible &&= vectors.direction.x > 0.12;
      button.hidden = !visible;
      if (visible) {
        button.style.left = (x + 1) * 50 + "%";
        button.style.top = (1 - y) * 50 + "%";
      }
    });
    if (firstFrame.current) {
      firstFrame.current = false;
      ready();
    }
    if (changingView.current && !flight.current && a === goal) {
      surface?.setAttribute("aria-busy", "false");
      changingView.current = false;
    }
    if (moving) invalidate();
  });

  return (
    <>
      <hemisphereLight args={[0xf9faff, 0x848078, 1.3]} />
      <directionalLight
        position={[-2, 4, 3]}
        intensity={2.1}
        color={0xfff7ed}
      />
      <directionalLight
        position={[2, 2, -2]}
        intensity={2.0}
        color={0xe1eaff}
      />
      <primitive object={frame.root} dispose={null} />
      <primitive object={clip.root} dispose={null} />
    </>
  );
}

class Boundary extends Component<
  { children: ReactNode; fail: () => void },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.fail();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

function supportsWebGL() {
  try {
    const probe = document.createElement("canvas").getContext("webgl2");
    if (!probe) return false;
    probe.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

export default function Viewer(props: Props) {
  const [supported] = useState(supportsWebGL);
  const pins = useRef(new Map<Part, HTMLButtonElement>());
  useEffect(() => {
    if (!supported) props.fail();
  }, [supported, props.fail]);
  if (!supported) return null;
  return (
    <div className="lr-canvas">
      <Boundary fail={props.fail}>
        <Canvas
          orthographic
          camera={{ near: 0.01, far: 16, position: [1, 0.5, 4] }}
          dpr={[1.25, 2]}
          frameloop="demand"
          gl={{
            alpha: true,
            antialias: true,
            powerPreference: "high-performance",
          }}
          onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
        >
          <Suspense fallback={null}>
            <Studio {...props} pins={pins} />
          </Suspense>
        </Canvas>
      </Boundary>
      {markers(props.chapter, props.wear === "clip", !!props.selected).map(
        (id) => (
          <button
            type="button"
            hidden
            key={id}
            className="lr-pin"
            aria-label={parts[id].name + "热点"}
            ref={(el) => {
              if (el) pins.current.set(id, el);
              else pins.current.delete(id);
            }}
            onClick={() => props.select({ part: id })}
          >
            <span aria-hidden="true">+</span>
          </button>
        ),
      )}
    </div>
  );
}

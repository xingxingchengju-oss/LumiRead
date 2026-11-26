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
  AgXToneMapping,
  AdditiveBlending,
  CanvasTexture,
  DirectionalLight,
  HemisphereLight,
  MathUtils,
  MeshBasicMaterial,
  PerspectiveCamera,
  Raycaster,
  Sprite,
  SRGBColorSpace,
  TextureLoader,
  Vector2,
  Vector3,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import {
  cameraChapters,
  exposedShell,
  interactivePart,
  markers,
  parts,
  type Chapter,
  type Part,
  type ScrollTrack,
  type Selection,
  type Wear,
} from "./product";
import {
  cameraPose,
  copyPose,
  ease,
  mixPose,
  prepareModel,
  studioEnvironment,
  type Shell,
} from "./studio";

type Props = {
  frameUrl: string;
  clipUrl: string;
  wear: Wear;
  chapter: Chapter;
  selected: Selection | null;
  track: RefObject<ScrollTrack>;
  project: RefObject<(() => void) | null>;
  rotate: boolean;
  reduced: boolean;
  sleep: boolean;
  photographing: boolean;
  select: (s: Selection, trigger?: HTMLElement) => void;
  pause: () => void;
  ready: (url: string) => void;
  fail: () => void;
};
type Pins = RefObject<Map<Part, HTMLButtonElement>>;

function Lighting({ fail }: { fail: () => void }) {
  const { gl, scene } = useThree();
  useLayoutEffect(() => {
    const environment = studioEnvironment(gl);
    scene.environment = environment.texture;
    const lost = (e: Event) => {
      e.preventDefault();
      fail();
    };
    gl.domElement.addEventListener("webglcontextlost", lost);
    return () => {
      gl.domElement.removeEventListener("webglcontextlost", lost);
      scene.environment = null;
      environment.dispose();
    };
  }, [gl, scene, fail]);
  return null;
}

function glowTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, "rgba(227,255,235,1)");
  g.addColorStop(0.22, "rgba(129,255,203,.55)");
  g.addColorStop(1, "rgba(85,255,191,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  return new CanvasTexture(canvas);
}

function Studio(
  props: Props & {
    url: string;
    pins: Pins;
    origin: RefObject<HTMLSpanElement | null>;
  },
) {
  const { gl, scene, camera, size, invalidate } = useThree();
  const cam = camera as PerspectiveCamera;
  const isClip = props.wear === "clip";
  const asset = useLoader(GLTFLoader, props.url);
  const shadow = useLoader(
    TextureLoader,
    "/products/" + (isClip ? "clip" : "frame") + "-shadow.png",
  );
  const model = useMemo(
    () => prepareModel(asset.scene, isClip),
    [asset, isClip],
  );
  const glow = useMemo(glowTexture, []);
  const surface = gl.domElement.closest<HTMLElement>(".lr-surface");
  const light = useRef<HemisphereLight>(null),
    key = useRef<DirectionalLight>(null),
    floor = useRef<MeshBasicMaterial>(null),
    indicator = useRef<Sprite>(null);
  const part = props.selected?.part;
  const stops = useMemo(
    () =>
      cameraChapters.map((c) =>
        cameraPose(
          model,
          c.id,
          props.wear,
          undefined,
          size.width || 1,
          size.height || 1,
        ),
      ),
    [model, props.wear, size.width, size.height],
  );
  const detail = useMemo(
    () =>
      part
        ? cameraPose(
            model,
            props.chapter,
            props.wear,
            part,
            size.width || 1,
            size.height || 1,
          )
        : null,
    [model, props.wear, props.chapter, part, size.width, size.height],
  );
  const actual = useRef(copyPose(stops[0])),
    desired = useRef(copyPose(stops[0]));
  const travel = useRef<{
    from: ReturnType<typeof copyPose>;
    started: number;
  } | null>(null);
  const installedAt = useRef(performance.now()),
    first = useRef(true),
    resuming = useRef(false),
    scrollPosition = useRef(props.track.current.progress),
    lastProgress = useRef(-1);
  const controls = useRef({
    yaw: 0,
    pitch: 0,
    phase: 0,
    drift: 0,
    hover: 0,
    hoverY: 0,
    shift: 0,
    shiftY: 0,
    spinYaw: 0,
    spinPitch: 0,
    recenter: false,
  });
  const sectionWeight = useRef(0),
    ghost = useRef<Shell | null>(null);
  const live = useRef(props);
  live.current = props;
  const vectors = useMemo(
    () => ({
      p: new Vector3(),
      q: new Vector3(),
      direction: new Vector3(),
      ray: new Raycaster(),
      pointer: new Vector2(),
    }),
    [],
  );
  const attachment = useMemo(() => {
    const module = model.roles.get("clip-module"),
      jaw = model.roles.get("clip-jaw");
    return module && jaw
      ? {
          module,
          jaw,
          pos: module.position.clone(),
          angle: jaw.rotation.x,
          last: -1,
        }
      : null;
  }, [model]);
  useLayoutEffect(() => {
    const track = props.track.current;
    if (props.sleep) {
      resuming.current = true;
      return;
    }
    track.redraw = invalidate;
    return () => {
      if (track.redraw === invalidate) track.redraw = undefined;
    };
  }, [props.track, props.sleep, invalidate]);
  useLayoutEffect(() => {
    const c = controls.current;
    if (first.current || props.reduced || resuming.current)
      travel.current = null;
    else {
      const from = copyPose(actual.current);
      from.yaw += c.yaw + c.drift + c.shift;
      from.pitch += c.pitch + c.shiftY;
      travel.current = { from, started: performance.now() };
    }
    c.yaw = c.pitch = c.drift = c.shift = c.shiftY = c.hover = c.hoverY = 0;
    c.spinYaw = c.spinPitch = 0;
    c.recenter = false;
    surface?.setAttribute("aria-busy", "true");
    model.lenses.forEach((m) => {
      m.visible = props.wear !== "open";
    });
    invalidate();
  }, [model, part, props.wear, props.reduced, stops, surface, invalidate]);
  useEffect(() => {
    invalidate();
  }, [
    props.rotate,
    props.photographing,
    props.sleep,
    props.chapter,
    detail,
    invalidate,
  ]);
  useEffect(
    () => () => {
      model.copies.forEach((m) => m.dispose());
      glow.dispose();
    },
    [model, glow],
  );

  useEffect(() => {
    const canvas = gl.domElement,
      { ray, pointer } = vectors;
    const fine: Part[] = ["camera", "tof", "light", "eye", "button"];
    function pick(x: number, y: number): Part | undefined {
      const rect = canvas.getBoundingClientRect();
      pointer.set(
        ((x - rect.left) / rect.width) * 2 - 1,
        1 - ((y - rect.top) / rect.height) * 2,
      );
      ray.setFromCamera(pointer, cam);
      if (!ray.ray.intersectsBox(model.bounds)) return;
      const hit = ray
        .intersectObjects(model.hits, false)
        .find(
          (h) => h.object.visible && model.tags.get(h.object) !== ghost.current,
        );
      const tag = hit && model.tags.get(hit.object);
      let result = tag && interactivePart(tag, isClip);
      if (result && fine.includes(result)) return result;
      let nearest = size.width < 700 ? 14 : 9;
      for (const id of fine) {
        const node = model.anchors.get(id);
        if (!node) continue;
        node.getWorldPosition(vectors.p);
        const facing = cam.position.z - vectors.p.z;
        if (id === "eye" ? facing > 0 : facing < 0) continue;
        if (
          hit &&
          vectors.q.copy(vectors.p).sub(hit.point).dot(ray.ray.direction) >
            0.035
        )
          continue;
        vectors.q.copy(vectors.p).project(cam);
        if (Math.abs(vectors.q.z) > 1) continue;
        const d = Math.hypot(
          ((vectors.q.x - pointer.x) * rect.width) / 2,
          ((vectors.q.y - pointer.y) * rect.height) / 2,
        );
        if (d < nearest) {
          nearest = d;
          result = id;
        }
      }
      return result || undefined;
    }
    let gesture: {
      id: number;
      x: number;
      y: number;
      lastX: number;
      lastY: number;
      time: number;
      speedX: number;
      speedY: number;
      dragged: boolean;
      scroll: boolean;
    } | null = null;
    let hoverAt = 0;
    function down(e: PointerEvent) {
      if (!e.isPrimary || e.button !== 0) return;
      const c = controls.current;
      c.spinYaw = c.spinPitch = 0;
      c.recenter = false;
      gesture = {
        id: e.pointerId,
        x: e.clientX,
        y: e.clientY,
        lastX: e.clientX,
        lastY: e.clientY,
        time: e.timeStamp,
        speedX: 0,
        speedY: 0,
        dragged: false,
        scroll: false,
      };
      canvas.setPointerCapture(e.pointerId);
    }
    function move(e: PointerEvent) {
      const c = controls.current;
      if (!gesture || gesture.id !== e.pointerId) {
        if (e.pointerType === "mouse" && performance.now() - hoverAt > 50) {
          hoverAt = performance.now();
          const id = pick(e.clientX, e.clientY);
          canvas.style.cursor = id ? "pointer" : "grab";
          canvas.title = id ? parts[id].name : "拖动旋转";
          if (
            live.current.rotate &&
            live.current.chapter === "top" &&
            !live.current.selected
          ) {
            c.hover = MathUtils.clamp(
              (e.offsetX / size.width - 0.5) * 0.07,
              -0.035,
              0.035,
            );
            c.hoverY = MathUtils.clamp(
              (0.5 - e.offsetY / size.height) * 0.04,
              -0.02,
              0.02,
            );
            invalidate();
          }
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
      }
      const dxAngle = (gesture.lastX - e.clientX) * 0.008,
        dyAngle = (e.clientY - gesture.lastY) * 0.006;
      const seconds = Math.max(0.008, (e.timeStamp - gesture.time) / 1000);
      gesture.speedX = MathUtils.clamp(dxAngle / seconds, -2.2, 2.2);
      gesture.speedY = MathUtils.clamp(dyAngle / seconds, -1.5, 1.5);
      gesture.time = e.timeStamp;
      c.yaw += dxAngle;
      c.pitch = MathUtils.clamp(c.pitch + dyAngle, -1.15, 1.15);
      gesture.lastX = e.clientX;
      gesture.lastY = e.clientY;
      canvas.style.cursor = "grabbing";
      invalidate();
    }
    function cancel() {
      gesture = null;
      canvas.style.cursor = "grab";
    }
    function up(e: PointerEvent) {
      if (!gesture || gesture.id !== e.pointerId) return;
      if (
        gesture.dragged &&
        !live.current.reduced &&
        e.timeStamp - gesture.time < 80
      ) {
        controls.current.spinYaw = gesture.speedX;
        controls.current.spinPitch = gesture.speedY;
        invalidate();
      }
      const click =
        !gesture.dragged &&
        !gesture.scroll &&
        Math.hypot(e.clientX - gesture.x, e.clientY - gesture.y) < 7;
      cancel();
      if (canvas.hasPointerCapture(e.pointerId))
        canvas.releasePointerCapture(e.pointerId);
      if (click) {
        const id = pick(e.clientX, e.clientY);
        if (id) live.current.select({ part: id });
      }
    }
    function keydown(e: KeyboardEvent) {
      if (
        live.current.sleep ||
        (live.current.chapter === "construction" && !live.current.selected) ||
        e.target !== surface ||
        !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)
      )
        return;
      e.preventDefault();
      live.current.pause();
      const c = controls.current;
      c.spinYaw = c.spinPitch = 0;
      c.recenter = false;
      if (e.key === "ArrowLeft" || e.key === "ArrowRight")
        c.yaw += e.key === "ArrowLeft" ? -0.16 : 0.16;
      else
        c.pitch = MathUtils.clamp(
          c.pitch + (e.key === "ArrowUp" ? 0.13 : -0.13),
          -1.15,
          1.15,
        );
      invalidate();
    }
    surface?.addEventListener("keydown", keydown);
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", cancel);
    canvas.addEventListener("lostpointercapture", cancel);
    return () => {
      surface?.removeEventListener("keydown", keydown);
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointercancel", cancel);
      canvas.removeEventListener("lostpointercapture", cancel);
    };
  }, [
    gl,
    cam,
    model,
    isClip,
    surface,
    size.width,
    size.height,
    invalidate,
    vectors,
  ]);

  useFrame((_, delta) => {
    if (props.sleep || !size.width || !size.height) return;
    const dt = Math.min(delta, 0.06),
      c = controls.current;
    const raw = props.track.current.progress;
    const goal = props.reduced ? Math.round(raw) : raw;
    const price = stops.length - 1;
    const cut =
      resuming.current ||
      (!part &&
        goal !== scrollPosition.current &&
        (goal === price || scrollPosition.current === price));
    if (cut) {
      travel.current = null;
      c.yaw = c.pitch = c.drift = c.shift = c.shiftY = c.hover = c.hoverY = 0;
      c.spinYaw = c.spinPitch = 0;
      resuming.current = false;
    }
    const follow =
      cut || first.current || props.reduced || part
        ? goal
        : MathUtils.damp(scrollPosition.current, goal, 25, dt);
    const progress = Math.abs(follow - goal) < 0.0007 ? goal : follow;
    scrollPosition.current = progress;
    let moving = progress !== goal;
    const low = Math.min(stops.length - 1, Math.floor(progress)),
      high = Math.min(stops.length - 1, low + 1);
    const blend = ease(progress - low);
    const target =
      detail || mixPose(desired.current, stops[low], stops[high], blend);
    if (!part && lastProgress.current >= 0 && raw !== lastProgress.current) {
      c.recenter = true;
      c.spinYaw = c.spinPitch = c.hover = c.hoverY = 0;
    }
    if (c.recenter) {
      c.recenter = false;
      for (const key of ["yaw", "pitch", "drift", "shift", "shiftY"] as const) {
        c[key] = props.reduced ? 0 : MathUtils.damp(c[key], 0, 16, dt);
        if (Math.abs(c[key]) < 0.001) c[key] = 0;
        else c.recenter = true;
      }
      moving ||= c.recenter;
    }
    if (c.spinYaw || c.spinPitch) {
      const decay = Math.exp(-10 * dt);
      c.yaw += (c.spinYaw * (1 - decay)) / 10;
      c.pitch = MathUtils.clamp(
        c.pitch + (c.spinPitch * (1 - decay)) / 10,
        -1.15,
        1.15,
      );
      c.spinYaw *= decay;
      c.spinPitch *= decay;
      if (Math.abs(c.spinYaw) + Math.abs(c.spinPitch) < 0.01)
        c.spinYaw = c.spinPitch = 0;
      else moving = true;
    }
    lastProgress.current = raw;
    const p = actual.current;
    if (travel.current && !props.reduced) {
      const sec = Math.max(
        0,
        (performance.now() - travel.current.started) / 1000,
      );
      const t =
        sec >= 0.48 ? 1 : (1 - Math.exp(-sec * 10)) / (1 - Math.exp(-4.8));
      mixPose(p, travel.current.from, target, t);
      if (t === 1) travel.current = null;
      else moving = true;
    } else mixPose(p, target, target, 1);
    if (!part && progress < 1 && props.rotate) {
      c.phase += dt * 0.34;
      c.drift = Math.sin(c.phase) * 0.157 * (1 - ease(progress));
      c.shift = MathUtils.damp(c.shift, c.hover, 7, dt);
      c.shiftY = MathUtils.damp(c.shiftY, c.hoverY, 7, dt);
      moving = true;
    }
    const yaw = p.yaw + c.yaw + c.drift + c.shift,
      pitch = MathUtils.clamp(p.pitch + c.pitch + c.shiftY, -1.32, 1.35);
    cam.position
      .set(
        Math.sin(yaw) * Math.cos(pitch),
        Math.sin(pitch),
        Math.cos(yaw) * Math.cos(pitch),
      )
      .multiplyScalar(p.distance)
      .add(p.target);
    cam.lookAt(p.target);
    cam.rotateZ(p.roll);
    cam.setViewOffset(
      size.width,
      size.height,
      (0.5 - p.x) * size.width,
      (0.5 - p.y) * size.height,
      size.width,
      size.height,
    );
    cam.updateMatrixWorld();
    if (attachment) {
      const a =
        props.reduced || (part && part !== "lens")
          ? 1
          : MathUtils.clamp(
              (performance.now() - installedAt.current) / 880,
              0,
              1,
            );
      if (a !== attachment.last) {
        attachment.module.position.copy(attachment.pos);
        const lift = 1 - ease((a - 0.16) / 0.58);
        attachment.module.position.y += 0.23 * lift;
        attachment.module.position.z += 0.1 * lift;
        attachment.jaw.rotation.x =
          attachment.angle +
          0.4 * ease(a / 0.15) * (1 - ease((a - 0.68) / 0.31));
        model.root.updateMatrixWorld(true);
        attachment.last = a;
      }
      moving ||= a < 1;
    }
    const shell = exposedShell(part, isClip);
    const wanted = shell ? 1 : 0;
    sectionWeight.current =
      props.reduced || cut || !part
        ? wanted
        : MathUtils.damp(sectionWeight.current, wanted, 17, dt);
    if (Math.abs(sectionWeight.current - wanted) < 0.006)
      sectionWeight.current = wanted;
    moving ||= sectionWeight.current !== wanted;
    ghost.current = sectionWeight.current > 0.05 ? shell : null;
    model.section(shell, sectionWeight.current);
    const luminous = (id: Chapter) =>
      Number(id === "explore" || id === "specifications");
    const wash = part
      ? Number(part === "lens")
      : MathUtils.lerp(
          luminous(cameraChapters[low].id),
          luminous(cameraChapters[high].id),
          blend,
        );
    scene.environmentIntensity = 1.05 + wash * 0.32;
    if (light.current) light.current.intensity = 0.43 + wash * 0.43;
    if (key.current) key.current.intensity = 2.15 + wash * 0.24;
    if (floor.current)
      floor.current.opacity =
        (part && part !== "lens" ? 0 : 1) *
        (0.22 + wash * 0.58) *
        (1 - ease((-pitch - 0.06) / 0.32));
    model.lamps.forEach((m) => {
      m.emissiveIntensity = props.photographing ? 3 : 0;
    });
    if (indicator.current) {
      indicator.current.visible = props.photographing;
      if (props.photographing)
        model.anchors.get("led")?.getWorldPosition(indicator.current.position);
    }
    function position(el: HTMLElement, id: string, pin: boolean) {
      const node = model.anchors.get(id);
      if (!node) {
        el.hidden = true;
        return;
      }
      node.getWorldPosition(vectors.p);
      vectors.q.copy(vectors.p).project(cam);
      const { x, y, z } = vectors.q;
      vectors.direction.copy(cam.position).sub(vectors.p).normalize();
      let visible =
        Math.abs(x) < 0.995 && Math.abs(y) < 0.99 && Math.abs(z) < 1;
      if (pin && ["lens", "camera", "light", "tof"].includes(id))
        visible &&= vectors.direction.z > 0.12;
      if (pin && id === "eye") visible &&= vectors.direction.z < 0.1;
      if (pin && id === "temple-right") visible &&= vectors.direction.x < 0;
      el.hidden = !visible;
      if (!visible) return;
      const left = (x + 1) * 50,
        top = (1 - y) * 50;
      if (!(Math.abs(parseFloat(el.style.left) - left) < 0.012))
        el.style.left = left + "%";
      if (!(Math.abs(parseFloat(el.style.top) - top) < 0.012))
        el.style.top = top + "%";
    }
    props.pins.current.forEach((el, id) => position(el, id, true));
    if (part === "tof" && props.origin.current) {
      position(props.origin.current, "tof", false);
      props.project.current?.();
    }
    if (first.current) {
      first.current = false;
      props.ready(props.url);
    }
    if (
      !travel.current &&
      (!attachment || attachment.last === 1) &&
      sectionWeight.current === wanted
    )
      surface?.setAttribute("aria-busy", "false");
    if (moving) invalidate();
  });
  return (
    <>
      <hemisphereLight ref={light} args={[0xf3f6ff, 0x6f6460, 0.48]} />
      <directionalLight
        ref={key}
        position={[-2.8, 4.3, 2.5]}
        color={0xfff4e6}
        intensity={2.2}
      />
      <directionalLight
        position={[1.4, 2, -3]}
        color={0xe2eaff}
        intensity={2.4}
      />
      <primitive object={model.root} dispose={null} />
      <mesh
        position={[0, -0.225, -0.55]}
        rotation={[-Math.PI / 2, 0, 0]}
        renderOrder={-1}
      >
        <planeGeometry args={[2.1, 2.1]} />
        <meshBasicMaterial
          ref={floor}
          map={shadow}
          color={0x24232a}
          transparent
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>
      <sprite ref={indicator} scale={[0.034, 0.034, 1]} visible={false}>
        <spriteMaterial
          map={glow}
          blending={AdditiveBlending}
          transparent
          depthWrite={false}
          toneMapped={false}
        />
      </sprite>
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
  const pins = useRef(new Map<Part, HTMLButtonElement>()),
    origin = useRef<HTMLSpanElement>(null);
  const url = props.wear === "clip" ? props.clipUrl : props.frameUrl;
  useEffect(() => {
    if (!supported) props.fail();
  }, [supported, props.fail]);
  if (!supported) return null;
  return (
    <div className="lr-canvas">
      <Boundary fail={props.fail}>
        <Canvas
          camera={{ fov: 24, near: 0.025, far: 40, position: [1, 0.5, 4] }}
          dpr={[1, 2]}
          frameloop={props.sleep ? "never" : "demand"}
          gl={{
            alpha: true,
            antialias: true,
            powerPreference: "high-performance",
          }}
          onCreated={({ gl }) => {
            gl.setClearColor(0x000000, 0);
            gl.toneMapping = AgXToneMapping;
            gl.toneMappingExposure = 1.08;
            gl.outputColorSpace = SRGBColorSpace;
          }}
        >
          <Lighting fail={props.fail} />
          <Suspense fallback={null} key={url}>
            <Studio {...props} url={url} pins={pins} origin={origin} />
          </Suspense>
        </Canvas>
      </Boundary>
      {props.selected?.part === "tof" && (
        <span className="lr-range-origin" ref={origin} aria-hidden="true" />
      )}
      {props.chapter !== "construction" &&
        markers(props.chapter, props.wear === "clip", !!props.selected).map(
          (id) => (
            <button
              type="button"
              hidden
              key={id}
              className="lr-pin"
              data-return={"pin-" + id}
              aria-label={parts[id].name + "热点"}
              ref={(el) => {
                if (el) pins.current.set(id, el);
                else pins.current.delete(id);
              }}
              onClick={(e) => props.select({ part: id }, e.currentTarget)}
            >
              <span aria-hidden="true">+</span>
            </button>
          ),
        )}
    </div>
  );
}

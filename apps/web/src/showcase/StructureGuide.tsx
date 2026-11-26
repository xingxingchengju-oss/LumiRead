import { useEffect, useMemo, useRef, useState } from "react";
import {
  markers,
  parts,
  type PosterPoints,
  type Selection,
  type Wear,
} from "./product";
import { clipSteps, frameSteps, type StructureStep } from "./structure";
import "./structure.css";

type Shot = {
  step: StructureStep;
  index: number;
  view: string;
  whole: string;
  key: string;
};
type DecodedShot = Shot & { hasMacro: boolean; hasLocator: boolean };
const source = (view: string) => "/products/" + view + ".webp";
const position = ([x, y]: [number, number]) => ({
  left: x * 100 + "%",
  top: y * 100 + "%",
});

export default function StructureGuide({
  active,
  warm,
  wear,
  index,
  reveal,
  reduced,
  points,
  weight,
  select,
}: {
  active: boolean;
  warm: boolean;
  wear: Wear;
  index: number;
  reveal: boolean;
  reduced: boolean;
  points?: PosterPoints;
  weight: number;
  select: (item: Selection, trigger: HTMLElement) => void;
}) {
  const steps = wear === "clip" ? clipSteps : frameSteps;
  const step = steps[index];
  const whole =
    wear === "open" ? "frame-open" : wear === "clip" ? "clip" : "frame";
  const view = !reveal && step.cover ? step.cover : step.view;
  const requested = useMemo<Shot>(
    () => ({ step, index, whole, view, key: whole + "/" + view }),
    [step, index, whole, view],
  );
  const [shots, setShots] = useState<{
    current: DecodedShot;
    previous?: DecodedShot;
  }>();
  const cache = useRef(new Map<string, HTMLImageElement>());

  useEffect(() => {
    if (!active && !warm) return;
    let live = true;
    function decode(key: string) {
      const images = cache.current;
      let image = images.get(key);
      if (image) images.delete(key);
      else {
        image = new Image();
        image.decoding = "async";
        image.src = source(key);
      }
      images.set(key, image);
      // Keep the locator and nearby full-resolution plates within mobile memory budgets.
      if (images.size > 5) images.delete(images.keys().next().value!);
      return image.decode().then(
        () => true,
        () => {
          if (images.get(key) === image) images.delete(key);
          return false;
        },
      );
    }
    async function load() {
      const [macro, overview] = await Promise.all([
        decode(view),
        decode(whole),
      ]);
      if (!live || !active) return;
      const visible: DecodedShot = {
        ...requested,
        view: macro ? view : whole,
        hasMacro: !!macro,
        hasLocator: !!overview,
      };
      setShots((old) =>
        old?.current.key === visible.key &&
        old.current.hasMacro === visible.hasMacro &&
        old.current.hasLocator === visible.hasLocator
          ? old
          : {
              current: visible,
              previous:
                reduced || old?.current.whole !== whole
                  ? undefined
                  : old.current,
            },
      );
      const next = steps[index + 1];
      if (view !== step.view) void decode(step.view);
      if (next) void decode(next.cover ?? next.view);
    }
    void load();
    return () => {
      live = false;
    };
  }, [active, warm, requested, view, whole, index, steps, step, reduced]);

  const loaded = shots?.current.whole === whole ? shots : undefined;
  const shown = loaded?.current ?? requested;
  const locator = points?.[shown.whole];
  const clip = shown.whole === "clip";
  const labels = shown.view === shown.step.view ? shown.step.labels : undefined;
  const macroPoints = points?.[shown.view];
  return (
    <section
      className="lr-guide"
      aria-label="佩戴结构导览"
      aria-hidden={!active}
      inert={!active}
      data-active={active}
      data-step={shown.index + 1}
      data-view={loaded?.current.view}
      aria-busy={active && loaded?.current.key !== requested.key}
    >
      <div className="lr-guide-layout">
        <figure
          className="lr-guide-plate"
          aria-label={shown.step.location + "特写"}
        >
          {loaded &&
            [loaded.previous, loaded.current].map(
              (shot) =>
                shot &&
                (shot.hasMacro || shot.hasLocator) && (
                  <img
                    key={shot.key}
                    src={source(shot.view)}
                    className={
                      shot === loaded.current
                        ? "lr-shot-current"
                        : "lr-shot-previous"
                    }
                    alt={
                      shot !== loaded.current
                        ? ""
                        : !shot.hasMacro
                          ? "眼镜全貌"
                          : shot.step.location +
                            (shot.view === shot.step.cover
                              ? "的闭合外壳"
                              : "的产品设计图")
                    }
                    onAnimationEnd={() => {
                      if (shot === loaded.current && loaded.previous)
                        setShots((old) =>
                          old?.current === shot ? { current: shot } : old,
                        );
                    }}
                  />
                ),
            )}
          {loaded &&
            labels?.map(
              (label) =>
                macroPoints?.[label.anchor] && (
                  <span
                    key={shown.view + label.anchor}
                    className="lr-guide-note"
                    data-below={!!label.below}
                    style={position(macroPoints[label.anchor])}
                  >
                    {label.text}
                  </span>
                ),
            )}
          {loaded && !loaded.current.hasMacro && (
            <span className="lr-guide-error" role="status">
              这张特写暂时无法载入。
            </span>
          )}
        </figure>
        <div className="lr-guide-copy">
          <div className="lr-guide-meta">
            <span>佩戴结构 · {clip ? "智能夹片" : "一体镜"}</span>
            <span>
              第 {shown.index + 1} 幕 / 共 {steps.length} 幕
            </span>
          </div>
          <div className="lr-guide-heading">
            <h2 aria-live="polite" aria-atomic="true">
              {shown.step.title}
            </h2>
            <figure className="lr-locator" aria-label="整镜部件定位">
              <div className="lr-locator-art">
                {loaded?.current.hasLocator && (
                  <img
                    src={source(shown.whole)}
                    alt={
                      clip
                        ? "安装夹片后的整镜"
                        : wear === "open"
                          ? "无镜片一体镜"
                          : "平光一体镜"
                    }
                  />
                )}
                {loaded?.current.hasLocator && locator?.[shown.step.part] && (
                  <i
                    className="lr-locator-target"
                    aria-hidden="true"
                    style={position(locator[shown.step.part])}
                  />
                )}
                {loaded?.current.hasLocator &&
                  markers("construction", clip, false).map(
                    (id, i) =>
                      locator?.[id] && (
                        <button
                          key={id}
                          className="lr-locator-pin"
                          data-side={i}
                          style={position(locator[id])}
                          type="button"
                          data-return={"pin-" + id}
                          aria-label={parts[id].name + "热点"}
                          title={parts[id].name}
                          onClick={(e) => select({ part: id }, e.currentTarget)}
                        >
                          <i aria-hidden="true">+</i>
                        </button>
                      ),
                  )}
              </div>
              <figcaption>{shown.step.location}</figcaption>
            </figure>
          </div>
          <p className="lr-guide-description">{shown.step.description}</p>
          {shown.step.part === "eye" && (
            <a className="lr-inline-link" href="/#reading">
              观看研究样片 <span aria-hidden="true">↗</span>
            </a>
          )}
          {clip && shown.index === 0 && (
            <p className="lr-spec-note">夹装模块目标重量约 {weight} g</p>
          )}
        </div>
      </div>
    </section>
  );
}

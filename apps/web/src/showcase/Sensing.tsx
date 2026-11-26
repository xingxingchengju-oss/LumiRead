import { useLayoutEffect, useRef, useState, type RefObject } from "react";
import worksheet from "../../../../data/demo/worksheet-original.png";
import type { Part } from "./product";

export function SensingPaper({
  part,
  photographing,
  capture,
}: {
  part?: Part;
  photographing: boolean;
  capture: () => void;
}) {
  const [dim, setDim] = useState(false);
  return (
    <figure className="lr-study">
      <div
        className="lr-study-sheet"
        data-dim={part === "light" && dim}
        data-camera={part === "camera"}
        data-flash={photographing}
      >
        <img
          src={worksheet}
          alt="算术作业示例，第二题是九减四"
          width="1050"
          height="429"
        />
        {part === "tof" && <i className="lr-paper-target" aria-hidden="true" />}
        {part === "camera" && (
          <span className="lr-viewfinder" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
          </span>
        )}
      </div>
      <figcaption>
        <span>
          {part === "tof"
            ? "测距落点示意"
            : part === "light"
              ? dim
                ? "佩戴处偏暗 · 示意"
                : "佩戴处较亮 · 示意"
              : part === "camera"
                ? photographing
                  ? "拍摄指示灯亮起"
                  : "作业取景示意"
                : "示例作业纸"}
        </span>
        {part === "light" && (
          <button type="button" onClick={() => setDim((v) => !v)}>
            {dim ? "调亮光线" : "调暗光线"}
          </button>
        )}
        {part === "camera" && (
          <button type="button" onClick={capture}>
            模拟拍摄
          </button>
        )}
      </figcaption>
    </figure>
  );
}

export function RangeLine({
  project,
}: {
  project: RefObject<(() => void) | null>;
}) {
  const svg = useRef<SVGSVGElement>(null),
    line = useRef<SVGPolylineElement>(null);
  useLayoutEffect(() => {
    const parent = svg.current?.parentElement;
    if (!parent || !svg.current || !line.current) return;
    const draw = () => {
      const origin = parent.querySelector<HTMLElement>(
        ".lr-range-origin:not([hidden])",
      );
      const target = parent.querySelector<HTMLElement>(".lr-paper-target");
      if (!line.current) return;
      if (!origin || !target) {
        line.current.style.visibility = "hidden";
        return;
      }
      const a = origin.getBoundingClientRect(),
        b = target.getBoundingClientRect(),
        box = parent.getBoundingClientRect();
      const clip = target.closest(".lr-copy")?.getBoundingClientRect();
      const y = b.top + b.height / 2;
      const visible =
        (origin.checkVisibility?.() ?? true) &&
        a.width > 0 &&
        b.width > 0 &&
        (!clip || (y >= clip.top && y <= clip.bottom));
      line.current.style.visibility = visible ? "visible" : "hidden";
      if (!visible) return;
      const sx = a.left + a.width / 2 - box.left,
        sy = a.top + a.height / 2 - box.top;
      const tx = b.left + b.width / 2 - box.left,
        ty = y - box.top;
      const path =
        box.width <= 700
          ? [
              [sx, sy],
              [sx, Math.min(sy + 18, box.height * 0.36)],
              [12, box.height * 0.39],
              [12, ty],
              [tx, ty],
            ]
          : [
              [sx, sy],
              [tx, ty],
            ];
      line.current.setAttribute(
        "points",
        path.map((p) => p.join(",")).join(" "),
      );
    };
    project.current = draw;
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(parent);
    const sheet = parent.querySelector(".lr-study");
    if (sheet) ro.observe(sheet);
    parent.addEventListener("scroll", draw, true);
    return () => {
      ro.disconnect();
      parent.removeEventListener("scroll", draw, true);
      project.current = null;
    };
  }, [project]);
  return (
    <svg ref={svg} className="lr-measure-line" aria-hidden="true">
      <polyline ref={line} />
    </svg>
  );
}

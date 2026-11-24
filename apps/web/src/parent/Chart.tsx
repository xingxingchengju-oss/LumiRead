import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart, RadarChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  GraphicComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";
echarts.use([
  LineChart,
  RadarChart,
  GridComponent,
  TooltipComponent,
  GraphicComponent,
  SVGRenderer,
]);

export function Chart({
  options,
  label,
  height = 230,
}: {
  options: (width: number, height: number) => EChartsCoreOption;
  label: string;
  height?: number;
}) {
  const node = useRef<HTMLDivElement>(null);
  const optionRef = useRef(options);
  const drawRef = useRef<() => void>(() => {});
  useEffect(() => {
    if (!node.current) return;
    const el = node.current;
    const chart = echarts.init(el, undefined, { renderer: "svg" });
    const draw = () => {
      if (el.clientWidth) {
        chart.resize();
        chart.setOption(optionRef.current(el.clientWidth, el.clientHeight), {
          notMerge: true,
        });
      }
    };
    drawRef.current = draw;
    const observer = new ResizeObserver(draw);
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, []);
  useEffect(() => {
    optionRef.current = options;
    drawRef.current();
  }, [options]);
  return (
    <div
      role="img"
      aria-label={label}
      style={{ width: "100%", height }}
      ref={node}
    />
  );
}

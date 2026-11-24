import { useCallback, useEffect, useRef, useState } from "react";
import { api, message } from "../api";

export const skills: Record<string, string> = {
  mixed_arithmetic: "四则混合运算",
  fractions: "分数通分约分",
  decimals: "小数乘除",
  equations: "简易方程",
  area: "几何面积",
  word_modeling: "应用题列式",
};
export function dateTime(stamp: number | string, seconds = false) {
  const d = new Date(typeof stamp === "number" ? stamp * 1000 : stamp);
  return d.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    ...(seconds ? { second: "2-digit" } : {}),
  });
}

// Only the resource affected by an event is re-read. Keep one fetch in flight and
// coalesce events received while it is pending into a single subsequent refresh.
export function useResource<T>(
  path: string | null,
  bus: EventTarget,
  events: string,
) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const reloadRef = useRef<() => void>(() => {});
  const reload = useCallback(() => reloadRef.current(), []);
  useEffect(() => {
    let active = true,
      pending = false,
      dirty = false;
    const controller = new AbortController();
    setData(undefined);
    setError("");
    if (path === null) {
      reloadRef.current = () => {};
      return;
    }
    const resourcePath = path;
    async function load() {
      if (pending) {
        dirty = true;
        return;
      }
      pending = true;
      try {
        const result = await api<T>(resourcePath, {
          signal: controller.signal,
        });
        if (active) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (active) setError(message(e));
      } finally {
        pending = false;
        if (active && dirty) {
          dirty = false;
          void load();
        }
      }
    }
    const run = () => {
      void load();
    };
    const names = events.split(" ").filter(Boolean);
    names.forEach((name) => bus.addEventListener(name, run));
    reloadRef.current = run;
    run();
    return () => {
      active = false;
      controller.abort();
      names.forEach((name) => bus.removeEventListener(name, run));
    };
  }, [path, bus, events]);
  return { data, error, reload };
}

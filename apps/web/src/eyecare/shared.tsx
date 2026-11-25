import { useEffect, useState } from "react";
import { useResource } from "../parent/data";

const updates = new EventTarget();
export function usePublic<T>(path: string) {
  return useResource<T>(path, updates, "");
}
export function Loading({
  error,
  reload,
}: {
  error: string;
  reload: () => void;
}) {
  return error ? (
    <p role="alert">
      {error} <button onClick={reload}>重试</button>
    </p>
  ) : (
    <p role="status">正在读取记录…</p>
  );
}
export const media = ["未阅读", "纸质", "电子", "物体文字"];
export const duration = (t: number) => {
  const s = Math.max(0, Math.floor(t));
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
};
export function usePlayback(start: number, end: number) {
  const [position, seek] = useState(start);
  const [playing, play] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [revision, revise] = useState(0);
  useEffect(() => {
    if (!playing) return;
    const initial = position,
      anchor = performance.now();
    const id = window.setInterval(() => {
      const p = Math.min(
        end,
        initial + ((performance.now() - anchor) * speed) / 1000,
      );
      seek(p);
      if (p >= end) play(false);
    }, 100);
    return () => clearInterval(id);
    // Re-anchor on a user action. Timer ticks only advance the displayed cursor.
  }, [playing, speed, start, end, revision]);
  function move(t: number) {
    seek(Math.min(end, Math.max(start, t)));
    revise((r) => r + 1);
  }
  function toggle() {
    if (!playing && position >= end) move(start);
    play(!playing);
  }
  return { position, playing, speed, setSpeed, move, toggle };
}
export type Player = ReturnType<typeof usePlayback>;
export function Controls({
  player,
  start,
  end,
}: {
  player: Player;
  start: number;
  end: number;
}) {
  return (
    <div className="ec-controls">
      <button onClick={player.toggle}>
        {player.playing ? "暂停" : player.position >= end ? "重播" : "播放"}
      </button>
      <label>
        速度{" "}
        <select
          value={player.speed}
          onChange={(e) => player.setSpeed(Number(e.target.value))}
        >
          {[1, 4, 10].map((n) => (
            <option key={n} value={n}>
              {n}×
            </option>
          ))}
        </select>
      </label>
      <label className="ec-seek">
        原始时间{" "}
        <input
          type="range"
          min={start}
          max={end}
          step="any"
          value={player.position}
          onChange={(e) => player.move(Number(e.target.value))}
        />
      </label>
      <output>
        {duration(player.position)} / {duration(end)}
      </output>
    </div>
  );
}

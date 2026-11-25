import type { components } from "../../../../packages/contracts/types";
import { useEffect, useRef, useState } from "react";
import { api, json, message } from "../api";
import { duration } from "./shared";
type State = "active" | "away" | "rest" | "end";
type Scene = "paper" | "electronic" | "writing";
type Change = { at: number; state: State };
type Log = { origin: number; scene: Scene; changes: Change[] };
type Result = components["schemas"]["ClockResult"];
const key = "lumiread-manual-study-v1";
const sceneNames = {
  paper: "纸质阅读",
  writing: "手动书写",
  electronic: "电子学习",
};
const stateNames = {
  active: "读写中",
  away: "短暂停顿",
  rest: "休息中",
  end: "已结束",
};
const now = () => Math.floor(Date.now() / 1000);
function load(): Log | null {
  try {
    const l = JSON.parse(localStorage.getItem(key) || "null");
    return l &&
      Object.hasOwn(sceneNames, l.scene) &&
      Number.isFinite(l.origin) &&
      Array.isArray(l.changes) &&
      l.changes.length &&
      l.changes.every(
        (c: Change) =>
          Number.isFinite(c.at) && Object.hasOwn(stateNames, c.state),
      )
      ? l
      : null;
  } catch {
    return null;
  }
}
export default function Timer() {
  const [mode, setMode] = useState<"manual" | "rule_demo">("manual");
  return (
    <section className="ec-card">
      <h2>读写时长与休息</h2>
      <p>
        连续读写满 40 分钟提醒休息。选定电子学习时在 30 分钟提醒，建议远眺放松约
        10 分钟。
      </p>
      <div className="ec-switch">
        <button
          aria-pressed={mode === "manual"}
          onClick={() => setMode("manual")}
        >
          实际手动计时
        </button>
        <button
          aria-pressed={mode === "rule_demo"}
          onClick={() => setMode("rule_demo")}
        >
          规则演示时间轴
        </button>
      </div>
      <Stopwatch key={mode} mode={mode} />
      <p className="ec-note">
        自动识别的阅读时长可在<a href="#reading">阅读识别页</a>
        查看。纯书写支持手动计时。短暂停顿时保留进度，连续离开或缺测满 10
        分钟后重新累计。选择「开始休息」并持续 10 分钟可记录完成休息。{" "}
        <a href="https://www.moe.gov.cn/srcsite/A17/moe_943/s3285/201808/t20180830_346672.html">
          读写与远眺建议依据 ↗
        </a>
      </p>
    </section>
  );
}
function Stopwatch({ mode }: { mode: "manual" | "rule_demo" }) {
  const sim = mode === "rule_demo";
  const [log, setLog] = useState<Log | null>(() => (sim ? null : load()));
  const [scene, setScene] = useState<Scene>(log?.scene || "paper");
  const [time, setTime] = useState(0),
    [tick, setTick] = useState(now);
  const [result, setResult] = useState<Result | null>(null),
    [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const last = log?.changes.at(-1);
  const running = !!log && last?.state !== "end";
  const t = log
    ? last?.state === "end"
      ? last.at
      : sim
        ? time
        : Math.max(last?.at || 0, tick - log.origin)
    : 0;
  const request = useRef(0);
  useEffect(() => {
    if (!running || sim) return;
    const h = window.setInterval(() => setTick(now()), 500);
    return () => clearInterval(h);
  }, [running, sim]);
  useEffect(() => {
    if (!sim && log)
      try {
        localStorage.setItem(key, JSON.stringify(log));
      } catch {
        /* The timer still works in memory. */
      }
  }, [log, sim]);
  useEffect(() => {
    const controller = new AbortController(),
      seq = ++request.current;
    if (!log) {
      setResult(null);
      return;
    }
    const spans = log.changes.map((c, i) => ({
      state: c.state,
      start: c.at,
      end: log.changes[i + 1]?.at ?? t,
    }));
    api<Result>("/eye-care/clock", {
      ...json("POST", { source: mode, scene: log.scene, spans }),
      signal: controller.signal,
    })
      .then((v) => {
        if (seq === request.current) {
          setResult(v);
          setError("");
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(message(e));
      });
    return () => controller.abort();
  }, [log, t, mode, retry]);
  function begin() {
    const at = now();
    setTime(0);
    setTick(at);
    setResult(null);
    setLog({ origin: at, scene, changes: [{ at: 0, state: "active" }] });
  }
  function change(state: State) {
    if (!log || !running || last?.state === state) return;
    const at = sim ? t : Math.max(t, now() - log.origin);
    setTick(now());
    setLog({ ...log, changes: [...log.changes, { at, state }] });
  }
  return (
    <>
      <div className="ec-inputs">
        <label>
          学习场景{" "}
          <select
            value={scene}
            disabled={running}
            onChange={(e) => setScene(e.target.value as Scene)}
          >
            {Object.entries(sceneNames).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <strong>
          {sim ? "模拟时间 · 不计入实测报告" : "本浏览器手动学习记录"}
        </strong>
      </div>
      <div className="ec-timer">
        <small>
          {last ? stateNames[last.state] : "待开始"} · 本段已累计读写
        </small>
        <strong>{duration(result?.bout_seconds ?? 0)}</strong>
        <span>
          合计 {duration(result?.active_seconds ?? 0)}　已休息{" "}
          {duration(result?.break_seconds ?? 0)}
        </span>
      </div>
      <div className="ec-controls">
        {!running ? (
          <button onClick={begin}>{last ? "开始新一段" : "开始计时"}</button>
        ) : (
          <>
            {last?.state !== "active" && (
              <button onClick={() => change("active")}>继续读写</button>
            )}
            {last?.state === "active" && (
              <button onClick={() => change("away")}>暂时移开视线</button>
            )}
            {last?.state !== "rest" && (
              <button onClick={() => change("rest")}>开始休息</button>
            )}
            <button className="outline" onClick={() => change("end")}>
              结束本段
            </button>
          </>
        )}
        {sim &&
          running &&
          [1, 60, 600, 1800, 2400].map((n) => (
            <button
              className="outline"
              key={n}
              onClick={() => setTime((v) => v + n)}
            >
              推进 {n === 1 ? "1 秒" : n / 60 + " 分钟"}
            </button>
          ))}
      </div>
      {error && (
        <p role="alert">
          {error} <button onClick={() => setRetry((x) => x + 1)}>重试</button>
        </p>
      )}
      {result?.events.map((e) => (
        <p role="status" className="ec-event" key={e.kind + e.source_second}>
          <strong>
            {e.kind === "rest_due"
              ? "请休息，远眺放松约 10 分钟。"
              : "已完成 10 分钟休息。"}
          </strong>
          <span>
            {duration(e.source_second)} · {sim ? "规则演示" : "手动计时"}
          </span>
        </p>
      ))}
    </>
  );
}

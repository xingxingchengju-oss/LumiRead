import { useEffect, useRef, useState } from "react";
import { api, json, message } from "../api";
import { brightnessNotice, distanceNotice } from "../eyeMessages";
import { Chart } from "./Chart";
import "./clouclip.css";

type Metric = "Dis" | "Lux";
type Sample = {
  line: number;
  Date: string;
  Dis: number | null;
  Lux: number | null;
  distance_cm: number | null;
  illuminance_lx: number | null;
  offset_seconds: number;
};
type Replay = {
  source: {
    file_url: string;
    supplement: string;
    sha256: string;
    timezone: string;
  };
  segment: {
    title: string;
    first_line: number;
    last_line: number;
    starts_at: string;
    ends_at: string;
    total_samples: number;
    duration_seconds: number;
  };
  status: "ready" | "playing" | "paused" | "finished";
  speed: number;
  generation: number;
  position_seconds: number;
  records: Sample[];
  events: {
    metric: Metric;
    start_line: number;
    started_at: string;
    ended_at: string | null;
    end_line: number | null;
  }[];
};
const statuses = {
  ready: "待播放",
  playing: "播放中",
  paused: "已暂停",
  finished: "已播完",
};
const timePart = (date: string) => date.slice(11);

function SensorTrend({ replay, metric }: { replay: Replay; metric: Metric }) {
  const distance = metric === "Dis";
  const title = distance ? "工作距离" : "环境照度";
  const unit = distance ? "cm" : "lx";
  const color = distance ? "#366321" : "#785121";
  const latest = replay.records.at(-1);
  const value =
    latest && (distance ? latest.distance_cm : latest.illuminance_lx);
  const threshold = distance ? 33 : 300;
  const recovery = distance ? 35 : 350;
  const duration = replay.segment.duration_seconds;
  const start = Date.parse(replay.segment.starts_at.replace(" ", "T") + "Z");
  const plot = replay.records.map((r) => [
    r.offset_seconds,
    distance ? r.distance_cm : r.illuminance_lx,
  ]);
  return (
    <section className="clouclip-metric">
      <header>
        <div>
          <h4>{title}</h4>
          <small>{metric}</small>
        </div>
        <div className="clouclip-reading">
          {value ?? "—"} <small>{unit}</small>
        </div>
      </header>
      <Chart
        label={title + "趋势，单位" + unit + "。逐点数值见下方原始记录。"}
        height={134}
        options={() => ({
          animation: false,
          grid: { left: 42, right: 18, top: 14, bottom: 29 },
          textStyle: { color: "#3c443a", fontFamily: "inherit" },
          xAxis: {
            type: "value",
            min: 0,
            max: duration,
            interval: duration / 2,
            axisLabel: {
              fontSize: 10,
              formatter: (n: number) =>
                new Date(start + n * 1000).toISOString().slice(11, 19),
            },
            axisLine: { lineStyle: { color: "#9aab95" } },
            splitLine: { show: false },
          },
          yAxis: {
            type: "value",
            min: 0,
            splitNumber: 3,
            axisLabel: { fontSize: 10 },
            splitLine: { lineStyle: { color: "#e3e9dd" } },
            axisLine: { show: false },
          },
          series: [
            {
              type: "line",
              data: [
                [0, threshold],
                [duration, threshold],
              ],
              silent: true,
              symbol: "none",
              lineStyle: { color: "#a66444", type: "dashed", width: 1 },
            },
            {
              type: "line",
              data: [
                [0, recovery],
                [duration, recovery],
              ],
              silent: true,
              symbol: "none",
              lineStyle: { color: "#7a8874", type: "dotted", width: 1 },
            },
            {
              type: "line",
              data: plot,
              connectNulls: false,
              symbolSize: 5,
              lineStyle: { color, width: 2 },
              itemStyle: { color },
            },
          ],
        })}
      />
      <small className="clouclip-limits">
        演示阈值 · 触发 &lt; {threshold} {unit} · 恢复 ≥ {recovery} {unit}
      </small>
    </section>
  );
}

function AlertSummary({
  replay,
  error,
  open,
}: {
  replay: Replay | null;
  error: string;
  open: () => void;
}) {
  const current = replay?.records.at(-1);
  const active = replay?.events.filter((event) => !event.ended_at) ?? [];
  const recent = active.length ? active : (replay?.events.slice(-1) ?? []);
  return (
    <section className="paper care-summary" aria-label="最近护眼提醒">
      <div>
        <h2>最近护眼提醒</h2>
        <p>Clouclip 公开传感器记录回放 · 本账号配对的成人观测片段</p>
        {error ? (
          <p role="alert">{error}</p>
        ) : recent.length ? (
          recent.map((event) => {
            const point = replay?.records.find(
              (row) => row.line === event.start_line,
            );
            const distance = event.metric === "Dis";
            return (
              <div
                className="care-episode"
                key={event.start_line + event.metric}
              >
                <strong>
                  <span aria-hidden="true">{event.ended_at ? "✓ " : "⚠ "}</span>
                  {distance ? "工作距离偏近" : "环境光偏暗"} ·{" "}
                  {event.ended_at ? "已解除" : "提醒中"}
                </strong>
                <p>
                  {event.started_at} 触发 ·{" "}
                  {distance ? point?.distance_cm : point?.illuminance_lx}{" "}
                  {distance ? "cm" : "lx"}
                  {event.ended_at && " · " + timePart(event.ended_at) + " 解除"}
                  （原设备时间）
                </p>
              </div>
            );
          })
        ) : (
          <p>
            {!replay
              ? "正在读取回放记录…"
              : current
                ? "截至 " + current.Date + "，已播放的样本均未触发提醒。"
                : "尚未开始回放。播放片段后，这里会显示触发与恢复记录。"}
          </p>
        )}
      </div>
      <button type="button" className="outline" onClick={open}>
        查看护眼记录
      </button>
    </section>
  );
}

function ReplayPanel({ sid, onOpen }: { sid: string; onOpen?: () => void }) {
  const endpoint = "/sessions/" + encodeURIComponent(sid) + "/clouclip";
  const [replay, setReplay] = useState<Replay | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const revision = useRef(0);
  const alive = useRef(true);
  async function refresh(signal?: AbortSignal) {
    if (pending.current) return;
    const id = ++revision.current;
    try {
      const body = await api<Replay>(endpoint, { signal });
      if (alive.current && id === revision.current) {
        setReplay((previous) =>
          previous &&
          previous.status === body.status &&
          previous.generation === body.generation &&
          previous.speed === body.speed &&
          previous.position_seconds === body.position_seconds
            ? previous
            : body,
        );
        setError("");
      }
      return body;
    } catch (e) {
      if (alive.current && id === revision.current && !signal?.aborted)
        setError(message(e));
    }
  }
  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    let timer = 0;
    async function poll() {
      const body = await refresh(controller.signal);
      if (!controller.signal.aborted)
        timer = window.setTimeout(
          poll,
          body?.status === "playing" ? (body.speed === 10 ? 250 : 700) : 2500,
        );
    }
    void poll();
    return () => {
      alive.current = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [endpoint]);
  async function control(
    action: "play" | "pause" | "replay" | "speed",
    speed?: number,
  ) {
    if (!replay || pending.current) return;
    pending.current = true;
    ++revision.current;
    setBusy(true);
    try {
      const body = await api<Replay>(
        endpoint + "/control",
        json("POST", { action, speed, generation: replay.generation }),
      );
      if (alive.current) {
        setReplay(body);
        setError("");
      }
    } catch (e) {
      if (alive.current) setError(message(e));
    } finally {
      pending.current = false;
      if (alive.current) setBusy(false);
    }
  }
  if (onOpen)
    return <AlertSummary replay={replay} error={error} open={onOpen} />;
  const current = replay?.records.at(-1);
  const errorNode = error && (
    <p role="alert" className="error">
      {error}{" "}
      <button type="button" className="link" onClick={() => void refresh()}>
        重试读取
      </button>
    </p>
  );
  if (!replay)
    return (
      <section aria-label="公开传感器记录回放" className="paper clouclip">
        {errorNode || <p role="status">正在读取公开传感器记录…</p>}
      </section>
    );
  const { segment, source } = replay;
  return (
    <section className="paper clouclip" aria-label="公开传感器记录回放">
      <header className="clouclip-head">
        <div>
          <p>公开传感器记录回放</p>
          <h3>{segment.title}</h3>
        </div>
        <span className="clouclip-status">{statuses[replay.status]}</span>
      </header>
      <p className="clouclip-source-note">
        本账号配对的是一位成年研究参与者的 Clouclip
        片段。学习档案与传感器记录来自不同来源。
      </p>
      <div className="clouclip-controls">
        <button
          type="button"
          disabled={busy || replay.status === "finished"}
          onClick={() =>
            void control(replay.status === "playing" ? "pause" : "play")
          }
        >
          {replay.status === "playing"
            ? "暂停"
            : replay.status === "paused"
              ? "继续播放"
              : "播放"}
        </button>
        <button
          type="button"
          className="outline"
          disabled={busy}
          onClick={() => void control("replay")}
        >
          重播
        </button>
        <label>
          回放速度{" "}
          <select
            value={replay.speed}
            disabled={busy}
            onChange={(e) => void control("speed", Number(e.target.value))}
          >
            <option value={1}>原速 1×</option>
            <option value={4}>4×</option>
            <option value={10}>10×</option>
          </select>
        </label>
      </div>
      {errorNode}
      <div className="clouclip-timeline">
        <span>{segment.starts_at.slice(0, 10)} · 美国中部时间</span>
        <strong>
          {current ? timePart(current.Date) : timePart(segment.starts_at)}
        </strong>
        <progress
          max={segment.duration_seconds}
          value={replay.position_seconds}
          aria-label="原始时间回放进度"
        />
        <span>
          {timePart(segment.starts_at)} – {timePart(segment.ends_at)}
        </span>
        <span>
          {replay.records.length} / {segment.total_samples} 点
        </span>
      </div>
      <div className="clouclip-metrics">
        <SensorTrend replay={replay} metric="Dis" />
        <SensorTrend replay={replay} metric="Lux" />
      </div>
      <div className="clouclip-events">
        <h4>提醒记录</h4>
        {replay.events.length > 0 ? (
          <ul>
            {replay.events.map((e) => (
              <li key={e.metric + "-" + e.start_line}>
                <strong>
                  {e.metric === "Dis" ? distanceNotice : brightnessNotice}
                </strong>
                <span>
                  {timePart(e.started_at)} 触发 ·{" "}
                  {e.ended_at ? timePart(e.ended_at) + " 解除" : "等待恢复"}
                </span>
                <small>
                  Clouclip {e.metric} · 原文件第 {e.start_line} 行
                  {e.end_line && " 至 " + e.end_line + " 行"}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <p>
            {replay.records.length
              ? "当前已播放的样本未触发提醒。"
              : "播放后可查看提醒起止时间。"}
          </p>
        )}
      </div>
      <details>
        <summary>演示阈值与来源</summary>
        <p>
          两项指标独立判断。低于触发线连续 3 个有效点时提醒，达到恢复线连续 2
          个有效点时解除。每 5 秒采样一次，3 个连续点的首末相隔 10
          秒。缺测、休眠和时间间断会清零相应计数。
        </p>
        <p>
          原文件第 {segment.first_line}–{segment.last_line}{" "}
          行，时间戳按设备原样保留。片段名称描述本次演示场景。
        </p>
        <a
          href={
            source.file_url +
            "#L" +
            segment.first_line +
            "-L" +
            segment.last_line
          }
          target="_blank"
          rel="noreferrer"
        >
          原始数据 ↗
        </a>
        {" · "}
        <a href={source.supplement} target="_blank" rel="noreferrer">
          传感器与采样说明 ↗
        </a>
      </details>
      <details>
        <summary>逐点原始记录（{replay.records.length}）</summary>
        <table>
          <caption>Clouclip 原始设备时间与测量值</caption>
          <thead>
            <tr>
              <th>CSV 行</th>
              <th>时间</th>
              <th>Dis (cm)</th>
              <th>Lux (lx)</th>
            </tr>
          </thead>
          <tbody>
            {replay.records.map((s) => (
              <tr key={s.line}>
                <td>{s.line}</td>
                <td>{timePart(s.Date)}</td>
                <td>{s.Dis ?? "缺测"}</td>
                <td>{s.Lux ?? "缺测"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}

export default function Clouclip({
  sid,
  accountId,
  onOpen,
}: {
  sid: string;
  accountId: string;
  onOpen?: () => void;
}) {
  return <ReplayPanel key={accountId + "/" + sid} sid={sid} onOpen={onOpen} />;
}

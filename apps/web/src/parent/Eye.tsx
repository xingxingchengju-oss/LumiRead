import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api, type EyeAlert, type Sample } from "../api";
import {
  brightnessNotice,
  distanceNotice,
  distanceState,
} from "../eyeMessages";
import { dateTime, useResource } from "./data";
const Chart = lazy(() => import("./Chart").then((m) => ({ default: m.Chart })));
const metrics: Record<string, string> = {
  distance_cm: "阅读距离",
  distance: "阅读距离",
  brightness: "相对明暗",
  brightness_level: "相对明暗",
  brightness_relative: "相对明暗",
  reading_seconds: "连续读写",
  reading_minutes: "连续读写",
  duration: "连续读写",
  head_tilt_deg: "头部倾斜",
  head_tilt: "头部倾斜",
  tilt_deg: "头部倾斜",
};
const words: Record<string, string> = {
  estimated: "估算",
  estimate: "估算",
  measured: "实测",
  observed: "实测",
  missing: "缺测",
  simulated: "模拟",
  simulation: "模拟",
  real: "实时采集",
  live: "实时采集",
  camera: "摄像头",
  rear: "后摄",
  front: "前摄",
  rear_camera: "后摄",
  front_camera: "前摄",
  good: "良好",
  ok: "良好",
  low: "低",
  unknown: "未知",
  poor: "低",
  phone: "手机",
  marker: "纸面标记",
  elapsed: "经过时间",
  cm: "cm",
  s: "秒",
  min: "分钟",
  deg: "°",
  level: "级",
  relative: "相对值",
  accelerated: "300 倍模拟",
  "qr-pinhole-v1": "纸面标记 · 镜头到纸面代理值",
  "qr-size-proxy-v2": "后摄固定尺寸纸面标记",
  "eye-line-roll-v1": "前摄眼线倾角",
  "center-luma-rec709-v1": "画面中心相对明暗（0–255）",
  "foreground-reading-clock-v1": "前台读写计时",
  "demo-clock-300x-v1": "演示计时",
  returned_to_range: "已恢复",
  signal_lost: "信号中断",
  silent: "进入静音",
};
const label = (s: string) => words[s] || s;
const metricName = (m: string) => metrics[m] || m;
function stated(sample: Sample) {
  if (sample.metric === "distance_cm") return distanceState(sample.value);
  return sample.value === null
    ? "缺测"
    : `${Number(sample.value.toFixed(2))} ${label(sample.unit)}`.trim();
}
function advice(metric: string) {
  if (metric === "distance_cm") return distanceNotice;
  if (metric === "brightness") return brightnessNotice;
  return metricName(metric) + "提醒";
}
function source(sample: Sample) {
  return [sample.value_kind, sample.input_mode, sample.method]
    .filter(Boolean)
    .map(label)
    .join(" · ");
}

function VisibleAlert({ alert, sid }: { alert: EyeAlert; sid: string }) {
  const node = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!node.current) return;
    let visible = false,
      sent = false,
      active = true,
      timer = 0;
    async function mark() {
      if (!active || !visible || sent || document.hidden) return;
      sent = true;
      try {
        await api(`/sessions/${sid}/alerts/${alert.id}/seen`, {
          method: "POST",
        });
      } catch {
        sent = false;
        if (active) timer = window.setTimeout(mark, 2000);
      }
    }
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      void mark();
    });
    observer.observe(node.current);
    document.addEventListener("visibilitychange", mark);
    return () => {
      active = false;
      clearTimeout(timer);
      observer.disconnect();
      document.removeEventListener("visibilitychange", mark);
    };
  }, [sid, alert.id]);
  return (
    <article ref={node} className="alert-card">
      <span className="alert-mark" aria-hidden="true">
        !
      </span>
      <div>
        <strong>{advice(alert.metric)}</strong>
        <p>
          {stated(alert)}　{source(alert)}
        </p>
        <small>开始于 {dateTime(alert.started_at, true)}</small>
      </div>
    </article>
  );
}

export function AlertSummary({
  alerts,
  sid,
}: {
  alerts: EyeAlert[] | undefined;
  sid: string;
}) {
  const open = alerts?.filter((a) => !a.ended_at);
  return (
    <section
      className="current-alerts"
      aria-label="当前护眼提醒"
      aria-live="polite"
    >
      {open?.length ? (
        open.map((a) => <VisibleAlert key={a.id} alert={a} sid={sid} />)
      ) : (
        <div className="quiet-alert">
          <span className="round-symbol" aria-hidden="true">
            {alerts ? "✓" : "…"}
          </span>
          <strong>{alerts ? "当前没有护眼提醒" : "正在读取护眼提醒"}</strong>
          {alerts && (
            <span>
              {alerts.length
                ? `最近记录于 ${dateTime(alerts[0].ended_at || alerts[0].started_at)}`
                : "等待本场设备观测"}
            </span>
          )}
        </div>
      )}
    </section>
  );
}

export function Eye({
  sid,
  bus,
  alerts,
}: {
  sid: string;
  bus: EventTarget;
  alerts: EyeAlert[] | undefined;
}) {
  const resource = useResource<{ samples: Sample[] }>(
    `/sessions/${sid}/telemetry?limit=240`,
    bus,
    "telemetry.updated",
  );
  const samples = resource.data?.samples;
  const [metric, setMetric] = useState(""),
    [mode, setMode] = useState("");
  const keys = useMemo(
    () => Array.from(new Set(samples?.map((s) => s.metric))),
    [samples],
  );
  const active = keys.some((k) => k === metric)
    ? metric
    : keys.find((k) => k.includes("distance")) || keys[0] || "";
  const streams = useMemo(
    () =>
      Array.from(
        new Set(
          samples?.filter((s) => s.metric === active).map((s) => s.input_mode),
        ),
      ),
    [samples, active],
  );
  const activeMode = streams.some((k) => k === mode) ? mode : streams[0];
  const data = useMemo(
    () =>
      [...(samples || [])]
        .filter((s) => s.metric === active && s.input_mode === activeMode)
        .sort((a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at)),
    [samples, active, activeMode],
  );
  const latest = data.at(-1);
  const options = useCallback(
    () => ({
      animation: false,
      grid: { left: 52, right: 20, top: 16, bottom: 30 },
      tooltip: { trigger: "axis", renderMode: "richText" },
      xAxis: {
        type: "time",
        axisLabel: {
          color: "#46574b",
          hideOverlap: true,
          formatter: (t: number) =>
            new Date(t).toLocaleTimeString("zh-CN", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            }),
        },
        axisLine: { lineStyle: { color: "#bfc9bd" } },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitNumber: 4,
        axisLabel: { color: "#46574b" },
        splitLine: { lineStyle: { color: "#dce1d4", type: "dashed" } },
      },
      series: [
        {
          name: metricName(active),
          type: "line",
          connectNulls: false,
          symbolSize: 6,
          lineStyle: { width: 3, color: "#2e6850" },
          itemStyle: { color: "#2e6850" },
          areaStyle: { color: "#d7e5d4", opacity: 0.55 },
          data: data.map((s) => [Date.parse(s.observed_at), s.value]),
        },
      ],
    }),
    [active, data],
  );
  return (
    <div className="stack">
      <section className="paper telemetry">
        <div className="entry-heading">
          <h2>护眼观测</h2>
          <span className="muted">本场记录</span>
        </div>
        {resource.error && (
          <p className="error" role="alert">
            {resource.error}{" "}
            <button className="link" onClick={resource.reload}>
              重新读取
            </button>
          </p>
        )}
        {keys.length > 0 && (
          <div className="metric-controls">
            <label>
              观测指标
              <select
                value={active}
                onChange={(e) => {
                  setMetric(e.target.value);
                  setMode("");
                }}
              >
                {keys.map((k) => (
                  <option key={k} value={k}>
                    {metricName(k)}
                  </option>
                ))}
              </select>
            </label>
            {streams.length > 1 && (
              <label>
                采集模式
                <select
                  value={activeMode}
                  onChange={(e) => setMode(e.target.value)}
                >
                  {streams.map((m) => (
                    <option key={m} value={m}>
                      {label(m)}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
        )}
        {latest ? (
          <>
            <div className="reading">
              <b>{stated(latest)}</b>
              <span>
                {metricName(active)}
                <br />
                {source(latest)}
              </span>
            </div>
            {active === "distance_cm" ? null : data.some(
                (s) => s.value !== null,
              ) ? (
              <Suspense fallback={<p>正在绘制曲线…</p>}>
                <Chart
                  options={options}
                  label={metricName(active) + "随时间变化，完整数值见下方记录"}
                />
              </Suspense>
            ) : (
              <p className="empty-line">这段时间的观测均为缺测。</p>
            )}
            <details className="setup">
              <summary>查看观测记录与来源（{data.length}）</summary>
              <div className="scroll-table">
                <table>
                  <thead>
                    <tr>
                      <th>时间</th>
                      <th>值</th>
                      <th>来源</th>
                      <th>质量</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data
                      .slice()
                      .reverse()
                      .map((s, i) => (
                        <tr key={s.observed_at + i}>
                          <td>{dateTime(s.observed_at, true)}</td>
                          <td>{stated(s)}</td>
                          <td>{source(s)}</td>
                          <td>{label(s.quality)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        ) : (
          <div className="empty-line">
            <strong>{samples ? "尚无观测样本" : "正在读取观测样本…"}</strong>
            {samples && <p>配对眼镜并开启取景后，这里将显示本场的读写数据。</p>}
          </div>
        )}
      </section>
      <section className="paper">
        <div className="entry-heading">
          <h2>提醒记录</h2>
          <span>{alerts?.length ?? "—"} 次</span>
        </div>
        {alerts?.length ? (
          <ul className="records">
            {alerts.map((a) => (
              <li key={a.id}>
                <strong>
                  {advice(a.metric)}{" "}
                  <small>
                    {a.ended_at ? label(a.reason || "已结束") : "进行中"}
                  </small>
                </strong>
                <p>
                  {stated(a)} · {source(a)}
                </p>
                <small>
                  {dateTime(a.started_at, true)}{" "}
                  {a.ended_at ? " 至 " + dateTime(a.ended_at, true) : " 起"}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">
            {alerts ? "本场尚未产生提醒。" : "正在读取提醒记录…"}
          </p>
        )}
      </section>
    </div>
  );
}

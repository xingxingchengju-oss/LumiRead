import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react";
import jsQR from "jsqr";
import {
  distanceState,
  distanceNotice,
  brightnessNotice,
} from "../eyeMessages";
import { api, json, message, type EventRow } from "../api";
import {
  MARKER,
  centerLuma,
  clockText,
  distanceCm,
  qrScale,
  sample,
  type Sample,
  type Metric,
} from "./sensors";
import "./glass.css";

interface Props {
  video: RefObject<HTMLVideoElement | null>;
  active: boolean;
  silent: boolean;
  sid: string;
}

type Alert = {
  id: string;
  metric: Metric;
  value: number;
  unit: string;
  input_mode: string;
  ended_at: string | null;
  reason?: string;
};
const alertNames = {
  distance_cm: "纸面距离",
  brightness: "桌面亮度",
  reading_seconds: "读写时长",
};
const alertLabels = {
  distance_cm: distanceNotice,
  brightness: brightnessNotice,
  reading_seconds: "连续读写达 45 分钟",
};
function describeAlert(a: Alert) {
  return a.metric === "reading_seconds"
    ? alertLabels[a.metric] +
        " · " +
        clockText(a.value) +
        (a.input_mode === "accelerated" ? " · 模拟" : "")
    : alertLabels[a.metric];
}
type Reading = {
  brightness: number | null;
  distance: number | null;
};
const empty: Reading = { brightness: null, distance: null };
export function SensorPanel({ video, active, silent, sid }: Props) {
  const [reading, setReading] = useState<Reading>(empty);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [recovery, setRecovery] = useState("");
  const [error, setError] = useState("");
  const [time, setTime] = useState(0);
  const [demo, setDemo] = useState(false);
  const [demoSeconds, setDemoSeconds] = useState(0);
  const activeAlerts = useRef<Alert[]>([]);
  const muted = useRef(silent);
  muted.current = silent;
  const [resting, setResting] = useState(false);
  const timer = useRef<{ start: number | null; elapsed: number }>({
    start: null,
    elapsed: 0,
  });
  const readingEnabled = active && !resting && !silent;
  const session = useRef(sid);
  session.current = sid;
  const pending = useRef(false);
  const latest = useRef(new Map<string, Sample>());
  const showAlerts = useCallback((reported: Alert[]) => {
    const current = reported.filter((a) => a.metric in alertLabels);
    const removed = activeAlerts.current.filter(
      (old) => !current.some((a) => a.id === old.id),
    );
    if (removed.length)
      setRecovery(
        (previous) =>
          previous ||
          "提醒已结束 · " + removed.map((a) => alertNames[a.metric]).join("、"),
      );
    if (current.length && !removed.length) setRecovery("");
    activeAlerts.current = current;
    setAlerts(current);
  }, []);
  useEffect(() => {
    let alive = true,
      seq = 0;
    async function sync() {
      const version = ++seq;
      try {
        const response = await api<{ alerts: Alert[] }>(
          "/sessions/" + sid + "/alerts",
        );
        if (alive && version === seq)
          showAlerts(response.alerts.filter((a) => !a.ended_at));
      } catch {
        /* The next observation batch also returns current alerts. */
      }
    }
    void sync();
    const receive = (e: Event) => {
      const event = (e as CustomEvent<EventRow>).detail;
      if (event?.session_id !== sid) return;
      if (event.type === "alert.cleared") {
        const metric = event.payload.metric as Alert["metric"];
        const reason = String(event.payload.reason);
        const text =
          reason === "returned_to_range"
            ? "指标已恢复"
            : reason === "silent"
              ? "静音结束提醒"
              : "采样中断";
        if (metric in alertLabels)
          setRecovery(text + " · " + alertNames[metric]);
      }
      if (event.type === "alert.raised" || event.type === "alert.cleared")
        void sync();
    };
    window.addEventListener("lumiread:event", receive);
    return () => {
      alive = false;
      window.removeEventListener("lumiread:event", receive);
    };
  }, [sid, showAlerts]);
  const publish = useCallback(
    (samples: Sample[]) => {
      if (muted.current) {
        latest.current.clear();
        return;
      }
      // A slow network keeps only the most recent unsent observation for each sensor and clock.
      for (const value of samples)
        latest.current.set(value.metric + "/" + value.input_mode, value);
      if (pending.current) return;
      pending.current = true;
      void (async () => {
        try {
          while (
            latest.current.size &&
            session.current === sid &&
            !muted.current
          ) {
            const batch = [...latest.current.values()];
            latest.current.clear();
            try {
              const result = await api<{
                accepted: number;
                active_alerts: Alert[];
              }>("/sessions/" + sid + "/telemetry/batch", {
                ...json("POST", { samples: batch }),
                signal: AbortSignal.timeout(7500),
              });
              if (!muted.current && session.current === sid) {
                showAlerts(result.active_alerts);
                setError("");
              }
            } catch (e) {
              if (!muted.current && session.current === sid)
                setError("观测同步失败 · " + message(e));
            }
          }
        } finally {
          pending.current = false;
        }
      })();
    },
    [sid, showAlerts],
  );
  useEffect(() => {
    if (!readingEnabled) return;
    timer.current.start = performance.now();
    setTime(Math.floor(timer.current.elapsed / 1000));
    const t = window.setInterval(() => {
      if (timer.current.start !== null)
        setTime(
          Math.floor(
            (timer.current.elapsed + performance.now() - timer.current.start) /
              1000,
          ),
        );
    }, 250);
    return () => {
      clearInterval(t);
      if (timer.current.start !== null)
        timer.current.elapsed += performance.now() - timer.current.start;
      timer.current.start = null;
      setTime(Math.floor(timer.current.elapsed / 1000));
      publish([sample("reading_seconds", null)]);
    };
  }, [readingEnabled, publish]);
  useEffect(() => {
    if (!active || silent) {
      setDemo(false);
      setResting(false);
      if (silent) {
        latest.current.clear();
        showAlerts([]);
        setError("");
      }
    }
  }, [active, silent, showAlerts]);
  useEffect(() => {
    if (!demo || !active || silent) return;
    const start = performance.now();
    let previous = -1;
    function tick() {
      const seconds = Math.min(
        2700,
        Math.floor((performance.now() - start) * 0.3),
      );
      if (previous === seconds) return;
      previous = seconds;
      setDemoSeconds(seconds);
      publish([sample("reading_seconds", seconds, true)]);
    }
    tick();
    const t = window.setInterval(tick, 1000);
    return () => {
      clearInterval(t);
      publish([sample("reading_seconds", null, true)]);
    };
  }, [demo, active, silent, publish]);

  useEffect(() => {
    const v = video.current;
    if (!active || silent || !v) return;
    let disposed = false,
      handle = 0;
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d", { willReadFrequently: true });
    let lastFrame = -1,
      lastFresh = -Infinity,
      lastSend = -Infinity;
    let current: Reading = { ...empty };
    const track = (v.srcObject as MediaStream | null)?.getVideoTracks()[0];
    setReading(empty);
    function loop() {
      if (disposed || !v || !context || document.hidden) return;
      const now = performance.now();
      if (v.readyState >= 2 && v.videoWidth && v.currentTime !== lastFrame) {
        lastFrame = v.currentTime;
        lastFresh = now;
        const ratio = Math.min(640 / Math.max(v.videoWidth, v.videoHeight), 1);
        const w = Math.round(v.videoWidth * ratio),
          h = Math.round(v.videoHeight * ratio);
        if (canvas.width !== w || canvas.height !== h) {
          canvas.width = w;
          canvas.height = h;
        }
        context.drawImage(v, 0, 0, w, h);
        const pixels = context.getImageData(0, 0, w, h).data;
        current.brightness = centerLuma(pixels, w, h);
        const qr = jsQR(pixels, w, h, { inversionAttempts: "dontInvert" });
        const loc = qr?.location;
        const scale =
          qr?.data === MARKER && loc
            ? qrScale(
                [
                  loc.topLeftCorner,
                  loc.topRightCorner,
                  loc.bottomRightCorner,
                  loc.bottomLeftCorner,
                ],
                w,
                h,
              )
            : null;
        current.distance = distanceCm(scale, w, h, track?.getSettings());
      }
      if (now - lastFresh > 1000) {
        current = { ...empty };
      }
      if (now - lastSend >= 950) {
        lastSend = now;
        setReading({ ...current });
        const values = [
          sample("distance_cm", current.distance),
          sample("brightness", current.brightness),
        ];
        if (timer.current.start !== null)
          values.push(
            sample(
              "reading_seconds",
              Math.floor(
                Math.max(0, timer.current.elapsed + now - timer.current.start) /
                  1000,
              ),
            ),
          );
        publish(values);
      }
      handle = window.setTimeout(loop, 400);
    }
    loop();
    return () => {
      disposed = true;
      clearTimeout(handle);
      setReading(empty);
      publish([sample("distance_cm", null), sample("brightness", null)]);
    };
  }, [active, silent, video, publish]);
  const usable = active && !silent;
  return (
    <section className="glass-observations" aria-label="护眼观测">
      <h2>护眼观测</h2>
      {alerts.length > 0 && (
        <ul className="glass-alert" aria-live="polite">
          {alerts.map((a) => (
            <li key={a.id}>⚠ {describeAlert(a)}</li>
          ))}
        </ul>
      )}
      {recovery && (
        <p aria-live="polite" className="glass-note">
          {recovery}
        </p>
      )}
      {error && <p className="glass-alert">{error}</p>}
      <dl className="glass-grid">
        <div>
          <dt>纸面距离</dt>
          <dd>{distanceState(reading.distance)}</dd>
          <small>后摄标记估算</small>
        </div>
        <div>
          <dt>画面相对亮度</dt>
          <dd>
            {reading.brightness === null
              ? "缺测"
              : reading.brightness + " / 255"}
          </dd>
          <small>
            {reading.brightness === null
              ? "图像实测"
              : reading.brightness < 65
                ? "偏暗"
                : reading.brightness > 200
                  ? "较亮"
                  : "适中"}{" "}
            · 非照度计
          </small>
        </div>
        <div>
          <dt>本段读写时间</dt>
          <dd>{clockText(time)}</dd>
          <small>{readingEnabled ? "后摄前台取景计时" : "已暂停"}</small>
        </div>
      </dl>
      <details className="glass-marker-guide">
        <summary>放置纸面标记</summary>
        <p>
          按实际大小打印，把黑色标记平放在作业旁。保持后摄
          1×，让镜头正对纸面，标记完整入镜。
        </p>
        <a href="/vision/paper-marker.svg" target="_blank" rel="noreferrer">
          打开可打印标记 ↗
        </a>
      </details>
      {usable && (
        <button
          className="outline"
          onClick={() => {
            setResting(!resting);
            if (!resting) {
              timer.current = { start: null, elapsed: 0 };
              setTime(0);
            }
          }}
        >
          {resting ? "开始新一段读写" : "休息并结束本段"}
        </button>
      )}
      <div className="glass-demo">
        <button
          className="outline"
          disabled={!usable}
          onClick={() => {
            setDemoSeconds(0);
            setDemo(!demo);
          }}
        >
          {demo ? "结束模拟" : "模拟 45 分钟提醒"}
        </button>
        {demo && <span>模拟 · 300 倍速 · {clockText(demoSeconds)}</span>}
      </div>
    </section>
  );
}

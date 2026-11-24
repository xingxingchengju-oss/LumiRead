import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  json,
  message,
  localHost,
  type EyeAlert,
  type Job,
  type Snapshot,
  type Session,
} from "../api";
import { Archive } from "./Archive";
import { Devices } from "./Devices";
import { Eye, AlertSummary } from "./Eye";
import { Worksheet } from "./Worksheet";
import { useResource } from "./data";

const tabs = {
  eye: "护眼观察",
  homework: "今日作业",
  archive: "学习档案",
} as const;
type Tab = keyof typeof tabs;
export function Notebook({
  snap,
  bus,
  connection,
  onSilent,
}: {
  snap: Snapshot;
  bus: EventTarget;
  connection: string;
  onSilent: (v: boolean) => void;
}) {
  const sid = snap.session_id,
    learner = snap.learner_id,
    key = "lumiread-notebook-" + sid;
  const [tab, setTab] = useState<Tab>(() => {
    const previous = sessionStorage.getItem(key);
    return previous && previous in tabs ? (previous as Tab) : "eye";
  });
  const deliberate = useRef(false);
  const select = useCallback(
    (t: Tab) => {
      setTab(t);
      sessionStorage.setItem(key, t);
    },
    [key],
  );
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  async function newSession() {
    if (creating) return;
    setCreating(true);
    try {
      const next = await api<Session>("/sessions", json("POST", {}));
      location.assign(
        "/legacy-app?room=" + encodeURIComponent(next.session_id),
      );
    } catch (e) {
      setError(message(e));
      setCreating(false);
    }
  }
  const jobs = useResource<Job[]>(
    "/sessions/" + sid + "/homework",
    bus,
    "grading.queued grading.running grading.completed grading.failed capture.received question.reviewed",
  );
  const alerts = useResource<{ alerts: EyeAlert[] }>(
    "/sessions/" + sid + "/alerts",
    bus,
    "alert.raised alert.cleared",
  );
  useEffect(() => {
    const captured = () => {
      if (!deliberate.current) select("homework");
    };
    bus.addEventListener("capture.received", captured);
    return () => bus.removeEventListener("capture.received", captured);
  }, [bus, select]);
  const today = new Date().toLocaleDateString("zh-CN");
  const recent = (jobs.data || []).filter(
    (j) => new Date(j.created * 1000).toLocaleDateString("zh-CN") === today,
  );
  const older = (jobs.data || []).filter(
    (j) => new Date(j.created * 1000).toLocaleDateString("zh-CN") !== today,
  );
  const worksheet = (job: Job) => (
    <Worksheet
      key={job.id}
      job={job}
      learner={learner}
      onUpdate={jobs.reload}
      onError={setError}
    />
  );
  return (
    <main className="notebook">
      <header className="notebook-cover">
        <div>
          <p>
            {new Date().toLocaleDateString("zh-CN", {
              year: "numeric",
              month: "long",
              day: "numeric",
              weekday: "long",
            })}
          </p>
          <h1>学习观察手册</h1>
        </div>
        <span className="field-number">家庭学习助手</span>
      </header>
      <div className="notebook-tools">
        <nav aria-label="手册目录">
          {Object.entries(tabs).map(([id, title]) => (
            <button
              key={id}
              aria-current={tab === id ? "page" : undefined}
              onClick={() => {
                deliberate.current = true;
                select(id as Tab);
              }}
            >
              {title}
            </button>
          ))}
        </nav>
        <span className="connection">{connection}</span>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}{" "}
          <button className="link" onClick={() => setError("")}>
            关闭
          </button>
        </p>
      )}
      {alerts.error && (
        <p className="error" role="alert">
          {alerts.error}{" "}
          <button className="link" onClick={alerts.reload}>
            重新读取提醒
          </button>
        </p>
      )}
      <AlertSummary alerts={alerts.data?.alerts} sid={sid} />
      <div className="desk">
        <div className="work-column">
          {tab === "eye" && (
            <Eye sid={sid} alerts={alerts.data?.alerts} bus={bus} />
          )}
          {tab === "homework" && (
            <>
              <div className="section-title">
                <h2>今日批改</h2>
                <span>{jobs.data ? recent.length + " 份作业" : "读取中"}</span>
              </div>
              {jobs.error && (
                <p className="error" role="alert">
                  {jobs.error}{" "}
                  <button className="link" onClick={jobs.reload}>
                    重试读取作业
                  </button>
                </p>
              )}
              {recent.map(worksheet)}
              {jobs.data && !recent.length && (
                <div className="empty">
                  <span className="empty-book" aria-hidden="true">
                    ▤
                  </span>
                  <h3>等待第一张作业</h3>
                  <p>配对 iPhone 后拍下作业，原图和逐题批改会出现在这里。</p>
                </div>
              )}
              {older.length > 0 && (
                <details className="paper setup">
                  <summary>本场较早作业（{older.length}）</summary>
                  {older.map(worksheet)}
                </details>
              )}
            </>
          )}
          {tab === "archive" && <Archive bus={bus} learner={learner} />}
        </div>
        <Devices
          sid={sid}
          snap={snap}
          setError={setError}
          onSilent={onSilent}
        />
      </div>
      <footer className="notebook-footer">
        本场编号 <code>{sid}</code>
        <a href={"/showcase?legacy=1&room=" + encodeURIComponent(sid)}>
          同场产品展示 ↗
        </a>
      </footer>
      {localHost() && (
        <details className="new-session">
          <summary>开始新的学习场次</summary>
          <p>
            新场次沿用本学习者的错题和画像。拍摄设备需要扫描新场次的配对码。
          </p>
          <button className="outline" disabled={creating} onClick={newSession}>
            创建并进入新场次
          </button>
        </details>
      )}
    </main>
  );
}

import { useState, useRef, useEffect } from "react";
import { api, json, message, type Job } from "../api";
import { Question } from "./Fields";
const viewId = crypto.getRandomValues(new Uint32Array(4)).join("-");
const time = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
const states: Record<string, string> = {
  queued: "等待批改",
  running: "正在批改",
  completed: "批改完成",
  failed: "批改未完成",
};
export function Worksheet({
  job,
  learner,
  onUpdate,
  onError,
}: {
  job: Job;
  learner: string;
  onUpdate: () => void;
  onError: (s: string) => void;
}) {
  const [original, setOriginal] = useState(false),
    [busy, setBusy] = useState(false);
  const [imageState, setImageState] = useState<"loading" | "ready" | "failed">(
    "loading",
  );
  const [imageAttempt, setImageAttempt] = useState(0);
  const resultLabel = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (
      job.status !== "completed" ||
      imageState !== "ready" ||
      !resultLabel.current
    )
      return;
    let visible = false,
      sent = false;
    async function mark() {
      if (sent || !visible || document.visibilityState !== "visible") return;
      sent = true;
      try {
        await api(
          "/jobs/" + job.id + "/seen",
          json("POST", { view_id: viewId }),
        );
      } catch {
        sent = false;
      }
    }
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      void mark();
    });
    observer.observe(resultLabel.current);
    document.addEventListener("visibilitychange", mark);
    window.addEventListener("online", mark);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", mark);
      window.removeEventListener("online", mark);
    };
  }, [job.id, job.status, imageState]);
  return (
    <article className="entry">
      <div className="entry-heading">
        <div>
          <p className="eyebrow">
            {new Date(job.created * 1000).toLocaleDateString("zh-CN")} ·{" "}
            {time(job.created)}
          </p>
          <h3>纸面作业</h3>
        </div>
        <span className="status">{states[job.status]}</span>
      </div>
      <div className="worksheet-photo">
        <img
          key={imageAttempt}
          className={original ? "original expanded" : "original"}
          src={"/api/v1/captures/" + job.capture_id + "/photo"}
          alt="本次上传的作业原图"
          loading="lazy"
          hidden={imageState === "failed"}
          onLoad={() => setImageState("ready")}
          onError={() => setImageState("failed")}
        />
        {imageState === "failed" ? (
          <div role="status">
            <p>原图未能载入。</p>
            <button
              className="link"
              onClick={() => {
                setImageState("loading");
                setImageAttempt((n) => n + 1);
              }}
            >
              重新载入原图
            </button>
          </div>
        ) : (
          <button
            className="link"
            disabled={imageState !== "ready"}
            aria-expanded={original}
            onClick={() => setOriginal(!original)}
          >
            {original ? "缩小原图" : "放大原图"}
          </button>
        )}
      </div>
      {job.status === "failed" && (
        <div role="alert">
          <p>{job.error}</p>
          <button
            disabled={busy}
            className="outline"
            onClick={async () => {
              setBusy(true);
              try {
                await api("/jobs/" + job.id + "/retry", { method: "POST" });
              } catch (e) {
                onError(message(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            重试批改
          </button>
        </div>
      )}
      {job.result && (
        <>
          <p ref={resultLabel} className="muted">
            {job.provider} · {job.model}
            {job.latency != null ? " · " + job.latency.toFixed(1) + " 秒" : ""}
          </p>
          {!job.result.length && <p>未能辨认出题目，请对准作业重新拍照。</p>}
          {job.result.map((item, i) => (
            <Question
              key={item.id + "-" + item.revision}
              item={item}
              number={i + 1}
              learner={learner}
              onUpdate={onUpdate}
            />
          ))}
        </>
      )}
    </article>
  );
}

import { useEffect, useRef, useState } from "react";
import { api, message, type Job } from "../api";
import { Worksheet } from "./Worksheet";
import { useResource } from "./data";

type Selection = { file: File; key: string };

export default function Homework({
  sid,
  learner,
  bus,
}: {
  sid: string;
  learner: string;
  bus: EventTarget;
}) {
  const jobs = useResource<Job[]>(
    "/sessions/" + encodeURIComponent(sid) + "/homework",
    bus,
    "capture.received grading.queued grading.running grading.completed grading.failed question.reviewed",
  );
  const [selection, setSelection] = useState<Selection | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const lock = useRef<AbortController | null>(null);
  useEffect(() => () => lock.current?.abort(), []);
  async function send() {
    if (!selection || lock.current) return;
    const controller = new AbortController();
    lock.current = controller;
    setBusy(true);
    setError("");
    setNotice("");
    const body = new FormData();
    body.set("photo", selection.file);
    body.set("source", "upload");
    body.set("idem", selection.key);
    try {
      await api("/sessions/" + encodeURIComponent(sid) + "/captures", {
        method: "POST",
        body,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      jobs.reload();
      setSelection(null);
      if (input.current) input.current.value = "";
      setNotice("图片已上传。可在下方查看批改进度。");
    } catch (err) {
      if (!controller.signal.aborted) setError(message(err));
    } finally {
      lock.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  return (
    <div className="homework-view">
      <section className="paper intake">
        <h2>上传作业</h2>
        <p>选择清晰的作业照片或截图，查看逐题批改和小鹿讲解。</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <label>
            作业图片
            <input
              ref={input}
              type="file"
              accept="image/*,.heic,.heif"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0];
                setError("");
                setNotice("");
                setSelection(null);
                if (!file) return;
                if (file.size > 16 * 1024 * 1024) {
                  setError("图片超过 16 MB，请选择较小的文件。");
                  return;
                }
                setSelection({ file, key: crypto.randomUUID() });
              }}
            />
          </label>
          <button type="submit" disabled={!selection || busy}>
            {busy ? "正在上传…" : "上传并批改"}
          </button>
        </form>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="inline-note">
            {notice}
          </p>
        )}
      </section>
      <section aria-labelledby="work-title" className="job-list">
        <div className="section-title">
          <h2 id="work-title">本账号作业</h2>
          {jobs.data && <span>{jobs.data.length} 份</span>}
        </div>
        {jobs.error && (
          <p role="alert" className="error">
            {jobs.error}{" "}
            <button className="link" onClick={jobs.reload}>
              重新读取作业
            </button>
          </p>
        )}
        {!jobs.data && !jobs.error && <p role="status">正在读取作业…</p>}
        {jobs.data?.length === 0 && (
          <p className="empty-line">尚未上传作业。</p>
        )}
        {jobs.data?.map((job) => (
          <Worksheet
            key={job.id}
            job={job}
            learner={learner}
            onUpdate={jobs.reload}
            onError={setError}
          />
        ))}
      </section>
    </div>
  );
}

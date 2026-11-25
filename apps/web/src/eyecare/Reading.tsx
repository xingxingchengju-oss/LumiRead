import { useEffect, useRef, useState } from "react";
import {
  Controls,
  duration,
  Loading,
  media,
  usePlayback,
  usePublic,
} from "./shared";

import type { components } from "../../../../packages/contracts/types";
type Clip = components["schemas"]["ScoredClip"];
type Research = components["schemas"]["Research"];
const names: Record<string, string> = {
  alternating: "交替阅读",
  Print: "纸质",
  Digital: "电子",
  Object: "物体文字",
  everyday: "日常活动",
  hard_negative: "有文字但未读",
};
function Track({
  title,
  runs,
  start,
  end,
  position,
  annotated = false,
}: {
  title: string;
  runs: number[][];
  start: number;
  end: number;
  position: number;
  annotated?: boolean;
}) {
  const pct = (s: number) => (100 * (s - start)) / (end - start) + "%";
  return (
    <div className="ec-track">
      <strong>{title}</strong>
      <div
        className={"ec-rail" + (annotated ? " ec-annotated" : "")}
        aria-hidden="true"
      >
        {runs.map(([s, e, c]) => (
          <i
            key={s}
            data-class={c}
            style={{
              left: pct(s),
              width: (100 * (e - s)) / (end - start) + "%",
            }}
          />
        ))}
        <b style={{ left: pct(position) }} />
      </div>
    </div>
  );
}
function ClipView({ clip, showVideo }: { clip: Clip; showVideo: boolean }) {
  const [start, end] = clip.evaluation;
  const player = usePlayback(start, end);
  const video = useRef<HTMLVideoElement>(null);
  const [videoError, errorVideo] = useState(false);
  const active = clip.intervals.find(
    ([a, b]) => a <= player.position && player.position < b,
  );
  const truth = clip.reference_intervals.some(
    ([a, b]) => a <= player.position && player.position < b,
  );
  const referenceName =
    clip.reference_medium > 0 ? media[clip.reference_medium] : "阅读";
  const prediction = active
    ? active[2]
      ? active[3]
        ? media[active[3]] + "阅读"
        : "阅读 · 媒介待定"
      : "未阅读"
    : "无有效预测";
  const total = clip.intervals.reduce(
    (sum, [a, b, read]) =>
      sum + read * Math.max(0, Math.min(b, player.position) - a),
    0,
  );
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const v = video.current;
    if (!v || !ready || videoError) return;
    v.playbackRate = player.speed;
    if (Math.abs(v.currentTime - player.position) > 0.55 || !player.playing)
      v.currentTime = player.position;
    if (player.playing && v.paused) void v.play().catch(() => {});
    else if (!player.playing && !v.paused) v.pause();
  }, [ready, videoError, player.speed, player.playing, player.position]);
  return (
    <>
      <div className="ec-read-grid">
        <div className="ec-media-area">
          {showVideo && !videoError ? (
            <video
              ref={video}
              muted
              playsInline
              preload="metadata"
              aria-label="Meta 眼镜第一视角研究录像"
              onLoadedMetadata={() => setReady(true)}
              onError={() => errorVideo(true)}
              src={"/api/v1/eye-care/preview/" + clip.id}
            />
          ) : (
            <div className="ec-clip-still">
              <img alt="" src="/products/frame-open.webp" />
              <p>
                {showVideo
                  ? "本机尚未下载授权录像，可使用下方时间轴。"
                  : "此片段提供逐秒识别时间轴。"}
              </p>
            </div>
          )}
          <a
            href="https://explorer.projectaria.com/ritw"
            target="_blank"
            rel="noreferrer"
          >
            在 Meta 按编号查找录像 ↗
          </a>
        </div>
        <div className="ec-readout">
          <small>录像原始时间</small>
          <strong className="ec-clock">{duration(player.position)}</strong>
          <dl>
            <dt>官方标注</dt>
            <dd>
              {player.position >= end
                ? "片段结束"
                : truth
                  ? referenceName + " · 阅读"
                  : "未阅读"}
            </dd>
            <dt>模型预测</dt>
            <dd>{prediction}</dd>
            <dt>已识别阅读时长</dt>
            <dd>{duration(total)}</dd>
          </dl>
        </div>
      </div>
      <Track
        title="官方阅读区间"
        annotated
        runs={clip.reference_intervals.map(([a, b]) => [a, b, 1])}
        start={start}
        end={end}
        position={player.position}
      />
      <Track
        title="模型阅读区间"
        runs={clip.intervals.map(([a, b, r]) => [a, b, r ? 2 : 0])}
        start={start}
        end={end}
        position={player.position}
      />
      <Controls player={player} start={start} end={end} />
      <p className="ec-note">
        编号 {clip.id} · 有效覆盖 {duration(clip.covered_seconds)} ·
        整段识别阅读 {duration(clip.clock.active_seconds)}
        。时间轴上的斜纹表示缺少预测，浅灰表示未阅读。此段未达到休息提醒时长。
      </p>
    </>
  );
}
export default function Reading() {
  const r = usePublic<Research>("/eye-care/research");
  const [choice, choose] = useState("");
  if (!r.data) return <Loading {...r} />;
  const { clips, metrics, showcase } = r.data;
  const clip = clips.find((c) => c.id === (choice || showcase))!;
  return (
    <>
      <section className="ec-card">
        <header className="ec-head">
          <div>
            <h2>阅读识别回放</h2>
            <p>同一段真实录像中的官方标注与模型预测。</p>
          </div>
          <label>
            测试片段{" "}
            <select value={clip.id} onChange={(e) => choose(e.target.value)}>
              {[...clips]
                .sort(
                  (a, b) =>
                    Number(b.id === showcase) - Number(a.id === showcase),
                )
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {names[c.group]} · {c.id.slice(-6)}
                  </option>
                ))}
            </select>
          </label>
        </header>
        <ClipView key={clip.id} clip={clip} showVideo={clip.id === showcase} />
      </section>
      <section className="ec-card">
        <h2>模型在测试集上的表现</h2>
        <p>
          {metrics.splits.train.recordings} 段训练、
          {metrics.splits.val.recordings} 段验证、
          {metrics.splits.test.recordings}{" "}
          段测试。两个方法均读取眼动与头部运动。
        </p>
        <div className="ec-table">
          <table>
            <caption>留出录像 · 两种识别方法</caption>
            <thead>
              <tr>
                {[
                  "模型",
                  "阅读 F1",
                  "时长平均误差",
                  "有字未读误报率",
                  "未读召回",
                  "纸质召回",
                  "电子召回",
                  "物体文字召回",
                ].map((s) => (
                  <th key={s}>{s}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(["official", "logistic"] as const).map((key) => {
                const s = metrics[key];
                return (
                  <tr key={key}>
                    <th>
                      {key === "official" ? "Meta 官方模型" : "逻辑回归基线"}
                    </th>
                    <td>{s.read_f1.toFixed(3)}</td>
                    <td>{s.duration_mae_seconds.toFixed(1)} 秒</td>
                    <td>{(100 * s.hard_false_positive_rate).toFixed(1)}%</td>
                    {["No read", "Print", "Digital", "Object"].map((c) => (
                      <td key={c}>{(100 * s.medium_recall[c]).toFixed(1)}%</td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="ec-note">
          本次成人测试中，模型对纸质、电子和物体文字的区分仍有较多漏判。媒介占比用于观察模型表现；距离提醒使用手动选择的场景。
          <a href="https://github.com/facebookresearch/reading_in_the_wild">
            Meta 数据与模型许可 ↗
          </a>
        </p>
      </section>
    </>
  );
}

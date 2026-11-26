import { useCallback, useEffect, useRef, useState } from "react";
import type { components } from "../../../../packages/contracts/types";
import ScoreGuide from "./ScoreGuide";
import { duration, Loading, usePublic } from "./shared";

type Monitor = components["schemas"]["Monitor"];
type Clip = components["schemas"]["MonitorClip"];
type Patch = Clip["patches"][number];
type Policy = Monitor["score_policy"];
const activities = {
  reading: "阅读",
  video: "看视频",
  rest: "休息",
  unknown: "待定",
};
const media = {
  phone: "手机",
  computer: "电脑",
  tablet: "平板",
  screen: "屏幕类型待定",
  paper: "纸质",
  other_text: "物体文字",
  unknown: "媒介待定",
  none: "—",
};
const reasons: Record<string, string> = {
  first: "首个有效片段",
  resume: "恢复有效判断",
  enter_reading: "进入阅读",
  switch: "活动切换",
  tie: "最高票打平",
  close_vote: "两类相差一票",
  gap: "存在缺失秒",
  periodic: "稳定期间定期复核",
  unresolved: "上一次证据不足",
};
function label(p: Pick<Patch, "activity" | "medium">) {
  return p.activity === "reading" || p.activity === "video"
    ? activities[p.activity] + " · " + media[p.medium]
    : activities[p.activity];
}
function scoring(p: Patch, policy: Policy, scoreAt: (t: number) => number) {
  if (p.activity === "rest") {
    if (scoreAt(p.start) === 0) return "本段从零分开始，继续休息时保持零分。";
    let decreasing = 0;
    for (let t = p.start; t < p.end; t++) {
      if (scoreAt(t + 1) < scoreAt(t)) decreasing++;
    }
    if (decreasing === 0)
      return `这段休息仍在前 ${policy.rest_grace_seconds} 秒的缓冲内，积分保持。`;
    return `休息时间跨片段累计。本段有 ${decreasing} 秒已过 ${policy.rest_grace_seconds} 秒缓冲，每秒减 ${policy.rest_points_per_second} 分，最低为零。`;
  }
  if (p.activity === "unknown") return "活动待定，这些秒数冻结积分。";
  const category = p.activity === "video" ? "video" : p.medium;
  const tier = policy.tiers.find((t) =>
    t.categories.some((c) => c === category),
  );
  if (!tier) return "已确认阅读，时长照计。媒介待定，积分冻结。";
  if (
    scoreAt(p.start) === policy.max_points &&
    scoreAt(p.end) === policy.max_points
  )
    return "积分已达上限，本段保持满分。";
  return `每 ${policy.settlement_seconds} 个有效秒加 ${tier.points_per_settlement} 分，余秒带入后续片段。`;
}

function Replay({
  clip,
  ticks,
  policy,
}: {
  clip: Clip;
  ticks: number;
  policy: Policy;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const rail = useRef<HTMLDivElement>(null);
  const scoreButton = useRef<HTMLButtonElement>(null);
  const resumeAfterGuide = useRef(false);
  const cursor = useRef(clip.start);
  const announced = useRef(new Set<number>());
  const [position, setPosition] = useState(clip.start);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState("");
  const [guideOpen, setGuideOpen] = useState(false);
  const index = Math.min(
    clip.end - clip.start,
    Math.max(0, Math.floor(position) - clip.start),
  );
  const [read, watched, score] = clip.points[index];
  const patch =
    clip.patches.find((p) => position < p.end) ??
    clip.patches[clip.patches.length - 1];
  const missingNow =
    position < clip.end && patch.missing.includes(Math.floor(position));
  const evidence =
    patch.review ??
    clip.patches.find((p) => p.start === patch.evidence_start)?.review;
  const scoreAt = (t: number) => clip.points[t - clip.start][2] / ticks;
  const startScore = scoreAt(patch.start);
  const endScore = scoreAt(patch.end);
  const reason =
    scoring(patch, policy, scoreAt) +
    (patch.missing.length
      ? `本段缺失的 ${patch.missing.length} 秒冻结积分，并中断连续休息。`
      : "");
  const change = (p: Patch) => {
    const delta =
      (clip.points[p.end - clip.start][2] -
        clip.points[p.start - clip.start][2]) /
      ticks;
    return (delta > 0 ? "+" : "") + delta.toFixed(2);
  };

  function seek(t: number) {
    const next = Math.min(clip.end, Math.max(clip.start, t));
    cursor.current = next;
    setPosition(next);
    setNotice("");
    const v = video.current;
    if (v && v.readyState >= 1) {
      v.currentTime = next;
      if (next === clip.end) v.pause();
    }
  }
  const syncPlayback = useCallback(
    (v: HTMLVideoElement) => {
      if (v.seeking) return;
      const at = Math.max(clip.start, Math.min(clip.end, v.currentTime));
      for (const t of clip.reminders) {
        if (cursor.current < t && t <= at && !announced.current.has(t)) {
          announced.current.add(t);
          setNotice(
            `${duration(t)}　提醒积分已达 ${policy.max_points}，休息一下。`,
          );
        }
      }
      cursor.current = at;
      setPosition(at);
      if (at >= clip.end) v.pause();
    },
    [clip, policy.max_points],
  );
  useEffect(() => {
    if (!playing || guideOpen) return;
    let frame = 0;
    function follow() {
      const v = video.current;
      if (!v || v.paused) return;
      syncPlayback(v);
      frame = requestAnimationFrame(follow);
    }
    frame = requestAnimationFrame(follow);
    return () => cancelAnimationFrame(frame);
  }, [playing, guideOpen, syncPlayback]);
  useEffect(() => {
    const container = rail.current;
    const selected = container?.querySelector<HTMLElement>(
      '[aria-pressed="true"]',
    );
    if (!container || !selected) return;
    const offset = selected.offsetLeft;
    if (
      offset < container.scrollLeft ||
      offset + selected.offsetWidth >
        container.scrollLeft + container.clientWidth
    )
      container.scrollLeft = Math.max(0, offset - container.clientWidth / 3);
  }, [patch.start]);

  async function play(v: HTMLVideoElement) {
    try {
      await v.play();
    } catch {
      setNotice("录像暂时无法播放，请重试。");
    }
  }
  function toggle() {
    const v = video.current;
    if (!v) return;
    if (!v.paused) return v.pause();
    if (position >= clip.end) seek(clip.start);
    void play(v);
  }
  function openGuide() {
    const v = video.current;
    resumeAfterGuide.current =
      !!v && !v.paused && !v.ended && v.currentTime < clip.end;
    if (v && !v.paused) {
      v.pause();
      syncPlayback(v);
    }
    setGuideOpen(true);
  }
  function closeGuide() {
    setGuideOpen(false);
    scoreButton.current?.focus({ preventScroll: true });
    if (resumeAfterGuide.current && video.current) void play(video.current);
    resumeAfterGuide.current = false;
  }

  return (
    <>
      <div className="ec-read-grid">
        <div className="ec-media-area ec-monitor-video">
          {failed ? (
            <div className="ec-clip-still">
              <p>本机缺少这段授权录像，仍可点选下方时间轴。</p>
            </div>
          ) : (
            <video
              ref={video}
              muted
              playsInline
              preload="auto"
              aria-label="眼镜第一视角录像"
              src={"/api/v1/eye-care/preview/" + clip.id}
              onLoadedMetadata={(e) => {
                e.currentTarget.currentTime = cursor.current;
                e.currentTarget.playbackRate = speed;
              }}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onEnded={() => {
                setPlaying(false);
                seek(clip.end);
              }}
              onError={() => {
                setFailed(true);
                setPlaying(false);
              }}
            />
          )}
        </div>
        <div className="ec-readout ec-monitor-current">
          <small>当前活动</small>
          <strong>
            {position >= clip.end
              ? "回放结束"
              : missingNow
                ? "数据缺失"
                : activities[patch.activity]}
          </strong>
          <dl>
            <dt>注视媒介</dt>
            <dd>{missingNow ? "—" : media[patch.medium]}</dd>
            <dt>原始时间</dt>
            <dd>{duration(position)}</dd>
          </dl>
          <span className="ec-note">
            从首次确认阅读处起播
            <br />
            录像编号 {clip.id}
          </span>
        </div>
      </div>
      <div className="ec-controls">
        <button onClick={toggle} disabled={failed}>
          {playing ? "暂停" : position >= clip.end ? "重播" : "播放"}
        </button>
        <label>
          速度{" "}
          <select
            value={speed}
            onChange={(e) => {
              const next = Number(e.target.value);
              setSpeed(next);
              if (video.current) video.current.playbackRate = next;
            }}
          >
            {[1, 2, 4, 10].map((n) => (
              <option value={n} key={n}>
                {n}×
              </option>
            ))}
          </select>
        </label>
        <label className="ec-seek">
          原始时间{" "}
          <input
            type="range"
            min={clip.start}
            max={clip.end}
            step="any"
            value={position}
            onChange={(e) => seek(Number(e.target.value))}
          />
        </label>
        <output>
          {duration(position)} / {duration(clip.end)}
        </output>
      </div>
      <div className="ec-stats ec-monitor-stats">
        <div>
          <small>累计阅读时长</small>
          <strong>{duration(read)}</strong>
        </div>
        <div>
          <small>累计视频时长</small>
          <strong>{duration(watched)}</strong>
        </div>
        <button
          type="button"
          className="ec-score"
          ref={scoreButton}
          aria-haspopup="dialog"
          onClick={openGuide}
        >
          <span className="ec-score-top">
            <small>用眼提醒积分</small>
            <span>
              了解积分 <b aria-hidden="true">›</b>
            </span>
          </span>
          <strong>
            {(score / ticks).toFixed(2)} <small>/ {policy.max_points}</small>
          </strong>
          <progress
            aria-hidden="true"
            max={policy.max_points}
            value={score / ticks}
          />
        </button>
      </div>
      {guideOpen && (
        <ScoreGuide
          policy={policy}
          activity={label(patch)}
          range={duration(patch.start) + "–" + duration(patch.end)}
          startScore={startScore.toFixed(2)}
          endScore={endScore.toFixed(2)}
          reason={(missingNow ? "当前秒数据缺失。" : "") + reason}
          onClose={closeGuide}
        />
      )}
      {notice && (
        <p role="status" className="ec-event">
          {notice}
        </p>
      )}
      <h3>活动时间轴</h3>
      <div
        className="ec-patches"
        ref={rail}
        role="group"
        aria-label="每七秒的预测和积分变化"
      >
        {clip.patches.map((p) => {
          const alerts = clip.reminders.filter(
            (t) => t > p.start && t <= p.end,
          );
          return (
            <button
              key={p.start}
              type="button"
              data-state={p.activity}
              aria-pressed={p.start === patch.start}
              onClick={() => seek(p.start)}
              aria-label={
                duration(p.start) + " " + label(p) + " " + change(p) + " 分"
              }
            >
              <small>{duration(p.start)}</small>
              <span>{label(p)}</span>
              <b>{change(p)} 分</b>
              {alerts.map((t) => (
                <em key={t}>{duration(t)} 提醒</em>
              ))}
            </button>
          );
        })}
      </div>
      <section className="ec-patch-detail" aria-label="选中片段的判定依据">
        <h4>
          {duration(patch.start)} – {duration(patch.end)}　{label(patch)}
        </h4>
        <p>
          眼动与头动投票　阅读 {patch.read_votes} 票 · 未阅读{" "}
          {patch.nonread_votes} 票 · 缺失 {patch.missing.length} 秒
        </p>
        <p>
          {patch.reasons.length
            ? "图像复核 · " +
              patch.reasons.map((r) => reasons[r] ?? r).join("、")
            : evidence
              ? "沿用 " + duration(patch.evidence_start!) + " 的图像复核"
              : "此段无有效图像证据"}
        </p>
        {patch.reasons.length > 0 && !evidence && (
          <p>同步画面或注视证据不足。</p>
        )}
        {evidence && (
          <p>
            {evidence.summary}　{evidence.frames.length} 帧中有{" "}
            {evidence.frames.filter((f) => f.hit).length} 帧注视落在材料内。
          </p>
        )}
        <p>
          本段积分 {change(patch)}。{reason}
        </p>
      </section>
    </>
  );
}

export default function Reading() {
  const resource = usePublic<Monitor>("/eye-care/monitor");
  const [kind, choose] = useState<Clip["kind"]>("paper");
  if (!resource.data) return <Loading {...resource} />;
  const { clips, ticks_per_point } = resource.data;
  const clip = clips.find((c) => c.kind === kind)!;
  return (
    <section className="ec-card ec-monitor">
      <header className="ec-head">
        <h2>阅读监测</h2>
        <div className="ec-switch" role="group" aria-label="选择实拍录像">
          {clips.map((c) => (
            <button
              key={c.id}
              aria-pressed={clip.id === c.id}
              onClick={() => choose(c.kind)}
            >
              {c.kind === "paper" ? "纸质阅读" : "电子阅读"}
            </button>
          ))}
        </div>
      </header>
      <Replay
        key={clip.id}
        clip={clip}
        ticks={ticks_per_point}
        policy={resource.data.score_policy}
      />
    </section>
  );
}

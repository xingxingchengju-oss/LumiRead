import { useState } from "react";
import {
  SensorTrend,
  sensorMessage,
  scenes,
  type Replay,
  type Scene,
} from "../parent/Clouclip";
import { Controls, Loading, usePlayback, usePublic } from "./shared";

type Excerpt = Pick<
  Replay,
  "source" | "segment" | "records" | "events" | "scene" | "distance_limit_cm"
>;
function Run({ data }: { data: Excerpt }) {
  const player = usePlayback(0, data.segment.duration_seconds);
  const records = data.records.filter(
    (r) => r.offset_seconds <= player.position,
  );
  const latest = records.at(-1)!;
  const events = data.events
    .filter((e) => e.start_line <= latest.line)
    .map((e) =>
      e.end_line && e.end_line > latest.line
        ? { ...e, end_line: null, ended_at: null }
        : e,
    );
  const replay: Replay = {
    ...data,
    records,
    events,
    status: player.playing ? "playing" : "paused",
    position_seconds: player.position,
    speed: player.speed,
    generation: 0,
  };
  return (
    <>
      <header className="ec-head">
        <div>
          <h3>{data.segment.title}</h3>
          <p>{data.source.timezone} · 成人公开观测</p>
        </div>
        <strong>{latest.Date}</strong>
      </header>
      <div className="clouclip-metrics">
        <SensorTrend replay={replay} metric="Dis" />
        <SensorTrend replay={replay} metric="Lux" />
      </div>
      <Controls player={player} start={0} end={data.segment.duration_seconds} />
      <h3>提醒记录</h3>
      {!events.length && <p>截至当前读数，尚未触发提醒。</p>}
      {events.map((e) => (
        <div
          role="status"
          className={e.ended_at ? "ec-event ec-recovered" : "ec-event"}
          key={e.metric + e.start_line}
        >
          <strong>{sensorMessage(e.metric, data.scene, !!e.ended_at)}</strong>
          <span>
            {e.started_at.slice(11)} 触发 ·{" "}
            {e.ended_at ? e.ended_at.slice(11) + " 解除" : "等待恢复"} ·
            源文件第 {e.start_line} 行
          </span>
        </div>
      ))}
      <details>
        <summary>查看已播放的原始读数</summary>
        <div className="ec-table">
          <table>
            <thead>
              <tr>
                <th>行</th>
                <th>原始时间</th>
                <th>距离 (cm)</th>
                <th>照度 (lux)</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.line}>
                  <td>{r.line}</td>
                  <td>{r.Date}</td>
                  <td>{r.distance_cm ?? "缺测"}</td>
                  <td>{r.illuminance_lx ?? "缺测"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
function Selected({ segment, scene }: { segment: string; scene: Scene }) {
  const data = usePublic<Excerpt>(
    "/eye-care/excerpts/" + segment + "?scene=" + scene,
  );
  return data.data ? <Run data={data.data} /> : <Loading {...data} />;
}
export default function Sensors() {
  const [segment, choose] = useState("dim"),
    [scene, setScene] = useState<Scene>("paper");
  return (
    <section className="ec-card">
      <h2>距离与光照</h2>
      <p>
        选择一次规则演示，再播放 Clouclip
        记录。原始数据只包含时间、距离和佩戴位置照度。
      </p>
      <div className="ec-inputs">
        <label>
          实测片段{" "}
          <select value={segment} onChange={(e) => choose(e.target.value)}>
            <option value="stable">稳定片段</option>
            <option value="near">偏近及恢复</option>
            <option value="dim">偏暗及恢复</option>
          </select>
        </label>
        <label>
          手动选择场景{" "}
          <select
            value={scene}
            onChange={(e) => setScene(e.target.value as Scene)}
          >
            {Object.entries(scenes).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      <Selected key={segment + scene} segment={segment} scene={scene} />
      <p className="ec-note">
        纸质、手机、电脑距离分别低于 33、40、50 cm 满 10
        秒时提醒。佩戴位置照度低于 300 lux 满 30
        秒时提醒。连续两个有效读数达到距离限值加 2 cm 或 350 lux 后解除。WS/T
        773 的 300 lx 指桌面平均照度，这里用眼镜位置的读数提示检查照明。导出表每
        5 秒一行，设备照度更新可能较慢。{" "}
        <a href="https://www.nhc.gov.cn/fzs/c100048/202008/d42388863f2340c4a3ca880b3e6b2c50/files/1733125825170_45982.pdf">
          视屏卫生要求 ↗
        </a>{" "}
        ·{" "}
        <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC11976500/">
          设备研究 ↗
        </a>
      </p>
    </section>
  );
}

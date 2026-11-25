import { useState } from "react";
import { scenes, type Scene } from "../parent/Clouclip";
import { duration, Loading, usePublic } from "./shared";

import type { components } from "../../../../packages/contracts/types";
type Report = components["schemas"]["EyeReport"];
type Source = Report["source"];
type Counts = Report["totals"];

function detailText(detail: Report["details"][number]) {
  if ("metric" in detail) {
    const end = detail.ended_at ? "恢复 " + detail.ended_at : "等待恢复";
    return [
      detail.started_at,
      detail.metric === "Lux" ? "偏暗" : "偏近",
      end,
      "CSV 第 " + detail.start_line + " 行",
    ].join(" · ");
  }
  if ("id" in detail)
    return (
      "RitW " +
      detail.id +
      " · 覆盖 " +
      duration(detail.covered_seconds) +
      " · 模型识别阅读 " +
      duration(detail.predicted_read_seconds)
    );
  const alerts = detail.events.map((e) => {
    const label =
      "metric" in e
        ? e.metric === "Dis"
          ? "偏近"
          : "偏暗"
        : e.kind === "rest_due"
          ? "休息提醒"
          : "休息完成";
    return label + " " + e.started_at.slice(11);
  });
  return [
    detail.start,
    scenes[detail.scene],
    duration(detail.active_seconds),
    alerts.join("，") || "无提醒",
  ].join(" · ");
}
const titles = {
  ritw: "RitW 阅读记录",
  clouclip: "Clouclip 实测记录",
  simulated: "模拟学生周报",
};
function percent(seconds: number, total: number) {
  return total ? ((100 * seconds) / total).toFixed(0) + "%" : "—";
}
function Summary({ source, stats }: { source: Source; stats: Counts }) {
  const sensor = source === "clouclip";
  const cells: [string, string][] = sensor
    ? [
        ["有效观测", duration(stats.coverage_seconds)],
        ["偏近提醒", String(stats.near)],
        ["偏暗提醒", String(stats.dim)],
      ]
    : [
        ["阅读时长", duration(stats.reading_seconds)],
        [
          "纸质占比",
          percent(stats.medium_seconds.Print || 0, stats.reading_seconds),
        ],
        [
          "电子占比",
          percent(stats.medium_seconds.Digital || 0, stats.reading_seconds),
        ],
      ];
  if (source === "simulated")
    cells.push(
      ["偏近提醒", String(stats.near)],
      ["偏暗提醒", String(stats.dim)],
      ["休息提醒", String(stats.breaks)],
    );
  return (
    <div className="ec-stats">
      {cells.map(([k, v]) => (
        <div key={k}>
          <small>{k}</small>
          <strong>{v}</strong>
        </div>
      ))}
    </div>
  );
}
function View({
  source,
  day,
  scene,
  onDay,
}: {
  source: Source;
  day: string;
  scene: Scene;
  onDay: (s: string) => void;
}) {
  const resource = usePublic<Report>(
    "/eye-care/report?source=" +
      source +
      "&scene=" +
      scene +
      (day ? "&day=" + day : ""),
  );
  const [limit, more] = useState(15);
  const [measure, setMeasure] = useState<
    "reading_seconds" | "near" | "dim" | "breaks"
  >(source === "clouclip" ? "near" : "reading_seconds");
  if (!resource.data) return <Loading {...resource} />;
  const r = resource.data,
    today = r.week.find((x) => x.date === r.day)!;
  const sensor = source === "clouclip",
    sim = source === "simulated";
  const amount = (d: Counts) => d[measure];
  const max = Math.max(1, ...r.week.map(amount));
  return (
    <>
      <div className="ec-inputs">
        <label>
          报告日期{" "}
          <input
            type="date"
            value={r.day}
            onChange={(e) => onDay(e.target.value)}
          />
        </label>
        <label>
          有记录的日期{" "}
          <select
            value={r.recorded_days.includes(r.day) ? r.day : ""}
            onChange={(e) => onDay(e.target.value)}
          >
            <option value="" disabled>
              选择日期
            </option>
            {r.recorded_days.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
        </label>
      </div>
      <h3>{sim ? "模拟学生 · " : ""}本周汇总</h3>
      <p>
        {r.week[0].date} 至 {r.week[6].date} ·{" "}
        {r.week.filter((d) => d.recorded).length} 天有记录 · 时长以分:秒显示
      </p>
      {r.week.some((d) => d.recorded) ? (
        <Summary stats={r.totals} source={source} />
      ) : (
        <p>本周无记录。</p>
      )}
      <label>
        趋势指标{" "}
        <select
          value={measure}
          onChange={(e) => setMeasure(e.target.value as typeof measure)}
        >
          {!sensor && <option value="reading_seconds">阅读时长</option>}
          {(sensor || sim) && (
            <>
              <option value="near">偏近提醒</option>
              <option value="dim">偏暗提醒</option>
            </>
          )}
          {sim && <option value="breaks">休息提醒</option>}
        </select>
      </label>
      <div className="ec-week" aria-label="一周每日趋势">
        {r.week.map((d) => (
          <button
            key={d.date}
            aria-pressed={d.date === r.day}
            onClick={() => onDay(d.date)}
          >
            <small>{d.date.slice(5)}</small>
            <span className="ec-column">
              <i
                style={{
                  height: (d.recorded ? (amount(d) / max) * 100 : 0) + "%",
                }}
              />
            </span>
            <strong>
              {d.recorded
                ? measure === "reading_seconds"
                  ? duration(amount(d))
                  : amount(d) + " 次"
                : "无记录"}
            </strong>
          </button>
        ))}
      </div>
      <h3>
        {sim ? "模拟学生 · " : ""}
        {r.day} 日报
      </h3>
      {today.recorded ? (
        <>
          <Summary stats={today} source={source} />
          <p>
            {sensor
              ? "距离和照度的有效覆盖分别为 " +
                duration(today.distance_seconds) +
                " 和 " +
                duration(today.light_seconds) +
                "，无效或断采区间已剔除。"
              : sim
                ? "时长和提醒来自当天的模拟学习记录。"
                : "当日测试片段覆盖 " +
                  duration(today.coverage_seconds) +
                  "。物体文字占 " +
                  percent(
                    today.medium_seconds.Object || 0,
                    today.reading_seconds,
                  ) +
                  "，媒介未确定占 " +
                  percent(
                    today.medium_seconds.Unknown || 0,
                    today.reading_seconds,
                  ) +
                  "。分母为模型判定的阅读时长。"}
          </p>
          {(sensor || sim) && (
            <aside className="ec-context">
              <strong>当日用眼建议</strong>
              {today.near > 0 && (
                <p>
                  出现 {today.near} 次偏近提醒。
                  {sim
                    ? "可按日程中的纸质、手机和电脑场景分别调整距离。"
                    : {
                        paper: "读写时让书本与眼睛相距约一尺。",
                        phone: "将手机移到距离眼睛至少 40 厘米的位置。",
                        computer: "电脑屏幕与眼睛的水平距离至少留出 50 厘米。",
                      }[scene]}
                </p>
              )}
              {today.dim > 0 && (
                <p>
                  出现 {today.dim}{" "}
                  次偏暗提醒。请检查书写面的光线，留意身体或手臂投下的阴影。
                </p>
              )}
              {today.breaks > 0 && (
                <p>
                  达到休息时长 {today.breaks} 次，电子学习后可安排约 10
                  分钟远眺。
                </p>
              )}
              {!today.near && !today.dim && !today.breaks && (
                <p>有效记录中没有触发提醒，可继续保持合适的工作距离与照明。</p>
              )}
              <a href="https://www.moe.gov.cn/jyb_xwfb/gzdt_gzdt/s5987/202306/t20230616_1064573.html">
                教育部近视防控问答 ↗
              </a>
            </aside>
          )}
          <details>
            <summary>
              查看当日{sensor ? "提醒" : "片段"}明细（{r.details.length}）
            </summary>
            <ul className="ec-detail">
              {r.details.slice(0, limit).map((d, i) => (
                <li key={i}>{detailText(d)}</li>
              ))}
            </ul>
            {r.details.length > limit && (
              <button onClick={() => more((n) => n + 25)}>查看更多</button>
            )}
          </details>
        </>
      ) : (
        <p>无记录。当天用眼情况未知。</p>
      )}
    </>
  );
}
export default function Reports() {
  const [source, setSource] = useState<Source>("clouclip"),
    [day, setDay] = useState(""),
    [scene, setScene] = useState<Scene>("paper");
  return (
    <section
      className={"ec-card" + (source === "simulated" ? " ec-simulation" : "")}
    >
      <h2>家长日报与周报</h2>
      <div className="ec-switch">
        {(Object.keys(titles) as Source[]).map((k) => (
          <button
            key={k}
            aria-pressed={source === k}
            onClick={() => {
              setSource(k);
              setDay("");
            }}
          >
            {titles[k]}
          </button>
        ))}
      </div>
      <p className="ec-context">
        {source === "simulated"
          ? "模拟学生 · 虚构的七天家庭记录，所有时长和提醒均来自独立示例。"
          : source === "ritw"
            ? "Meta 成人研究片段，按录像的 UTC 日期汇总。每个日期可能包含不同参与者。"
            : "同一名成年参与者的佩戴记录，按设备所在的美国中部日期汇总。提醒次数来自所选场景的规则回算。"}
      </p>
      {source === "clouclip" && (
        <label>
          手动选择报告场景{" "}
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
      )}
      <View
        key={source + scene}
        source={source}
        day={day}
        scene={scene}
        onDay={setDay}
      />
    </section>
  );
}

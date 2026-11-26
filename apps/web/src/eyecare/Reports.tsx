import { useState } from "react";
import type { components } from "../../../../packages/contracts/types";
import { Chart } from "../parent/Chart";
import { duration, Loading, usePublic } from "./shared";
import "./reports.css";

type Report = components["schemas"]["WeeklyReport"];
type Totals = Report["totals"];
const activities = [
  ["reading", "阅读"],
  ["video", "视频"],
  ["rest", "暂停"],
  ["unknown", "活动待定"],
] as const;
const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
function calendarDate(date: string, showYear = true) {
  const [year, month, day] = date.split("-").map(Number);
  return (showYear ? year + "年" : "") + month + "月" + day + "日";
}

function timeText(seconds: number) {
  const minutes = Math.floor(seconds / 60),
    rest = seconds % 60;
  if (!minutes) return rest + "秒";
  return minutes + "分" + (rest ? rest + "秒" : "");
}

function Overview({ totals }: { totals: Totals }) {
  const metrics = [
    ["记录总时长", totals.total],
    ["阅读时长", totals.reading],
    ["观看视频", totals.video],
  ] as const;
  return (
    <dl className="wr-totals" aria-label="本周片段时长">
      {metrics.map(([label, seconds]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>
            <time dateTime={`PT${seconds}S`}>
              {Math.floor(seconds / 60)}
              <small>分</small>
              {seconds % 60}
              <small>秒</small>
            </time>
          </dd>
        </div>
      ))}
    </dl>
  );
}

function ActivityRadar({ report }: { report: Report }) {
  const media = report.reading_by_medium;
  const axes = [
    ["纸质阅读", media.paper ?? 0],
    ["手机阅读", media.phone ?? 0],
    ["电脑阅读", media.computer ?? 0],
    ["其他文字阅读", media.other_text ?? 0],
    ["观看视频", report.totals.video],
    ["暂停", report.totals.rest],
  ] as const;
  // Choose one whole-minute step for all four rings and all six axes.
  const step = Math.max(
    1,
    Math.ceil(Math.max(...axes.map(([, s]) => s)) / 240),
  );
  return (
    <section className="wr-card" aria-labelledby="wr-radar-title">
      <h2 id="wr-radar-title">各类活动用了多久</h2>
      <p className="wr-sub">六个方向刻度相同，每格 {step} 分钟。</p>
      <div className="wr-radar-body">
        <Chart
          height={222}
          label="六类活动时长雷达图，准确时长见旁边的列表"
          options={(width) => ({
            animation: false,
            radar: {
              indicator: axes.map(([name]) => ({ name, max: step * 4 })),
              radius: Math.min(82, (width - 108) / 2),
              center: ["50%", "50%"],
              splitNumber: 4,
              axisNameGap: 7,
              axisName: { color: "#40584d", fontSize: 12 },
              axisLine: { lineStyle: { color: "#c3cfbd" } },
              splitLine: { lineStyle: { color: "#c7d2c1" } },
              splitArea: { areaStyle: { color: ["#f0f3e8", "#fafaf3"] } },
            },
            series: [
              {
                type: "radar",
                symbol: "circle",
                symbolSize: 6,
                itemStyle: { color: "#245d4d" },
                lineStyle: { width: 2, color: "#346b55" },
                areaStyle: { color: "rgba(104,153,104,.44)" },
                data: [{ value: axes.map(([, seconds]) => seconds / 60) }],
              },
            ],
          })}
        />
        <dl className="wr-values">
          {axes.map(([label, seconds]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{timeText(seconds)}</dd>
            </div>
          ))}
        </dl>
      </div>
      <p className="wr-note">
        另有{timeText(media.unknown ?? 0)}
        已识别为阅读，载体待定。这部分已计入阅读总时长。
      </p>
    </section>
  );
}

function DailyChart({ report }: { report: Report }) {
  const [selected, select] = useState(0);
  const day = report.days[selected];
  const step = Math.max(
    1,
    Math.ceil(Math.max(...report.days.map((d) => d.totals.total)) / 300),
  );
  const maxSeconds = step * 5 * 60;
  return (
    <section className="wr-card" aria-labelledby="wr-days-title">
      <h2 id="wr-days-title">七天的活动分布</h2>
      <ul className="wr-legend" aria-label="图例">
        {activities.map(([key, label]) => (
          <li key={key}>
            <i className={"wr-fill-" + key} />
            {label}
          </li>
        ))}
      </ul>
      <div className="wr-chart-unit">分钟</div>
      <div className="wr-day-chart">
        <div className="wr-scale" aria-hidden="true">
          {[5, 4, 3, 2, 1, 0].map((tick) => (
            <span key={tick}>{tick * step}</span>
          ))}
        </div>
        <div className="wr-bars" role="group" aria-label="选择日期查看片段时长">
          {report.days.map((d, i) => (
            <button
              key={d.date}
              type="button"
              aria-pressed={i === selected}
              aria-label={weekdays[i] + "，记录" + timeText(d.totals.total)}
              aria-controls="wr-day-values"
              onMouseEnter={() => select(i)}
              onFocus={() => select(i)}
              onClick={() => select(i)}
            >
              <span className="wr-track" aria-hidden="true">
                <span
                  className="wr-stack"
                  style={{ height: (100 * d.totals.total) / maxSeconds + "%" }}
                >
                  {activities.map(([key]) => (
                    <i
                      key={key}
                      className={"wr-fill-" + key}
                      style={{ flexGrow: d.totals[key] }}
                    />
                  ))}
                </span>
              </span>
              <span className="wr-day-label">{weekdays[i]}</span>
            </button>
          ))}
        </div>
      </div>
      <div
        className="wr-day-values"
        id="wr-day-values"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <strong>
          {day.date.slice(5).replace("-", "/")} {weekdays[selected]}
        </strong>
        {activities.map(([key, label]) => (
          <span key={key}>
            {label} {timeText(day.totals[key])}
          </span>
        ))}
      </div>
      <p className="wr-note">
        浅灰部分是尚未判定的活动，本周共 {timeText(report.totals.unknown)}。
      </p>
    </section>
  );
}

function ParentLetter({ report }: { report: Report }) {
  const letter = report.publication?.narrative;
  if (!letter)
    return (
      <p className="wr-card" role="status">
        这份周报的文字解读尚未准备好。
      </p>
    );
  const facts = new Map(report.facts.map((f) => [f.id, f.text]));
  return (
    <article className="wr-letter">
      <section aria-labelledby="wr-observation">
        <h2 id="wr-observation">本周观察</h2>
        <p className="wr-prose">{letter.summary}</p>
      </section>
      <section aria-labelledby="wr-actions">
        <h2 id="wr-actions">下周可以试试</h2>
        <ul>
          {letter.suggestions.map((s, i) => (
            <li key={i}>
              <p>{s.action}</p>
              <small>{facts.get(s.fact_id)}</small>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}

export default function Reports() {
  const resource = usePublic<Report>("/eye-care/weekly-report");
  if (!resource.data) return <Loading {...resource} />;
  const r = resource.data;
  return (
    <div className="weekly-report">
      <header className="wr-heading">
        <div>
          <h1>{r.student_label}的用眼周报</h1>
          <p className="wr-dates">
            <time dateTime={r.week.start}>{calendarDate(r.week.start)}</time>
            {" 至 "}
            <time dateTime={r.week.end}>
              {calendarDate(
                r.week.end,
                r.week.start.slice(0, 4) !== r.week.end.slice(0, 4),
              )}
            </time>
          </p>
          <p className="wr-source">{r.source_note}</p>
        </div>
        <img src="/products/frame-open.webp" alt="" />
      </header>
      <Overview totals={r.totals} />
      <div className="wr-charts">
        <ActivityRadar report={r} />
        <DailyChart report={r} />
      </div>
      <ParentLetter report={r} />
      <details className="wr-sources">
        <summary>查看 {r.clips.length} 段录像的来源与区间</summary>
        <table>
          <thead>
            <tr>
              <th>编排日期</th>
              <th>Meta 录像 ID</th>
              <th>原录像起止时间</th>
            </tr>
          </thead>
          <tbody>
            {[...r.clips]
              .sort((a, b) => a.date.localeCompare(b.date))
              .map((c) => (
                <tr key={c.id}>
                  <td>{c.date}</td>
                  <td>{c.id}</td>
                  <td>
                    {duration(c.start)} – {duration(c.end)}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

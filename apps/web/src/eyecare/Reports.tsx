import { useState } from "react";
import type { components } from "../../../../packages/contracts/types";
import { duration, Loading, usePublic } from "./shared";
import windowScene from "./weekly-window.webp";
import "./reports.css";

type Report = components["schemas"]["WeeklyReport"];
type Totals = Report["totals"];
const activities = [
  ["reading", "阅读"],
  ["video", "视频"],
  ["rest", "暂停"],
  ["unknown", "活动待定"],
] as const;

function weekday(date: string) {
  return "周" + "日一二三四五六"[new Date(date + "T00:00:00Z").getUTCDay()];
}

function timeText(seconds: number) {
  const minutes = Math.floor(seconds / 60),
    rest = seconds % 60;
  if (!minutes) return rest + "秒";
  return minutes + "分" + (rest ? rest + "秒" : "");
}

function ReportDates({ week }: { week: Report["week"] }) {
  const [year, month, first] = week.start.split("-").map(Number);
  const [endYear, endMonth, last] = week.end.split("-").map(Number);
  return (
    <p className="wr-dates">
      <time dateTime={week.start}>
        <span className="wr-month">
          <span>{year} 年</span>
          <b>{month} 月</b>
        </span>
        <strong>{first}</strong>
      </time>
      <span className="wr-date-dash">–</span>
      <time dateTime={week.end}>
        {(endYear !== year || endMonth !== month) && (
          <span className="wr-month">
            {endYear !== year && <span>{endYear} 年</span>}
            <b>{endMonth} 月</b>
          </span>
        )}
        <strong>{last}</strong>
        <span className="wr-date-unit">日</span>
      </time>
    </p>
  );
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

function ActivityBreakdown({ report }: { report: Report }) {
  const media = report.reading_by_medium;
  const rows = [
    { label: "纸质阅读", seconds: media.paper ?? 0, kind: "reading" },
    { label: "手机阅读", seconds: media.phone ?? 0, kind: "reading" },
    { label: "电脑阅读", seconds: media.computer ?? 0, kind: "reading" },
    { label: "其他文字阅读", seconds: media.other_text ?? 0, kind: "reading" },
    { label: "观看视频", seconds: report.totals.video, kind: "video" },
    { label: "暂停", seconds: report.totals.rest, kind: "rest" },
  ].sort((a, b) => b.seconds - a.seconds);
  const stepMinutes = Math.max(1, Math.ceil(rows[0].seconds / (4 * 60)));
  const maxSeconds = 4 * stepMinutes * 60;

  return (
    <section className="wr-breakdown" aria-labelledby="wr-activities">
      <h2 id="wr-activities">各类活动用了多久</h2>
      <div className="wr-rank-axis" aria-hidden="true">
        <span>分钟</span>
        <div>
          {[0, 1, 2, 3, 4].map((tick) => (
            <i key={tick} style={{ left: tick * 25 + "%" }}>
              {tick * stepMinutes}
            </i>
          ))}
        </div>
      </div>
      <ol className="wr-ranking" role="list" aria-label="六类活动时长">
        {rows.map(({ label, seconds, kind }) => (
          <li key={label}>
            <span>{label}</span>
            <span className="wr-rank-track" aria-hidden="true">
              <i
                className={"wr-fill-" + kind}
                style={{ width: (seconds / maxSeconds) * 100 + "%" }}
              />
            </span>
            <time dateTime={`PT${seconds}S`}>{timeText(seconds)}</time>
          </li>
        ))}
      </ol>
      {media.unknown > 0 && (
        <p className="wr-note">
          另有
          <time dateTime={`PT${media.unknown}S`}>
            {timeText(media.unknown)}
          </time>
          已识别为阅读，载体待定。这部分已计入阅读总时长。
        </p>
      )}
    </section>
  );
}

function DailyChart({ report }: { report: Report }) {
  const [selected, select] = useState(0);
  const day = report.days[selected] ?? report.days[0];
  if (!day) return <p className="wr-note">本周暂无每日片段记录。</p>;
  const step = Math.max(
    1,
    Math.ceil(Math.max(...report.days.map((d) => d.totals.total)) / 300),
  );
  const maxSeconds = step * 5 * 60;
  const clips = report.clips.filter((clip) => clip.date === day.date).length;
  return (
    <section className="wr-days" aria-labelledby="wr-days-title">
      <h2 id="wr-days-title">七天的活动分布</h2>
      <ul className="wr-legend" aria-label="图例">
        {activities.map(([key, label]) => (
          <li key={key}>
            <i className={"wr-fill-" + key} aria-hidden="true" />
            {label}
          </li>
        ))}
      </ul>
      <div className="wr-chart-unit" aria-hidden="true">
        分钟
      </div>
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
              aria-pressed={d.date === day.date}
              aria-label={weekday(d.date) + "，记录" + timeText(d.totals.total)}
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
              <span className="wr-day-label">{weekday(d.date)}</span>
            </button>
          ))}
        </div>
      </div>
      <div
        className="wr-day-values"
        id="wr-day-values"
        role="status"
        aria-atomic="true"
      >
        <div className="wr-slip-date">
          <time dateTime={day.date}>{day.date.slice(5).replace("-", "/")}</time>
          <span>
            {weekday(day.date)} · {clips} 个片段
          </span>
        </div>
        <div className="wr-slip-times">
          {activities.map(([key, label]) => (
            <span key={key}>
              {label}{" "}
              <time dateTime={`PT${day.totals[key]}S`}>
                {timeText(day.totals[key])}
              </time>
            </span>
          ))}
        </div>
      </div>
      {report.totals.unknown > 0 && (
        <p className="wr-note">
          灰色斜线是尚未判定的活动，本周共{" "}
          <time dateTime={`PT${report.totals.unknown}S`}>
            {timeText(report.totals.unknown)}
          </time>
          。
        </p>
      )}
    </section>
  );
}

function keepDurationsTogether(text: string) {
  return text.split(/(\d+分(?:\d+秒)?|\d+秒)/).map((part, index) =>
    index % 2 === 1 ? (
      <span className="wr-duration" key={index}>
        {part}
      </span>
    ) : (
      part
    ),
  );
}

function ParentLetter({ report }: { report: Report }) {
  const letter = report.publication?.narrative;
  if (!letter)
    return <p className="wr-letter wr-note">这份周报的文字解读尚未准备好。</p>;
  const facts = new Map(report.facts.map((f) => [f.id, f.text]));
  return (
    <div className="wr-letter">
      <section aria-labelledby="wr-observation">
        <h2 id="wr-observation">本周观察</h2>
        <p className="wr-prose">{keepDurationsTogether(letter.summary)}</p>
      </section>
      <section className="wr-actions" aria-labelledby="wr-actions">
        <h2 id="wr-actions">下周可以试试</h2>
        <ul role="list">
          {letter.suggestions.map((suggestion) => (
            <li key={suggestion.fact_id}>
              <div>
                <p>{suggestion.action}</p>
                <small>
                  {keepDurationsTogether(facts.get(suggestion.fact_id) ?? "")}
                </small>
              </div>
              {suggestion.fact_id === "paper" && (
                <img src={windowScene} alt="" width="660" height="338" />
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function ClipSources({ clips }: { clips: Report["clips"] }) {
  return (
    <details className="wr-sources">
      <summary>查看 {clips.length} 段录像的来源与区间</summary>
      <div
        className="wr-table-wrap"
        role="region"
        aria-label="原录像区间"
        tabIndex={0}
      >
        <table>
          <thead>
            <tr>
              <th scope="col">编排日期</th>
              <th scope="col">Meta 录像 ID</th>
              <th scope="col">原录像起止时间</th>
            </tr>
          </thead>
          <tbody>
            {[...clips]
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
      </div>
    </details>
  );
}

export default function Reports() {
  const resource = usePublic<Report>("/eye-care/weekly-report");
  if (!resource.data) return <Loading {...resource} />;
  const r = resource.data;
  return (
    <div className="weekly-report">
      <article className="wr-book" aria-labelledby="wr-title">
        <div className="wr-page wr-page-week">
          <header className="wr-heading">
            <div className="wr-dateline">
              <ReportDates week={r.week} />
              <span className="wr-frame-mark" aria-hidden="true">
                <img
                  src="/products/frame-open.webp"
                  alt=""
                  width="1440"
                  height="833"
                />
              </span>
            </div>
            <h1 id="wr-title">{r.student_label}的用眼周报</h1>
            <p className="wr-source">{r.source_note}</p>
          </header>
          <Overview totals={r.totals} />
          <ActivityBreakdown report={r} />
        </div>
        <div className="wr-page wr-page-daily">
          <DailyChart key={r.week.start} report={r} />
          <ParentLetter report={r} />
        </div>
      </article>
      <ClipSources clips={r.clips} />
    </div>
  );
}

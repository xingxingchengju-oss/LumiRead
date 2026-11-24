import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  api,
  json,
  message,
  type ArchivedItem,
  type Attempt,
  type Mastery,
  type Recommendation,
} from "../api";
import { dateTime, skills, useResource } from "./data";
import { Question } from "./Fields";
const Chart = lazy(() => import("./Chart").then((m) => ({ default: m.Chart })));
const short: Record<string, string> = {
  mixed_arithmetic: "四则",
  fractions: "分数",
  decimals: "小数",
  equations: "方程",
  area: "面积",
  word_modeling: "应用",
};
export function Profile({ profile }: { profile: Mastery }) {
  const options = useCallback(
    (width: number, height: number) => {
      const rows = profile.skills,
        radius = Math.min(width * 0.33, height * 0.345),
        cx = width * 0.5,
        cy = height * 0.5;
      const vals = rows.map((s) =>
        s.probability === null ? null : Math.round(s.probability * 1000) / 10,
      );
      const hasAll = vals.every((v) => v !== null);
      return {
        animation: false,
        radar: {
          center: [cx, cy],
          radius,
          splitNumber: 4,
          axisNameGap: 8,
          indicator: rows.map((s) => ({
            name: short[s.skill] || s.skill,
            max: 100,
          })),
          axisName: { color: "#385244", fontSize: 12 },
          axisLine: { lineStyle: { color: "#bdcbbf" } },
          splitArea: { areaStyle: { color: ["#eff4e9", "#f8faf4"] } },
          splitLine: { lineStyle: { color: "#c0cfc0" } },
        },
        series: [
          {
            type: "radar",
            symbolSize: 5,
            itemStyle: { color: "#38654d" },
            lineStyle: { width: 2 },
            areaStyle: { color: "#729e75", opacity: 0.48 },
            data: hasAll ? [{ value: vals }] : [],
          },
        ],
        graphic: hasAll
          ? []
          : vals.flatMap((v, i) => {
              if (v === null) return [];
              const angle = Math.PI / 2 + (2 * Math.PI * i) / vals.length;
              return [
                {
                  type: "circle",
                  shape: {
                    cx: cx + radius * (v / 100) * Math.cos(angle),
                    cy: cy - radius * (v / 100) * Math.sin(angle),
                    r: 4,
                  },
                  style: { fill: "#38654d" },
                },
              ];
            }),
      };
    },
    [profile],
  );
  return (
    <section className="paper">
      <div className="entry-heading">
        <h2>六维学习画像</h2>
        <span className="status">
          {profile.available ? "DKT 预测" : "模型待就绪"}
        </span>
      </div>
      <p className="muted">
        {profile.available &&
        profile.skills.every((s) => s.evidence_count === 0)
          ? "尚无个人作答。当前显示模型对首题的初始答对概率。"
          : "下一道同类题的预计答对概率，附已记录的作答数。"}
      </p>
      <div className="profile-body">
        <Suspense fallback={<p>正在绘制雷达图…</p>}>
          <Chart
            height={244}
            options={options}
            label="六类知识点答对概率雷达图，数值列于下方"
          />
        </Suspense>
        <ul className="skill-list">
          {profile.skills.map((s) => (
            <li key={s.skill}>
              <span>{skills[s.skill]}</span>
              <b>
                {s.probability === null
                  ? "暂无预测"
                  : `${Math.round(s.probability * 100)}%`}
              </b>
              <small>{s.evidence_count} 次作答</small>
            </li>
          ))}
        </ul>
      </div>
      {profile.available ? (
        <small className="muted">
          模型 {profile.model_version} · {(profile.device || "").toUpperCase()}
        </small>
      ) : (
        <p className="muted">模型就绪后将显示概率。现有作答数已保留。</p>
      )}
    </section>
  );
}
type Solved = { id: string; answer: string; result: Attempt };
function Practice({
  item,
  onSolved,
  onStart,
}: {
  item: Recommendation;
  onSolved: (s: Solved) => void;
  onStart: () => void;
}) {
  const [answer, setAnswer] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const pending = useRef(false),
    submission = useRef<{ answer: string; idem: string } | null>(null);
  async function send() {
    if (pending.current || !answer.trim()) return;
    pending.current = true;
    setBusy(true);
    setError("");
    const input = answer.trim();
    if (!submission.current || submission.current.answer !== input)
      submission.current = { answer: input, idem: crypto.randomUUID() };
    try {
      const result = await api<Attempt>(
        `/recommendations/${item.id}/attempts`,
        json("POST", submission.current),
      );
      onSolved({ id: item.id, answer: input, result });
    } catch (e) {
      setError(message(e));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <form
      className="practice"
      onSubmit={(e) => {
        e.preventDefault();
        void send();
      }}
    >
      <small>{skills[item.skill]}</small>
      <h3>{item.question}</h3>
      <label>
        你的答案
        <input
          required
          maxLength={100}
          value={answer}
          onChange={(e) => {
            onStart();
            setAnswer(e.target.value);
          }}
          autoComplete="off"
        />
      </label>
      <button disabled={busy || !answer.trim()}>提交答案</button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}
export function Archive({
  learner,
  bus,
  showProfile = true,
}: {
  learner: string;
  bus: EventTarget;
  showProfile?: boolean;
}) {
  const base = `/learners/${encodeURIComponent(learner)}`;
  const [filter, setFilter] = useState(""),
    [solved, setSolved] = useState<Solved[]>([]);
  const [round, setRound] = useState<Recommendation[]>([]);
  const locked = useRef(false);
  const training = useResource<Mastery>(
    showProfile ? base + "/mastery" : null,
    bus,
    "mastery.updated",
  );
  const tasks = useResource<{ items: Recommendation[] }>(
    base + "/recommendations",
    bus,
    "recommendations.ready",
  );
  const archive = useResource<{ items: ArchivedItem[] }>(
    base + "/mistakes" + (filter ? "?skill=" + encodeURIComponent(filter) : ""),
    bus,
    "mistake.saved question.reviewed",
  );
  useEffect(() => {
    if (tasks.data && !locked.current) setRound(tasks.data.items);
  }, [tasks.data]);
  const finished =
    round.length > 0 && round.every((t) => solved.some((s) => s.id === t.id));
  const nextRound = tasks.data?.items;
  const canAdvance =
    finished &&
    nextRound?.length &&
    nextRound.some((t) => !round.some((old) => old.id === t.id));
  const finish = (entry: Solved) => {
    setSolved((old) => [entry, ...old.filter((s) => s.id !== entry.id)]);
    training.reload();
    tasks.reload();
  };
  return (
    <div className="stack">
      {showProfile && training.error && (
        <p className="error" role="alert">
          {training.error}{" "}
          <button className="link" onClick={training.reload}>
            重试画像
          </button>
        </p>
      )}
      {showProfile &&
        (training.data ? (
          <Profile profile={training.data} />
        ) : (
          !training.error && <p>正在读取学习画像…</p>
        ))}
      <section className="paper">
        <h2>巩固练习</h2>
        {solved.length > 0 && (
          <div aria-live="polite" className="practice-history">
            {solved.map((s) => (
              <article key={s.id}>
                <strong>
                  {s.result.correct ? "✓ 回答正确" : "× 再看一看"}
                </strong>
                <p>{s.result.question}</p>
                <p>
                  你的答案　{s.answer}　 / 　参考答案　
                  {s.result.reference_answer}
                </p>
                <p>{s.result.explanation}</p>
              </article>
            ))}
          </div>
        )}
        {tasks.error && (
          <p className="error" role="alert">
            {tasks.error}{" "}
            <button className="link" onClick={tasks.reload}>
              重试练习
            </button>
          </p>
        )}
        {round.map(
          (t) =>
            !solved.some((s) => s.id === t.id) && (
              <Practice
                key={t.id}
                item={t}
                onStart={() => {
                  locked.current = true;
                }}
                onSolved={finish}
              />
            ),
        )}
        {canAdvance ? (
          <button
            onClick={() => {
              setSolved([]);
              setRound(nextRound!);
              locked.current = false;
            }}
          >
            开始下一组练习
          </button>
        ) : null}
        {tasks.data?.items.length === 0 && !round.length && (
          <p className="muted">暂无巩固题，模型生成推荐后会自动更新。</p>
        )}
        {!tasks.data && !tasks.error && <p>正在读取推荐…</p>}
      </section>
      <section className="paper">
        <div className="entry-heading">
          <h2>历史错题</h2>
          <label className="filter-label">
            知识点
            <select
              aria-label="知识点"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="">全部知识点</option>
              {Object.entries(skills).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </div>
        {archive.error && (
          <p className="error" role="alert">
            {archive.error}{" "}
            <button className="link" onClick={archive.reload}>
              重试错题
            </button>
          </p>
        )}
        {archive.data?.items.map((item, i) => (
          <article key={item.id + "-" + item.revision}>
            <small className="muted">收藏于 {dateTime(item.created)}</small>
            <Question item={item} number={i + 1} learner={learner} archived />
          </article>
        ))}
        {archive.data?.items.length === 0 && (
          <p className="muted">
            {filter
              ? "这个知识点还没有收藏。"
              : "在今日作业中收藏错题，即可跨场次回看讲解。"}
          </p>
        )}
      </section>
    </div>
  );
}

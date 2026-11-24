import { useEffect, useId, useRef, useState } from "react";
import { api, message } from "../api";
import { skills } from "../parent/data";
import "../parent/demo.css";
import "./federated.css";

interface Round {
  round: number;
  client_count: number;
  target_count: number;
  client_target_min: number;
  client_target_max: number;
  client_target_histogram: Record<string, number>;
  validation_auc: number;
  validation_brier: number;
  validation_log_loss: number;
  train_loss: number;
  elapsed_seconds: number;
  logical_upload_bytes: number;
  logical_download_bytes: number;
  update_l2: number;
}
type Score = {
  attempts: number;
  correct: number;
  auc: number | null;
  accuracy: number | null;
  f1: number | null;
  precision: number | null;
  recall: number | null;
  brier: number | null;
  log_loss: number | null;
  confusion_matrix: number[][];
};
type Study = {
  overall: Score;
  short_history: Score;
  per_skill: Record<string, Score>;
};
type Run = {
  seed: number;
  best_round: number;
  best_validation_auc: number;
  rounds: Round[];
  test: Score;
};
type Report = {
  schema_version: number;
  status: string;
  method: string;
  dataset: {
    name: string;
    train_students: number;
    validation_students: number;
    test_students: number;
    train_targets: number;
    validation_targets: number;
    test_targets: number;
  };
  protocol: {
    clients_per_round: number;
    local_epochs: number;
    local_optimizer: string;
    short_history_max_prior: number;
    threshold: number;
  };
  selected: {
    seed: number;
    round: number;
    validation_auc: number;
    model_version: string;
    device: string;
  };
  runs: Run[];
  comparison: { central_dkt: Study; federated_dkt: Study; lightgbm: Study };
  provenance: {
    source_url: string;
    training_device: string;
    protocol_sha256: string;
    dataset_sha256: string;
  };
};
const steps = ["模型下发", "本地训练", "更新回传", "加权聚合"];
const metrics = {
  validation_auc: "验证 ROC AUC",
  validation_brier: "验证 Brier 分数",
  validation_log_loss: "验证对数损失",
} as const;
type Metric = keyof typeof metrics;
const names = {
  central_dkt: "集中式 DKT",
  federated_dkt: "联邦 DKT",
  lightgbm: "LightGBM",
} as const;
const count = (value: number) => value.toLocaleString("zh-CN");
const decimal = (value: number | null, digits = 4) =>
  value === null ? "—" : value.toFixed(digits);

function Plot({
  rounds,
  index,
  metric,
  onSeek,
}: {
  rounds: Round[];
  index: number;
  metric: Metric;
  onSeek: (index: number) => void;
}) {
  const title = useId();
  const surface = useRef<SVGSVGElement>(null);
  const [width, setWidth] = useState(800);
  useEffect(() => {
    const node = surface.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.max(240, Math.round(entry.contentRect.width)));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const left = width < 500 ? 46 : 66,
    top = 16,
    right = width - 32,
    bottom = 174;
  const values = rounds.map((r) => r[metric]);
  const min = Math.min(...values),
    max = Math.max(...values);
  const span = Math.max(max - min, 0.005);
  const lo = Math.max(0, min - 0.09 * span),
    hi = max + 0.09 * span;
  const x = (i: number) =>
    left + ((right - left) * i) / Math.max(1, rounds.length - 1);
  const y = (v: number) => bottom - ((bottom - top) * (v - lo)) / (hi - lo);
  const points = (v: number[]) => v.map((n, i) => x(i) + "," + y(n)).join(" ");
  const ticks = [
    ...new Set([0, Math.floor((rounds.length - 1) / 2), rounds.length - 1]),
  ];
  return (
    <svg
      ref={surface}
      className="fed-plot"
      viewBox={"0 0 " + width + " 208"}
      role="slider"
      tabIndex={0}
      aria-valuemin={1}
      aria-valuemax={rounds.length}
      aria-valuenow={index + 1}
      aria-labelledby={title}
      onClick={(e) => {
        const matrix = e.currentTarget.getScreenCTM();
        if (!matrix) return;
        const point = new DOMPoint(e.clientX, e.clientY).matrixTransform(
          matrix.inverse(),
        );
        onSeek(
          Math.max(
            0,
            Math.min(
              rounds.length - 1,
              Math.round(
                ((point.x - left) / (right - left)) * (rounds.length - 1),
              ),
            ),
          ),
        );
      }}
      onKeyDown={(e) => {
        const position: Record<string, number> = {
          ArrowLeft: index - 1,
          ArrowDown: index - 1,
          ArrowRight: index + 1,
          ArrowUp: index + 1,
          Home: 0,
          End: rounds.length - 1,
        };
        if (!(e.key in position)) return;
        e.preventDefault();
        onSeek(Math.max(0, Math.min(rounds.length - 1, position[e.key])));
      }}
    >
      <title id={title}>
        {metrics[metric]}，当前第 {rounds[index].round} 轮，数值{" "}
        {decimal(values[index])}。各轮完整数值列于下方表格。
      </title>
      {[0, 1, 2, 3].map((t) => {
        const v = lo + ((hi - lo) * t) / 3;
        return (
          <g key={t}>
            <line
              x1={left}
              x2={right}
              y1={y(v)}
              y2={y(v)}
              stroke="#d2dbd4"
              strokeDasharray="4 4"
            />
            <text x={left - 9} y={y(v) + 4} textAnchor="end">
              {v.toFixed(3)}
            </text>
          </g>
        );
      })}
      <polyline
        points={points(values)}
        fill="none"
        stroke="#80988e"
        strokeWidth="2.3"
        strokeDasharray="5 4"
      />
      <polyline
        points={points(values.slice(0, index + 1))}
        fill="none"
        stroke="#145749"
        strokeWidth="3"
      />
      <line
        x1={x(index)}
        x2={x(index)}
        y1={top}
        y2={bottom}
        stroke="#65766a"
        strokeDasharray="3 3"
      />
      <circle
        cx={x(index)}
        cy={y(values[index])}
        r="5"
        fill="#f1bc75"
        stroke="#244236"
        strokeWidth="2"
      />
      {ticks.map((i) => (
        <text key={i} x={x(i)} y="198" textAnchor="middle">
          第 {rounds[i].round} 轮
        </text>
      ))}
    </svg>
  );
}

function RunPlayer({ run, report }: { run: Run; report: Report }) {
  const [cursor, setCursor] = useState(
      () =>
        run.rounds.findIndex((row) => row.round === run.best_round) *
        steps.length,
    ),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1),
    [metric, setMetric] = useState<Metric>("validation_auc");
  const stage = cursor % steps.length,
    index = Math.floor(cursor / steps.length),
    last = run.rounds.length * steps.length - 1;
  const row = run.rounds[index];
  useEffect(() => {
    if (!playing) return;
    if (cursor === last) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setCursor(cursor + 1), 950 / speed);
    return () => window.clearTimeout(timer);
  }, [playing, cursor, speed, last]);
  useEffect(() => {
    const pause = () => {
      if (document.hidden) setPlaying(false);
    };
    document.addEventListener("visibilitychange", pause);
    return () => document.removeEventListener("visibilitychange", pause);
  }, []);
  function seek(next: number, phase = 0) {
    setPlaying(false);
    setCursor(next * steps.length + phase);
  }
  const stageCopy = [
    "服务器向 " +
      count(row.client_count) +
      " 位参与者各下发一份当前模型，共 " +
      count(row.logical_download_bytes) +
      " 字节。",
    "每位参与者在自己的作答序列上执行 " +
      report.protocol.local_epochs +
      " 遍 " +
      report.protocol.local_optimizer +
      " 训练。本轮共有 " +
      count(row.target_count) +
      " 次有效作答。",
    count(row.client_count) +
      " 位参与者回传本地模型更新，共 " +
      count(row.logical_upload_bytes) +
      " 字节。",
    "按各参与者的有效作答数加权平均。本轮全局参数更新的 L2 范数为 " +
      decimal(row.update_l2) +
      "。",
  ];
  const dots = Object.entries(row.client_target_histogram)
    .sort(([a], [b]) => Number(a) - Number(b))
    .flatMap(([n, clients]) => Array<string>(clients).fill(n));
  return (
    <>
      <section className="fed-panel player-panel" aria-labelledby="play-title">
        <div className="fed-panel-head">
          <div>
            <h2 id="play-title">训练过程回放</h2>
            <p>
              种子 {run.seed} · 验证 AUC 最高点在第 {run.best_round} 轮
            </p>
          </div>
          <div className="current-round">
            <b>第 {row.round} 轮</b>
            <small>共 {run.rounds.length} 轮</small>
          </div>
        </div>
        <div className="fed-playbar">
          <button
            className="play-toggle"
            aria-pressed={playing}
            onClick={() => {
              if (!playing && cursor === last) setCursor(0);
              setPlaying(!playing);
            }}
          >
            {playing ? "暂停回放" : cursor === last ? "重新播放" : "播放回放"}
          </button>
          <button
            className="link play-start"
            onClick={() => {
              setCursor(0);
              setPlaying(true);
            }}
          >
            从第 1 轮播放
          </button>
          <label className="seek">
            回放轮次
            <input
              type="range"
              min="1"
              max={run.rounds.length}
              value={index + 1}
              onChange={(e) => seek(Number(e.target.value) - 1)}
            />
          </label>
          <label className="speed">
            播放速度
            <select
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
            >
              {[1, 2, 4].map((v) => (
                <option key={v} value={v}>
                  {v}×
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="stage-strip" role="group" aria-label="训练阶段">
          {steps.map((label, i) => (
            <button
              key={label}
              aria-pressed={stage === i}
              onClick={() => seek(index, i)}
            >
              <small>{String(i + 1).padStart(2, "0")}</small> {label}
            </button>
          ))}
        </div>
        <div
          className="training-stage"
          data-stage={stage}
          data-playing={playing}
        >
          <div className="node-server">
            <span className="rack" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <strong>全局模型</strong>
          </div>
          <div className="model-wire" aria-hidden="true">
            <span>{stage === 0 ? "→" : stage === 2 ? "←" : "·"}</span>
          </div>
          <div className="node-clients">
            <div
              className="client-dots"
              aria-label={dots.length + " 位参与者，按有效作答数排列"}
            >
              {dots.map((n, i) => (
                <i key={i} title={"有效作答 " + n + " 次"} />
              ))}
            </div>
            <strong>{count(row.client_count)} 位参与者</strong>
          </div>
        </div>
        <p className="stage-description">
          <strong>{steps[stage]}</strong>　{stageCopy[stage]}
        </p>
        <dl className="round-values">
          {[
            ["参与客户端", count(row.client_count)],
            ["有效作答数", count(row.target_count)],
            ["下发字节", count(row.logical_download_bytes)],
            ["回传字节", count(row.logical_upload_bytes)],
          ].map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        <p className="fed-note">
          一位训练集学生对应一个模拟客户端。通信量按 FP32
          模型参数换算，仅统计模型张量。
        </p>
      </section>
      <section className="fed-panel" aria-labelledby="val-title">
        <div className="fed-panel-head">
          <div>
            <h2 id="val-title">验证曲线</h2>
            <p>实线截至当前轮次，虚线显示本次完整训练。</p>
          </div>
          <label className="field-select">
            验证指标
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value as Metric)}
            >
              {Object.entries(metrics).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="curve-value">
          <strong>{decimal(row[metric])}</strong>
          <span>
            第 {row.round} 轮 · {metrics[metric]}
          </span>
        </div>
        <Plot rounds={run.rounds} index={index} metric={metric} onSeek={seek} />
        <details className="round-details">
          <summary>查看每轮记录（{run.rounds.length}）</summary>
          <div className="table-clip">
            <table>
              <caption>点击轮次定位回放</caption>
              <thead>
                <tr>
                  {[
                    "轮次",
                    "参与者",
                    "有效作答",
                    "训练损失",
                    "验证 AUC",
                    "耗时（秒）",
                  ].map((k) => (
                    <th scope="col" key={k}>
                      {k}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {run.rounds.map((r, i) => (
                  <tr
                    key={r.round}
                    aria-current={index === i ? "true" : undefined}
                  >
                    <td>
                      <button
                        className="link"
                        onClick={() => seek(i)}
                        aria-label={"查看第 " + r.round + " 轮"}
                      >
                        第 {r.round} 轮
                      </button>
                    </td>
                    <td>{r.client_count}</td>
                    <td>{count(r.target_count)}</td>
                    <td>{decimal(r.train_loss)}</td>
                    <td>{decimal(r.validation_auc)}</td>
                    <td>{decimal(r.elapsed_seconds, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>
    </>
  );
}
function Comparison({ report }: { report: Report }) {
  const [group, setGroup] = useState("overall");
  return (
    <section className="fed-panel" aria-labelledby="test-title">
      <div className="fed-panel-head">
        <div>
          <h2 id="test-title">同一测试集上的模型表现</h2>
          <p>
            三种模型在相同留出学生的作答上评估。联邦模型采用验证集选出的种子{" "}
            {report.selected.seed}、第 {report.selected.round} 轮权重。
          </p>
        </div>
        <label className="field-select">
          测试范围
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="overall">全部测试作答</option>
            <option value="short_history">
              短历史（此前至多 {report.protocol.short_history_max_prior}{" "}
              次作答）
            </option>
            {Object.keys(report.comparison.federated_dkt.per_skill).map((s) => (
              <option key={s} value={s}>
                {skills[s] || s}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div
        className="table-clip"
        tabIndex={0}
        role="region"
        aria-label="测试集指标表"
      >
        <table className="compare-table">
          <thead>
            <tr>
              {[
                "模型",
                "有效作答",
                "ROC AUC",
                "准确率",
                "F1",
                "Brier 分数",
                "对数损失",
              ].map((k) => (
                <th scope="col" key={k}>
                  {k}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(Object.keys(names) as (keyof typeof names)[]).map((k) => {
              const model = report.comparison[k],
                score =
                  group === "overall" || group === "short_history"
                    ? model[group]
                    : model.per_skill[group];
              return (
                <tr key={k}>
                  <th scope="row">{names[k]}</th>
                  <td>{count(score.attempts)}</td>
                  {[
                    score.auc,
                    score.accuracy,
                    score.f1,
                    score.brier,
                    score.log_loss,
                  ].map((n, i) => (
                    <td key={i}>{decimal(n)}</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="fed-note">
        Brier 分数和对数损失越低越好。现场上传与练习只更新登录账号的学习记录。
      </p>
    </section>
  );
}
function StudyPage({ report }: { report: Report }) {
  const [seed, setSeed] = useState(report.selected.seed);
  const run = report.runs.find((r) => r.seed === seed)!;
  return (
    <>
      <header className="fed-cover">
        <p>本机多客户端模拟 · 真实训练记录回放</p>
        <h1>联邦学习实验</h1>
        <p>回看各客户端在自己的作答序列上训练，以及服务器如何汇总更新。</p>
        <dl>
          {[
            ["训练学生", count(report.dataset.train_students)],
            ["验证学生", count(report.dataset.validation_students)],
            ["测试学生", count(report.dataset.test_students)],
          ].map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </header>
      <div className="run-picker">
        <label>
          训练种子
          <select
            value={seed}
            onChange={(e) => setSeed(Number(e.target.value))}
          >
            {report.runs.map((r) => (
              <option key={r.seed} value={r.seed}>
                {r.seed}
                {r.seed === report.selected.seed ? " · 验证集入选" : ""}
              </option>
            ))}
          </select>
        </label>
        <span>
          本次最佳验证 AUC <b>{decimal(run.best_validation_auc)}</b>　测试 AUC{" "}
          <b>{decimal(run.test.auc)}</b>
        </span>
      </div>
      <RunPlayer key={seed} run={run} report={report} />
      <Comparison report={report} />
      <details className="fed-panel report-source">
        <summary>数据来源与复核</summary>
        <dl className="source-list">
          <div>
            <dt>数据来源</dt>
            <dd>
              <a href={report.provenance.source_url}>{report.dataset.name}</a>
            </dd>
          </div>
          <div>
            <dt>权重版本</dt>
            <dd>
              <code>{report.selected.model_version}</code> ·{" "}
              {report.provenance.training_device.toUpperCase()}
            </dd>
          </div>
          <div>
            <dt>数据校验</dt>
            <dd>
              <code>{report.provenance.dataset_sha256}</code>
            </dd>
          </div>
          <div>
            <dt>协议校验</dt>
            <dd>
              <code>{report.provenance.protocol_sha256}</code>
            </dd>
          </div>
        </dl>
        <a href="/api/v1/federated" download="federated-report.json">
          下载完整训练报告（JSON）
        </a>
      </details>
    </>
  );
}
export default function Federated() {
  const [report, setReport] = useState<Report>(),
    [error, setError] = useState(""),
    [version, setVersion] = useState(0);
  useEffect(() => {
    document.title = "LumiRead · 联邦学习实验";
    const abort = new AbortController();
    setError("");
    api<Report>("/federated", { signal: abort.signal })
      .then((data) => {
        if (
          data.schema_version !== 1 ||
          data.status !== "complete" ||
          !data.runs?.length ||
          data.runs.some(
            (r) => !r.rounds?.some((row) => row.round === r.best_round),
          ) ||
          !data.runs.some((r) => r.seed === data.selected?.seed)
        )
          throw new Error("训练报告缺少已完成运行的记录。");
        if (!abort.signal.aborted) setReport(data);
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(message(e));
      });
    return () => abort.abort();
  }, [version]);
  return (
    <div className="fed-shell">
      <header className="demo-mast">
        <div className="demo-mast-inner">
          <a className="demo-brand" href="/showcase">
            <span className="book" aria-hidden="true">
              <i />
              <i />
            </span>
            LumiRead
          </a>
          <nav aria-label="站点导航">
            <a href="/showcase">产品展示</a>
            <a href="/app">家庭学习手册 ↗</a>
          </nav>
        </div>
      </header>
      <main className="fed-main">
        {report ? (
          <StudyPage report={report} />
        ) : error ? (
          <p role="alert" className="error">
            {error}{" "}
            <button onClick={() => setVersion((v) => v + 1)}>
              重新读取训练报告
            </button>
          </p>
        ) : (
          <p role="status">正在读取真实训练记录…</p>
        )}
      </main>
    </div>
  );
}

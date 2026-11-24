import { useRef, useState } from "react";
import { api, json, message, type Item } from "../api";
import { skills } from "./data";

export function Guidance({ item }: { item: Item }) {
  const [step, setStep] = useState<number | null>(null);
  const hints = item.hints.filter(Boolean);
  const parts = [...hints, ...(item.explanation ? [item.explanation] : [])];
  if (!parts.length) return null;
  if (step === null)
    return (
      <button className="link" onClick={() => setStep(0)}>
        小鹿分步讲解
      </button>
    );
  const full = step === hints.length;
  return (
    <section className="fawn-guide" aria-label="小鹿分步讲解">
      <img
        src="/products/fawn.webp"
        alt="一只小鹿低头看着摊开的练习本"
        width="138"
        height="138"
      />
      <div>
        <strong>
          小鹿讲题{" "}
          <span>
            {" "}
            / {full ? "完整解析" : `提示 ${step + 1} · 共 ${hints.length} 步`}
          </span>
        </strong>
        <p aria-live="polite">{parts[step]}</p>
        {full && item.reference_answer && (
          <p>
            参考答案　<b>{item.reference_answer}</b>
          </p>
        )}
        <div className="actions">
          <button
            className="outline"
            disabled={step === 0}
            onClick={() => setStep(step - 1)}
          >
            上一步
          </button>
          {step + 1 < parts.length && (
            <button onClick={() => setStep(step + 1)}>
              {step + 1 === hints.length ? "查看解析" : "下一步"}
            </button>
          )}
          <button className="link" onClick={() => setStep(null)}>
            收起
          </button>
        </div>
      </div>
    </section>
  );
}

export function Question({
  item,
  number,
  learner,
  archived = false,
  onUpdate,
}: {
  item: Item;
  number: number;
  learner: string;
  archived?: boolean;
  onUpdate?: () => void;
}) {
  const [editing, setEditing] = useState(false),
    [question, setQuestion] = useState(item.question),
    [answer, setAnswer] = useState(item.student_answer);
  const [busy, setBusy] = useState(false),
    [saved, setSaved] = useState(archived),
    [note, setNote] = useState(""),
    [error, setError] = useState("");
  const pending = useRef(false);
  async function submit(kind: "review" | "archive") {
    if (!item.id || pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    setNote("");
    try {
      if (kind === "archive") {
        await api(
          `/learners/${encodeURIComponent(learner)}/mistakes/${encodeURIComponent(item.id)}`,
          { method: "PUT" },
        );
        setSaved(true);
        setNote("已收藏到历史错题。");
      } else {
        const updated = await api<Item | { job_id: string }>(
          `/questions/${encodeURIComponent(item.id)}/review`,
          json("PATCH", {
            question: question.trim(),
            student_answer: answer.trim(),
            revision: item.revision,
          }),
        );
        setEditing(false);
        setNote(
          "job_id" in updated
            ? "订正已提交，正在重新判分。"
            : "订正已完成，判分已更新。",
        );
      }
      onUpdate?.();
    } catch (e) {
      setError(message(e));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <section className="item">
      <div className="item-top">
        <b>第 {number} 题</b>
        <span className={"verdict " + item.verdict}>
          {item.verdict === "correct"
            ? "✓ 正确"
            : item.verdict === "incorrect"
              ? "× 有误"
              : "? 待复核"}
        </span>
      </div>
      <h4>{item.question}</h4>
      <p>
        作答　<strong>{item.student_answer || "未辨认"}</strong>
      </p>
      <p className="muted">
        {skills[item.skill] || item.skill}
        {item.verdict === "needs_review" ? " · " + item.review_reason : ""}
      </p>
      {item.verdict !== "needs_review" &&
        item.reference_answer &&
        !item.explanation && <p>参考答案　{item.reference_answer}</p>}
      <Guidance item={item} />
      {item.id && !archived && (
        <div className="question-actions">
          <button
            className="outline"
            aria-expanded={editing}
            disabled={busy}
            onClick={() => {
              setEditing(!editing);
              setQuestion(item.question);
              setAnswer(item.student_answer);
              setError("");
            }}
          >
            对照原图订正
          </button>
          {item.verdict === "incorrect" && (
            <button
              className="outline"
              disabled={saved || busy}
              onClick={() => submit("archive")}
            >
              {saved ? "已收藏" : "收藏错题"}
            </button>
          )}
        </div>
      )}
      {editing && (
        <form
          className="review-form"
          onSubmit={(e) => {
            e.preventDefault();
            void submit("review");
          }}
        >
          <label>
            订正题干
            <textarea
              required
              maxLength={2500}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
          </label>
          <label>
            订正学生答案
            <input
              required
              maxLength={500}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
            />
          </label>
          <button disabled={busy || !question.trim() || !answer.trim()}>
            提交重新判分
          </button>
        </form>
      )}
      {note && (
        <p role="status" className="inline-note">
          {note}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}

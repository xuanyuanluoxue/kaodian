import type { Question, QuestionType } from "../../types";
import { hasAnswer } from "./helpers";

/* 题目导航：底部上一题 / 标记 / 下一题 / 交卷，以及侧栏题号网格。 */

interface NavProps {
  questions: Question[];
  index: number;
  responses: Record<string, unknown>;
  flagged: Record<string, boolean>;
  byId: Record<string, QuestionType>;
  submitting: boolean;
  onGo: (index: number) => void;
  onToggleFlag: (qid: string) => void;
  onSubmit: () => void;
}

export function QuizNav({
  questions,
  index,
  flagged,
  submitting,
  onGo,
  onToggleFlag,
  onSubmit,
}: NavProps) {
  const current = questions[index];
  const last = index >= questions.length - 1;
  return (
    <div className="quiz-nav">
      <button className="btn btn-ghost" onClick={() => onGo(index - 1)} disabled={index === 0}>
        ← 上一题
      </button>
      <button
        className="btn btn-ghost"
        aria-pressed={!!current && !!flagged[current.id]}
        onClick={() => current && onToggleFlag(current.id)}
      >
        {current && flagged[current.id] ? "★ 已标记" : "☆ 标记"}
      </button>
      {!last ? (
        <button className="btn" onClick={() => onGo(index + 1)}>
          下一题 →
        </button>
      ) : (
        <button className="btn btn-primary" onClick={onSubmit} disabled={submitting}>
          {submitting ? "交卷中…" : "交卷"}
        </button>
      )}
    </div>
  );
}

interface RailProps extends Omit<NavProps, "onToggleFlag"> {
  answeredCount: number;
  paused: boolean;
}

export function QuizRail({
  questions,
  index,
  responses,
  flagged,
  byId,
  submitting,
  answeredCount,
  paused,
  onGo,
  onSubmit,
}: RailProps) {
  const current = questions[index];
  const percent = questions.length ? Math.round((answeredCount / questions.length) * 100) : 0;
  return (
    <>
      <div className="progress-row">
        <span>
          已答 {answeredCount} / {questions.length}
        </span>
        <span className="muted small">{percent}%</span>
      </div>
      <div className="q-grid" role="group" aria-label="题号导航">
        {questions.map((item, i) => {
          const done = hasAnswer(byId[item.type]?.input, responses[item.id]);
          return (
            <button
              key={item.id}
              type="button"
              className={`q-cell ${i === index ? "current" : ""} ${done ? "done" : ""} ${
                flagged[item.id] ? "flagged" : ""
              }`}
              aria-label={`第 ${i + 1} 题${done ? "，已答" : ""}`}
              aria-current={i === index ? "step" : undefined}
              onClick={() => onGo(i)}
            >
              {i + 1}
            </button>
          );
        })}
      </div>
      {current && (
        <div className="rail-code">
          <span className="muted small">当前考点</span>
          <b>{current.outline_code}</b>
          <p className="muted small">{current.tags.join(" · ")}</p>
        </div>
      )}
      <button
        className="btn btn-primary btn-block"
        onClick={onSubmit}
        disabled={submitting}
        aria-busy={submitting}
      >
        {submitting ? "交卷中…" : "交卷"}
      </button>
      <p className="hint">{paused ? "计时已暂停，点上面的「继续」恢复。" : "切到别的标签页会自动暂停计时。"}</p>
    </>
  );
}

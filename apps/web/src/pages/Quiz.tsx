import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { errorText } from "../lib/format";
import { LETTERS } from "../types";
import { AgentStrip } from "./quiz/AgentStrip";
import { QuestionView } from "./quiz/QuestionView";
import { QuizNav, QuizRail } from "./quiz/QuizNav";
import { QuizTimer } from "./quiz/QuizTimer";
import { useQuizSession } from "./quiz/useQuizSession";

/* 只做编排：状态、计时、草稿都在 useQuizSession，渲染拆到子组件。 */
export function QuizPage() {
  const { quizId } = useParams();
  const s = useQuizSession(quizId);
  const {
    attempt,
    q,
    index,
    questions,
    byId,
    practice,
    go,
    submit,
    reveal,
    toggleOption,
    toggleFlag,
    togglePause,
    responses,
    flagged,
    selfGrades,
    submitting,
    error,
    setError,
    clock,
    limit,
    paused,
    answeredCount,
    latestNote,
    sendHelp,
  } = s;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      // 输入 / 可编辑区域自己处理按键
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target?.isContentEditable) {
        return;
      }
      // 按钮上的 Space / Enter 是原生点击，不抢
      if (tag === "BUTTON" && (e.key === " " || e.key === "Enter")) return;
      const question = q;
      if (!question) return;
      const meta = byId[question.type];
      if (/^[1-8]$/.test(e.key)) {
        const n = Number(e.key) - 1;
        if (meta?.input === "judge") {
          if (n < 2) toggleOption(question, n === 0 ? "A" : "B");
        } else if (meta?.input === "choice") {
          if (question.options && n < question.options.length) toggleOption(question, LETTERS[n]);
        }
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (index < questions.length - 1) go(index + 1);
        else void submit();
      } else if (e.key === "ArrowLeft") {
        go(index - 1);
      } else if (e.key === "ArrowRight") {
        go(index + 1);
      } else if (e.key.toLowerCase() === "f") {
        toggleFlag(question.id);
      } else if (e.key === " ") {
        e.preventDefault();
        togglePause();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [q, index, questions.length, byId, go, submit, toggleOption, toggleFlag, togglePause]);

  if (error && !attempt) {
    return (
      <div className="page">
        <div className="alert">{error}</div>
      </div>
    );
  }

  if (!attempt || !q) {
    return (
      <div className="page">
        <p className="muted">正在开始计时…</p>
      </div>
    );
  }

  const meta = byId[q.type];
  const group = q.group_id
    ? (attempt.quiz.groups || []).find((g) => g.id === q.group_id)
    : undefined;

  return (
    <div className="quiz-shell">
      <main className="quiz-main">
        {attempt.quiz.agent_session_id && (
          <AgentStrip
            note={latestNote?.body ?? undefined}
            onSend={async (text) => {
              try {
                return await sendHelp(text);
              } catch (e) {
                setError(errorText(e));
                return false;
              }
            }}
          />
        )}

        <div className="quiz-head">
          <div>
            <p className="eyebrow">
              {attempt.quiz.mode === "exam" ? "考试模式" : "练习模式"} · {s.label(q.type)}
            </p>
            <h1>{attempt.quiz.title}</h1>
          </div>
          <div className="quiz-head-meta">
            <span className="code-chip">{q.outline_code}</span>
            <span className="muted small">
              {index + 1} / {questions.length}
            </span>
          </div>
        </div>

        {error && <div className="alert">{error}</div>}

        <QuestionView
          question={q}
          group={group}
          meta={meta}
          response={responses[q.id]}
          selfGrade={selfGrades[q.id] || []}
          revealed={s.revealed.has(q.id)}
          practice={practice}
          onResponse={(value) => s.setResponse(q.id, value)}
          onToggleOption={(letter) => toggleOption(q, letter)}
          onReveal={() => reveal(q.id)}
          onToggleSelfGrade={(pointIndex) => s.toggleSelfGrade(q.id, pointIndex)}
          onEnter={() => (practice ? reveal(q.id) : go(index + 1))}
        />

        <QuizNav
          questions={questions}
          index={index}
          responses={responses}
          flagged={flagged}
          byId={byId}
          submitting={submitting}
          onGo={go}
          onToggleFlag={toggleFlag}
          onSubmit={() => void submit()}
        />
        <p className="kbd-hint">
          键盘：<kbd>1</kbd>–<kbd>4</kbd> 选项 · <kbd>Enter</kbd> 下一题 · <kbd>F</kbd> 标记 ·{" "}
          <kbd>Space</kbd> 暂停
        </p>
      </main>

      <aside className="rail quiz-rail">
        <QuizTimer clock={clock} limit={limit} paused={paused} onTogglePause={togglePause} />
        <QuizRail
          questions={questions}
          index={index}
          responses={responses}
          flagged={flagged}
          byId={byId}
          submitting={submitting}
          answeredCount={answeredCount}
          paused={paused}
          onGo={go}
          onSubmit={() => void submit()}
        />
      </aside>
    </div>
  );
}

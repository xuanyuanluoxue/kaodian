import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { MathText } from "../components/MathText";
import { LETTERS, TYPE_LABEL } from "../types";
import type { AgentEvent, Attempt, Question } from "../types";

function mmss(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function normalize(value: unknown): string {
  return String(value ?? "")
    .normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/[，。；：、,.;:!?！？"'“”‘’（）()[\]【】]/g, "");
}

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const sa = new Set(a.map((x) => x.toUpperCase()));
  const sb = new Set(b.map((x) => x.toUpperCase()));
  return [...sa].every((x) => sb.has(x));
}

function localCorrect(q: Question, response: unknown): boolean | null {
  if (!q.answer) return null;
  if (q.type === "fill") {
    const accepted = q.answer.map(normalize);
    return accepted.includes(normalize(response));
  }
  if (q.type === "judge") {
    const got = Array.isArray(response) ? response[0] : response;
    return normalize(got) === normalize(q.answer[0]);
  }
  if (q.type === "single" || q.type === "multiple") {
    const got = Array.isArray(response) ? response.map(String) : [String(response)];
    return sameSet(got, q.answer);
  }
  return null;
}

function hasAnswer(q: Question, response: unknown): boolean {
  if (q.type === "short" || q.type === "calc" || q.type === "code" || q.type === "essay") {
    return typeof response === "string" && response.trim().length > 0;
  }
  if (q.type === "fill") return typeof response === "string" && response.trim().length > 0;
  return Array.isArray(response) && response.length > 0;
}

export function QuizPage() {
  const { quizId } = useParams();
  const navigate = useNavigate();
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [index, setIndex] = useState(0);
  const [responses, setResponses] = useState<Record<string, unknown>>({});
  const [selfGrades, setSelfGrades] = useState<Record<string, number[]>>({});
  const [flagged, setFlagged] = useState<Record<string, boolean>>({});
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [active, setActive] = useState(0);
  const [manualPause, setManualPause] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [idle, setIdle] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);
  const [helpOpen, setHelpOpen] = useState(false);
  const [helpText, setHelpText] = useState("");
  const [helpSent, setHelpSent] = useState(false);

  const activeRef = useRef(0);
  const pausedRef = useRef(false);
  const lastActivity = useRef(Date.now());
  const enterAt = useRef(Date.now());
  const times = useRef<Record<string, number>>({});
  const submitted = useRef(false);
  const submitRef = useRef<() => void>(() => {});
  const agentCursor = useRef(0);

  const paused = manualPause || hidden || idle;
  pausedRef.current = paused;

  const questions = attempt?.quiz.questions ?? [];
  const q = questions[index];
  const practice = attempt?.quiz.mode === "practice";
  const limit = attempt?.quiz.time_limit ?? null;
  const remaining = limit ? limit - active : null;

  useEffect(() => {
    if (!quizId) return;
    let alive = true;
    const key = `kaodian:attempt:${quizId}`;
    const saved = sessionStorage.getItem(key);
    const resume = saved
      ? api.attempt(saved).then((a) => (a.status === "active" ? a : null)).catch(() => null)
      : Promise.resolve(null);

    resume
      .then((existing) => existing ?? api.startAttempt(quizId))
      .then((a) => {
        if (!alive) return;
        sessionStorage.setItem(key, a.id);
        setAttempt(a);
        setActive(a.active_seconds);
        activeRef.current = a.active_seconds;
        enterAt.current = Date.now();
      })
      .catch((e) => setError(e instanceof ApiError ? String(e.message) : String(e)));
    return () => {
      alive = false;
    };
  }, [quizId]);

  useEffect(() => {
    if (!attempt || attempt.status !== "active") return;
    const t = setInterval(() => {
      if (pausedRef.current || document.hidden) return;
      activeRef.current += 1;
      setActive(activeRef.current);
    }, 1000);
    return () => clearInterval(t);
  }, [attempt]);

  useEffect(() => {
    const bump = () => {
      lastActivity.current = Date.now();
      setIdle(false);
    };
    const events: (keyof WindowEventMap)[] = ["keydown", "click", "scroll", "touchstart"];
    events.forEach((e) => window.addEventListener(e, bump, { passive: true } as AddEventListenerOptions));
    const t = setInterval(() => {
      if (Date.now() - lastActivity.current > 90_000) setIdle(true);
    }, 5000);
    return () => {
      events.forEach((e) => window.removeEventListener(e, bump));
      clearInterval(t);
    };
  }, []);

  useEffect(() => {
    const onVis = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", onVis);
    onVis();
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  useEffect(() => {
    if (!attempt || attempt.status !== "active") return;
    const t = setInterval(() => {
      api.patchAttempt(attempt.id, { active_seconds: activeRef.current }).catch(() => {});
    }, 15_000);
    return () => clearInterval(t);
  }, [attempt]);

  useEffect(() => {
    const sid = attempt?.quiz.agent_session_id;
    if (!sid) return;
    let alive = true;
    const load = () => {
      api
        .agentFeed(sid, agentCursor.current)
        .then((list) => {
          if (!alive || !list.length) return;
          agentCursor.current = list[list.length - 1].id;
          setAgentEvents((prev) => [...prev, ...list]);
        })
        .catch(() => {});
    };
    load();
    const t = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [attempt?.quiz.agent_session_id]);

  const go = useCallback(
    (next: number) => {
      const current = questions[index];
      if (current) {
        times.current[current.id] =
          (times.current[current.id] || 0) + Math.max(0, Math.round((Date.now() - enterAt.current) / 1000));
      }
      enterAt.current = Date.now();
      setIndex(Math.max(0, Math.min(next, questions.length - 1)));
    },
    [index, questions],
  );

  const setResponse = (qid: string, value: unknown) => {
    setResponses((prev) => ({ ...prev, [qid]: value }));
  };

  const reveal = (qid: string) => setRevealed((prev) => new Set(prev).add(qid));

  function toggleOption(question: Question, letter: string) {
    if (question.type === "single" || question.type === "judge" || question.type === "fill") {
      const value = question.type === "judge" ? [letter === "A" ? "true" : "false"] : [letter];
      setResponse(question.id, value);
      if (practice) reveal(question.id);
      return;
    }
    if (question.type === "multiple") {
      const current = Array.isArray(responses[question.id]) ? (responses[question.id] as string[]) : [];
      const next = current.includes(letter) ? current.filter((x) => x !== letter) : [...current, letter];
      setResponse(question.id, next);
      if (practice && revealed.has(question.id)) {
        // 改答案后收起批改，等重新核对
        setRevealed((prev) => {
          const copy = new Set(prev);
          copy.delete(question.id);
          return copy;
        });
      }
    }
  }

  function toggleSelfGrade(qid: string, pointIndex: number) {
    const current = selfGrades[qid] || [];
    const next = current.includes(pointIndex) ? current.filter((x) => x !== pointIndex) : [...current, pointIndex];
    setSelfGrades((prev) => ({ ...prev, [qid]: next }));
  }

  async function requestHelp() {
    if (!attempt || !q || !helpText.trim()) return;
    const spent = times.current[q.id] || 0;
    try {
      await api.sendHelp(
        attempt.id,
        q.id,
        `${helpText.trim()}\n\n[${q.outline_code} · ${TYPE_LABEL[q.type]} · 本题已用 ${spent}s]`,
      );
      setHelpSent(true);
      setHelpText("");
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : String(e));
    }
  }

  const submit = useCallback(async () => {
    if (!attempt || submitting || submitted.current) return;
    const unanswered = questions.filter((item) => !hasAnswer(item, responses[item.id])).length;
    if (unanswered > 0 && !window.confirm(`还有 ${unanswered} 题没有作答，确定交卷？`)) return;

    setSubmitting(true);
    setError("");
    const current = questions[index];
    if (current) {
      times.current[current.id] =
        (times.current[current.id] || 0) + Math.max(0, Math.round((Date.now() - enterAt.current) / 1000));
    }
    try {
      await api.submitAttempt(attempt.id, {
        active_seconds: activeRef.current,
        answers: questions.map((item) => ({
          question_id: item.id,
          response: responses[item.id] ?? null,
          time_spent: times.current[item.id] || 0,
          flagged: !!flagged[item.id],
          self_grade: selfGrades[item.id] ?? null,
        })),
      });
      submitted.current = true;
      sessionStorage.removeItem(`kaodian:attempt:${quizId}`);
      navigate(`/result/${attempt.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : String(e));
      setSubmitting(false);
    }
  }, [attempt, questions, responses, selfGrades, flagged, index, submitting, navigate]);

  submitRef.current = submit;

  useEffect(() => {
    if (remaining !== null && remaining <= 0 && !submitted.current) submitRef.current();
  }, [remaining]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const question = questions[index];
      if (!question) return;
      if (/^[1-8]$/.test(e.key)) {
        const n = Number(e.key) - 1;
        if (question.type === "judge") {
          if (n < 2) toggleOption(question, n === 0 ? "A" : "B");
        } else if (question.type === "single" || question.type === "multiple") {
          if (question.options && n < question.options.length) toggleOption(question, LETTERS[n]);
        }
      } else if (e.key === "Enter") {
        if (index < questions.length - 1) go(index + 1);
        else submitRef.current();
      } else if (e.key === "ArrowLeft") {
        go(index - 1);
      } else if (e.key === "ArrowRight") {
        go(index + 1);
      } else if (e.key.toLowerCase() === "f") {
        setFlagged((prev) => ({ ...prev, [question.id]: !prev[question.id] }));
      } else if (e.key === " ") {
        e.preventDefault();
        setManualPause((p) => !p);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [questions, index, go, responses, revealed, practice]);

  const latestNote = useMemo(
    () => [...agentEvents].reverse().find((e) => e.kind === "note"),
    [agentEvents],
  );

  const answeredCount = useMemo(
    () => questions.filter((item) => hasAnswer(item, responses[item.id])).length,
    [questions, responses, selfGrades],
  );

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

  const correct = practice ? localCorrect(q, responses[q.id]) : null;
  const isRevealed = practice && (revealed.has(q.id) || (correct !== null && correct));
  const subjective = ["short", "calc", "code", "essay"].includes(q.type);
  const rubric = q.rubric || [];
  const selfScore = (selfGrades[q.id] || []).reduce((sum, i) => sum + (rubric[i]?.score || 0), 0);
  const optionValues =
    q.type === "judge" ? ["true", "false"] : (q.options || []).map((_, i) => LETTERS[i]);

  return (
    <div className="quiz-shell">
      <main className="quiz-main">
        {attempt.quiz.agent_session_id && (
          <>
            <div className="agent-strip">
              <span className="agent-badge">Agent</span>
              <p>
                {latestNote?.body ||
                  "在对话里让 Agent 出题；需要提示就点右边的「卡住了」。"}
              </p>
              <button
                className="btn btn-ghost agent-help-btn"
                onClick={() => {
                  setHelpOpen((v) => !v);
                  setHelpSent(false);
                }}
              >
                {helpOpen ? "收起" : "卡住了"}
              </button>
            </div>
            {helpOpen && (
              <div className="help-box">
                <textarea
                  value={helpText}
                  onChange={(e) => setHelpText(e.target.value)}
                  placeholder="哪一步卡住了？Agent 会看到题目编号、本题用时和你的描述。"
                  rows={3}
                />
                <div className="help-actions">
                  <span className="muted small">
                    {helpSent ? "已发送，Agent 会在对话里看到。" : "不会自动重试，发送后继续答下一题即可。"}
                  </span>
                  <button
                    className="btn btn-primary"
                    onClick={requestHelp}
                    disabled={!helpText.trim() || helpSent}
                  >
                    {helpSent ? "已发送" : "发送给 Agent"}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
        <div className="quiz-head">
          <div>
            <p className="eyebrow">
              {attempt.quiz.mode === "exam" ? "考试模式" : "练习模式"} · {TYPE_LABEL[q.type]}
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

        <article className="question-card">
          <div className="question-stem">
            <MathText text={q.stem} />
          </div>

          {q.type === "fill" && (
            <input
              className="answer-input"
              placeholder="填答案，回车下一题"
              value={typeof responses[q.id] === "string" ? (responses[q.id] as string) : ""}
              onChange={(e) => setResponse(q.id, e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  if (practice) reveal(q.id);
                  else if (index < questions.length - 1) go(index + 1);
                }
              }}
            />
          )}

          {q.type === "judge" && (
            <div className="options judge-options">
              {["对", "错"].map((label, i) => {
                const value = optionValues[i];
                const picked = Array.isArray(responses[q.id]) && (responses[q.id] as string[])[0] === value;
                const showCorrect = isRevealed && q.answer?.[0] === value;
                const showWrong = isRevealed && picked && q.answer?.[0] !== value;
                return (
                  <button
                    key={value}
                    className={`option ${picked ? "picked" : ""} ${showCorrect ? "correct" : ""} ${showWrong ? "wrong" : ""}`}
                    onClick={() => toggleOption(q, i === 0 ? "A" : "B")}
                  >
                    <span className="option-key">{i === 0 ? "1" : "2"}</span>
                    {label}
                  </button>
                );
              })}
            </div>
          )}

          {q.options && q.type !== "judge" && (
            <div className="options">
              {q.options.map((opt, i) => {
                const letter = LETTERS[i];
                const picked = Array.isArray(responses[q.id]) && (responses[q.id] as string[]).includes(letter);
                const showCorrect = isRevealed && !!q.answer?.includes(letter);
                const showWrong = isRevealed && picked && !q.answer?.includes(letter);
                return (
                  <button
                    key={letter}
                    className={`option ${picked ? "picked" : ""} ${showCorrect ? "correct" : ""} ${showWrong ? "wrong" : ""}`}
                    onClick={() => toggleOption(q, letter)}
                  >
                    <span className="option-key">{letter}</span>
                    <span>
                      <MathText text={opt} />
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {practice && (q.type === "multiple" || q.type === "fill") && !revealed.has(q.id) && (
            <button className="btn btn-ghost check-btn" onClick={() => reveal(q.id)}>
              核对本题
            </button>
          )}

          {subjective && (
            <>
              <div className="answer-box">
                <label htmlFor={`ans-${q.id}`}>
                  你的解答 <span className="muted small">· Agent 会读这段来评分</span>
                </label>
                <textarea
                  id={`ans-${q.id}`}
                  rows={5}
                  value={typeof responses[q.id] === "string" ? (responses[q.id] as string) : ""}
                  onChange={(e) => setResponse(q.id, e.target.value)}
                  placeholder={
                    q.type === "code"
                      ? "贴出你的代码；写清思路和边界情况。"
                      : q.type === "calc"
                        ? "写出关键步骤和最终结果，公式可以用 $...$。"
                        : "分点写：定义 / 要点 / 结论。"
                  }
                />
              </div>
              <div className="self-grade">
              <div className="self-grade-head">
                <b>自评</b>
                <span className="muted small">可选，供 Agent 参考</span>
                <span className="self-score">
                  {selfScore} / {q.score}
                </span>
              </div>
              <ul>
                {rubric.map((point, i) => (
                  <li key={i}>
                    <label>
                      <input
                        type="checkbox"
                        checked={(selfGrades[q.id] || []).includes(i)}
                        onChange={() => toggleSelfGrade(q.id, i)}
                      />
                      <span>{point.point}</span>
                      <b>{point.score} 分</b>
                    </label>
                  </li>
                ))}
              </ul>
              <details>
                <summary>参考答案</summary>
                <pre className="reference">{q.reference_answer}</pre>
              </details>
              </div>
            </>
          )}

          {practice && isRevealed && (
            <div className={`feedback ${correct ? "ok" : "bad"}`}>
              <b>{correct ? "答对了" : "答错了"}</b>
              <p>
                <MathText text={q.explanation || ""} />
              </p>
              {q.reference_answer && (
                <details>
                  <summary>参考答案</summary>
                  <pre className="reference">{q.reference_answer}</pre>
                </details>
              )}
            </div>
          )}
        </article>

        <div className="quiz-nav">
          <button className="btn btn-ghost" onClick={() => go(index - 1)} disabled={index === 0}>
            ← 上一题
          </button>
          <button className="btn btn-ghost" onClick={() => setFlagged((p) => ({ ...p, [q.id]: !p[q.id] }))}>
            {flagged[q.id] ? "★ 已标记" : "☆ 标记"}
          </button>
          {index < questions.length - 1 ? (
            <button className="btn" onClick={() => go(index + 1)}>
              下一题 →
            </button>
          ) : (
            <button className="btn btn-primary" onClick={submit} disabled={submitting}>
              {submitting ? "交卷中…" : "交卷"}
            </button>
          )}
        </div>
        <p className="kbd-hint">
          键盘：<kbd>1</kbd>–<kbd>4</kbd> 选项 · <kbd>Enter</kbd> 下一题 · <kbd>F</kbd> 标记 ·{" "}
          <kbd>Space</kbd> 暂停
        </p>
      </main>

      <aside className="rail quiz-rail">
        <div className={`timer ${paused ? "paused" : ""}`}>
          <span className="timer-label">{paused ? "已暂停" : limit ? "剩余" : "已用"}</span>
          <b>{limit ? mmss(remaining ?? 0) : mmss(active)}</b>
          <button className="link-btn" onClick={() => setManualPause((p) => !p)}>
            {paused ? "继续" : "暂停"}
          </button>
        </div>
        <div className="progress-row">
          <span>
            已答 {answeredCount} / {questions.length}
          </span>
          <span className="muted small">{Math.round((answeredCount / questions.length) * 100)}%</span>
        </div>
        <div className="q-grid">
          {questions.map((item, i) => (
            <button
              key={item.id}
              className={`q-cell ${i === index ? "current" : ""} ${
                hasAnswer(item, responses[item.id]) ? "done" : ""
              } ${flagged[item.id] ? "flagged" : ""}`}
              onClick={() => go(i)}
            >
              {i + 1}
            </button>
          ))}
        </div>
        <div className="rail-code">
          <span className="muted small">当前考点</span>
          <b>{q.outline_code}</b>
          <p className="muted small">{q.tags.join(" · ")}</p>
        </div>
        <button className="btn btn-primary btn-block" onClick={submit} disabled={submitting}>
          {submitting ? "交卷中…" : "交卷"}
        </button>
        <p className="hint">切到别的标签页会自动暂停计时。</p>
      </aside>
    </div>
  );
}
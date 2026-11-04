import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { GroupMaterial } from "../components/GroupMaterial";
import { MathText } from "../components/MathText";
import { QuestionMedia } from "../components/QuestionMedia";
import { errorText, formatDuration, percent } from "../lib/format";
import { useQuestionTypes } from "../lib/useQuestionTypes";
import type { Attempt, ResultItem } from "../types";

function answerText(item: ResultItem, input?: string): string {
  const { response } = item;
  if (input === "judge") {
    const v = Array.isArray(response) ? response[0] : response;
    if (v === "true") return "对";
    if (v === "false") return "错";
    return "未作答";
  }
  if (typeof response === "string") return response.trim() ? response : "未作答";
  if (Array.isArray(response)) return response.length ? response.join("") : "未作答";
  return response == null ? "未作答" : String(response);
}

function correctText(item: ResultItem, input?: string): string {
  const a = item.question.answer;
  if (!a) return "见参考答案";
  if (input === "judge") return a[0] === "true" ? "对" : "错";
  return a.flat().join("");
}

export function Result() {
  const { attemptId } = useParams();
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const { byId, label } = useQuestionTypes();

  useEffect(() => {
    if (!attemptId) return;
    api
      .attempt(attemptId)
      .then(setAttempt)
      .catch((e) => setError(errorText(e)));
  }, [attemptId]);

  useEffect(() => {
    if (!attemptId || attempt?.grading_status !== "pending") return;
    const t = setInterval(() => {
      api.attempt(attemptId).then(setAttempt).catch(() => {});
    }, 5000);
    return () => clearInterval(t);
  }, [attemptId, attempt?.grading_status]);

  if (error) return <div className="page"><div className="alert">{error}</div></div>;
  if (!attempt) return <div className="page"><p className="muted">正在读取结果…</p></div>;

  const results = attempt.results || [];

  async function copySummary() {
    const lines = [
      `【考点】${attempt!.quiz.title}`,
      `得分 ${attempt!.score}/${attempt!.max_score}，用时 ${formatDuration(attempt!.active_seconds)}`,
      attempt!.weak?.length ? `薄弱：${attempt!.weak.map((w) => `${w.code}×${w.wrong}`).join("、")}` : "薄弱：无",
      "逐题：",
      ...results.map((r, i) => {
        const mark = r.correct === true ? "✓" : r.correct === false ? "×" : "自评";
        return `${i + 1}. ${r.question.outline_code} ${mark} ${r.score}/${r.max_score}`;
      }),
    ];
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("复制失败，请手动选择文本");
    }
  }
  const objective = results.filter((r) => r.question.answer);
  const correctCount = objective.filter((r) => r.correct).length;
  const pct = attempt.max_score ? Math.round(((attempt.score || 0) / attempt.max_score) * 100) : 0;

  return (
    <div className="page result-page">
      <section className="score-card">
        <div className="score-main">
          <span className="eyebrow">本次得分</span>
          <b>
            {attempt.score}
            <small> / {attempt.max_score}</small>
          </b>
          <span className={`score-pct ${pct >= 60 ? "ok" : "bad"}`}>{pct}%</span>
        </div>
        <div className="score-meta">
          <div>
            <span>用时</span>
            <b>{formatDuration(attempt.active_seconds)}</b>
          </div>
          <div>
            <span>客观题正确率</span>
            <b>{percent(correctCount, objective.length)}</b>
          </div>
          <div>
            <span>题量</span>
            <b>{results.length}</b>
          </div>
        </div>
      </section>

      {attempt.grading_status === "pending" && (
        <div className="grading-banner">
          <div>
            <b>主观题待 Agent 评分</b>
            <p className="muted small">
              你的答案已经写入数据库，我会读取并写回分数；页面每 5 秒自动刷新一次。
            </p>
          </div>
          <button className="btn btn-ghost" onClick={() => api.attempt(attemptId!).then(setAttempt)}>
            刷新评分
          </button>
        </div>
      )}

      {attempt.quiz.agent_session_id && (
        <div className="sync-badge">
          结果已写入 <code>{attempt.quiz.agent_session_id}</code>，Agent 可以直接读取这次作答。
        </div>
      )}

      <div className="result-actions">
        <Link className="btn btn-primary" to="/build">
          再来一组
        </Link>
        <button className="btn btn-ghost" onClick={copySummary}>
          {copied ? "已复制" : "复制结果摘要"}
        </button>
        <Link className="btn btn-ghost" to="/">
          回到今天
        </Link>
        <Link className="btn btn-ghost" to="/review">
          看待复习
        </Link>
      </div>

      {attempt.weak && attempt.weak.length > 0 && (
        <section className="card weak-card">
          <div className="card-kicker">薄弱考点</div>
          <div className="chips">
            {attempt.weak.map((w) => {
              const subjectId =
                results.find((r) => r.question.outline_code === w.code)?.question.subject_id ||
                attempt.quiz.questions[0]?.subject_id ||
                "";
              return (
                <Link
                  key={w.code}
                  className="chip chip-code"
                  to={`/build${subjectId ? `?subject=${encodeURIComponent(subjectId)}` : ""}`}
                >
                  {w.code}
                  <span className="chip-num">{w.wrong}</span>
                </Link>
              );
            })}
          </div>
          <p className="muted small">这些编号的题已经排进复习队列，按掌握度间隔回来。</p>
        </section>
      )}

      <section className="result-list">
        <h2>逐题</h2>
        {results.map((item, i) => {
          const q = item.question;
          const ok = item.correct;
          const group = q.group_id
            ? (attempt.quiz.groups || []).find((g) => g.id === q.group_id)
            : undefined;
          return (
            <details key={q.id} className={`result-item ${ok === true ? "ok" : ok === false ? "bad" : ""}`}>
              <summary>
                <span className="result-index">{i + 1}</span>
                <span className={`result-mark ${ok === true ? "ok" : ok === false ? "bad" : "self"}`}>
                  {item.score === null ? "待评" : ok === true ? "✓" : ok === false ? "×" : "自评"}
                </span>
                <span className="result-stem">
                  <MathText text={q.stem} />
                </span>
                <span className="result-score">
                  {item.score === null ? "待评分" : `${item.score} / ${item.max_score}`}
                </span>
              </summary>
              <div className="result-body">
                <GroupMaterial group={group} collapsible />
                <p className="meta-line">
                  <span className="code-chip">{q.outline_code}</span>
                  <span className="muted small">{label(q.type)}</span>
                  <span className="muted small">用时 {item.time_spent ?? 0} 秒</span>
                </p>
                <QuestionMedia media={q.media} />
                <div className="answer-compare">
                  <div>
                    <span className="muted small">你的答案</span>
                    {byId[q.type]?.grading === "agent" ? (
                      <pre className="answer-text">{answerText(item, byId[q.type]?.input)}</pre>
                    ) : (
                      <b>{answerText(item, byId[q.type]?.input)}</b>
                    )}
                  </div>
                  <div>
                    <span className="muted small">正确答案</span>
                    <b>{correctText(item, byId[q.type]?.input)}</b>
                  </div>
                  {q.rubric && (
                    <div>
                      <span className="muted small">自评得分点</span>
                      <ul className="rubric-read">
                        {q.rubric.map((p, idx) => (
                          <li key={idx} className={(item.self_grade || []).includes(idx) ? "on" : ""}>
                            {p.point} <b>{p.score}</b>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                {item.feedback && (
                  <div className="explain agent-feedback">
                    <span className="muted small">Agent 评分意见</span>
                    <p>{item.feedback}</p>
                  </div>
                )}
                {q.explanation && (
                  <div className="explain">
                    <span className="muted small">解析</span>
                    <p><MathText text={q.explanation} /></p>
                  </div>
                )}
                {q.reference_answer && (
                  <details className="reference-block">
                    <summary>参考答案</summary>
                    <pre className="reference">{q.reference_answer}</pre>
                  </details>
                )}
              </div>
            </details>
          );
        })}
      </section>
    </div>
  );
}
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { errorText } from "../lib/format";
import { MathText } from "../components/MathText";
import type { Question, Subject } from "../types";

interface DueQuestion extends Question {
  due_date: string;
  mastery: number;
  interval_days: number;
}

export function Review() {
  const [due, setDue] = useState<DueQuestion[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([api.due(), api.subjects()])
      .then(([d, s]) => {
        setDue(d as DueQuestion[]);
        setSubjects(s);
      })
      .catch((e) => setError(errorText(e)));
  }, []);

  const grouped = useMemo(() => {
    const map = new Map<string, DueQuestion[]>();
    due.forEach((q) => map.set(q.subject_id, [...(map.get(q.subject_id) || []), q]));
    return [...map.entries()];
  }, [due]);

  async function start() {
    if (!due.length) return;
    setBusy(true);
    try {
      const quiz = await api.buildQuiz({
        title: `复习 · ${Math.min(due.length, 30)} 题`,
        mode: "practice",
        count: Math.min(due.length, 30),
        question_ids: due.slice(0, 30).map((q) => q.id),
      });
      navigate(`/quiz/${quiz.id}`);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <p className="eyebrow">复习队列</p>
        <h1>{due.length ? `${due.length} 道题到期` : "队列是空的"}</h1>
        <p className="lede">
          {due.length
            ? "按到期日和掌握度排序。答对连 3 次升一级，答错降一级。"
            : "没有到期的题。去组一套新的，错题会自动排进来。"}
        </p>
      </div>

      {error && <div className="alert">{error}</div>}

      {due.length > 0 && (
        <div className="review-actions">
          <button className="btn btn-primary" onClick={start} disabled={busy}>
            {busy ? "正在组卷…" : `开始复习（${Math.min(due.length, 30)} 题）`}
          </button>
          <span className="muted small">超过 30 题时先取前 30 道</span>
        </div>
      )}

      {grouped.map(([subjectId, list]) => {
        const subject = subjects.find((s) => s.id === subjectId);
        return (
          <section key={subjectId} className="review-group">
            <div className="section-head">
              <h2>{subject?.short || subjectId}</h2>
              <span className="muted small">{list.length} 题</span>
            </div>
            <div className="review-list">
              {list.map((q) => (
                <div key={q.id} className="review-item">
                  <div className="review-item-head">
                    <span className="code-chip">{q.outline_code}</span>
                    <span className="muted small">掌握度 {q.mastery} / 5</span>
                    <span className="muted small">间隔 {q.interval_days} 天</span>
                    <span className="muted small">到期 {q.due_date}</span>
                  </div>
                  <p>
                    <MathText text={q.stem} />
                  </p>
                </div>
              ))}
            </div>
          </section>
        );
      })}

      {!due.length && !error && (
        <div className="empty-state">
          <p>复习队列为空。</p>
          <Link to="/build" className="btn btn-primary">
            去组一套新题
          </Link>
        </div>
      )}
    </div>
  );
}
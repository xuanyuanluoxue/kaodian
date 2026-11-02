import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { Markdown } from "../components/Markdown";
import { formatDuration, percent } from "../lib/format";
import type { DailyStats, PageDetail, PageSummary, QuizSummary, Subject } from "../types";

const KIND_LABEL: Record<string, string> = {
  outline: "大纲",
  lesson: "讲义",
  daily: "任务",
  note: "笔记",
};

function dateLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

export function Console() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [pages, setPages] = useState<PageSummary[]>([]);
  const [page, setPage] = useState<PageDetail | null>(null);
  const [quizzes, setQuizzes] = useState<QuizSummary[]>([]);
  const [stats, setStats] = useState<DailyStats | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const selectedId = params.get("page");

  useEffect(() => {
    Promise.all([api.pages(), api.quizzes(8), api.today(), api.subjects()])
      .then(([p, q, s, subs]) => {
        setPages(p);
        setQuizzes(q);
        setStats(s);
        setSubjects(subs);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    const id = selectedId || pages[0]?.id;
    if (!id) return;
    let alive = true;
    api
      .page(id)
      .then((p) => alive && setPage(p))
      .catch((e) => alive && setError(e instanceof ApiError ? String(e.message) : String(e)));
    return () => {
      alive = false;
    };
  }, [selectedId, pages]);

  const subject = useMemo(
    () => subjects.find((s) => s.id === page?.subject_id),
    [subjects, page],
  );

  function select(id: string) {
    setParams({ page: id });
  }

  async function practice() {
    if (!page) return;
    setBusy(true);
    setError("");
    try {
      const session = await api.createAgentSession(`控制台 · ${page.title}`);
      const quiz = await api.buildQuiz({
        title: `${page.title} · 练习`,
        mode: "practice",
        count: 6,
        agent_session_id: session.id,
        filters: {
          subject_id: page.subject_id || "computer",
          codes: page.outline_codes,
        },
      });
      navigate(`/quiz/${quiz.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : String(e));
      setBusy(false);
    }
  }

  const answered = stats?.answered ?? 0;
  const correct = stats?.correct ?? 0;

  return (
    <div className="console-page">
      <aside className="console-side">
        <div className="console-side-head">
          <h1>控制台</h1>
          <span className="muted small">{pages.length} 页</span>
        </div>
        <p className="hint">Agent 写入的讲解与任务，按时间倒序。</p>
        <div className="console-list">
          {pages.map((item) => (
            <button
              key={item.id}
              className={`console-item ${page?.id === item.id ? "on" : ""}`}
              onClick={() => select(item.id)}
            >
              <span className={`kind-badge kind-${item.kind}`}>{KIND_LABEL[item.kind] || item.kind}</span>
              <b>{item.title}</b>
              <span className="muted small">
                {item.outline_codes.join(" · ") || "无关联考点"} · {dateLabel(item.created_at)}
              </span>
            </button>
          ))}
          {!pages.length && <p className="muted small">还没有内容。在对话里让 Agent 写一页。</p>}
        </div>
      </aside>

      <main className="console-main">
        {error && <div className="alert">{error}</div>}
        {page ? (
          <article className="lesson">
            <header className="lesson-head">
              <div className="lesson-meta">
                <span className="agent-badge">Agent 写入</span>
                <span className="muted small">{subject?.short || page.subject_id || "通用"}</span>
                <span className="muted small">{KIND_LABEL[page.kind] || page.kind}</span>
                <span className="muted small">{dateLabel(page.created_at)}</span>
              </div>
              <h1>{page.title}</h1>
              {page.summary && <p className="lede">{page.summary}</p>}
              {page.outline_codes.length > 0 && (
                <div className="chips lesson-codes">
                  {page.outline_codes.map((code) => (
                    <span key={code} className="code-chip">
                      {code}
                    </span>
                  ))}
                </div>
              )}
            </header>

            <Markdown>{page.body}</Markdown>

            <footer className="lesson-actions">
              <button className="btn btn-primary" onClick={practice} disabled={busy}>
                {busy ? "正在组卷…" : `练这一课${page.outline_codes.length ? `（${page.outline_codes.slice(0, 4).join(" / ")}${page.outline_codes.length > 4 ? "…" : ""}）` : ""}`}
              </button>
              <Link className="btn btn-ghost" to="/build">
                手动组卷
              </Link>
              <span className="muted small">练习单会关联一个 Agent 会话，卡住可以直接求助。</span>
            </footer>
          </article>
        ) : (
          <div className="empty-state">
            <p>控制台还没有页面。</p>
            <p className="muted small">在对话里说「把今天的内容写成讲义并发布」，Agent 会出现在这里。</p>
          </div>
        )}
      </main>

      <aside className="console-rail">
        <div className="card">
          <div className="card-kicker">今天</div>
          <div className="console-stat">
            <b>{formatDuration(stats?.active_seconds ?? 0)}</b>
            <span>学习时长</span>
          </div>
          <div className="console-stat-row">
            <div>
              <b>{answered}</b>
              <span>已答</span>
            </div>
            <div>
              <b>{percent(correct, answered)}</b>
              <span>正确率</span>
            </div>
            <div>
              <b>{quizzes.length}</b>
              <span>练习单</span>
            </div>
          </div>
          <Link className="link-btn" to="/review">
            看看到期复习 →
          </Link>
        </div>

        <div className="card">
          <div className="card-kicker">最近出的题</div>
          <div className="quiz-mini-list">
            {quizzes.map((q) => (
              <Link key={q.id} className="quiz-mini" to={`/quiz/${q.id}`}>
                <b>{q.title}</b>
                <span className="muted small">
                  {q.question_count} 题 · {q.mode === "exam" ? "考试" : "练习"}
                  {q.time_limit ? ` · ${Math.round(q.time_limit / 60)} 分钟` : ""}
                </span>
              </Link>
            ))}
            {!quizzes.length && <p className="muted small">还没有练习单。</p>}
          </div>
          <Link className="btn btn-ghost btn-block" to="/build">
            手动组一套
          </Link>
        </div>

        <p className="hint">
          在对话里说「按 C-08 出 6 道」或「把这一节写成讲义」，我会直接更新这个控制台。
        </p>
      </aside>
    </div>
  );
}
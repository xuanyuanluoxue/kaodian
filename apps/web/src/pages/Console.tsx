import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { Markdown } from "../components/Markdown";
import type { LibraryStats, PageDetail, PageSummary, Progress, QuizSummary, Subject } from "../types";

const KIND_LABEL: Record<string, string> = {
  outline: "大纲",
  lesson: "讲义",
  daily: "任务",
  note: "笔记",
};

function dateLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

function weekday(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("zh-CN", { weekday: "narrow" });
}

function GoalRing({ value, total }: { value: number; total: number }) {
  const pct = total > 0 ? Math.min(1, value / total) : 0;
  const c = 2 * Math.PI * 15.5;
  return (
    <svg className="goal-ring" viewBox="0 0 36 36" role="img" aria-label={`今日目标 ${Math.round(pct * 100)}%`}>
      <circle cx="18" cy="18" r="15.5" fill="none" stroke="var(--line)" strokeWidth="3" />
      <circle
        cx="18"
        cy="18"
        r="15.5"
        fill="none"
        stroke="var(--accent-solid)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={`${c * pct} ${c}`}
        transform="rotate(-90 18 18)"
      />
      <text x="18" y="20.5" textAnchor="middle" className="goal-text">
        {Math.round(pct * 100)}
      </text>
    </svg>
  );
}

export function Console() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [pages, setPages] = useState<PageSummary[]>([]);
  const [page, setPage] = useState<PageDetail | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [library, setLibrary] = useState<LibraryStats | null>(null);
  const [quizzes, setQuizzes] = useState<QuizSummary[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [completing, setCompleting] = useState(false);

  const selectedId = params.get("page");
  const reading = !!selectedId;

  useEffect(() => {
    Promise.all([api.pages(), api.progress(), api.quizzes(6), api.subjects(), api.library()])
      .then(([p, prog, q, subs, lib]) => {
        setPages(p);
        setProgress(prog);
        setQuizzes(q);
        setSubjects(subs);
        setLibrary(lib);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setPage(null);
      return;
    }
    let alive = true;
    api
      .page(selectedId)
      .then((p) => alive && setPage(p))
      .catch((e) => alive && setError(e instanceof ApiError ? String(e.message) : String(e)));
    return () => {
      alive = false;
    };
  }, [selectedId]);

  const outlinePage = pages.find((p) => p.kind === "outline");
  const lessons = useMemo(() => pages.filter((p) => p.kind !== "outline"), [pages]);
  const nextLesson = lessons.find((p) => !p.completed) || lessons[lessons.length - 1];
  const subject = useMemo(() => subjects.find((s) => s.id === page?.subject_id), [subjects, page]);

  async function practice(target?: PageDetail | PageSummary) {
    const p = target || page;
    if (!p) return;
    setBusy(true);
    setError("");
    try {
      const session = await api.createAgentSession(`控制台 · ${p.title}`);
      const quiz = await api.buildQuiz({
        title: `${p.title} · 练习`,
        mode: "practice",
        count: 6,
        agent_session_id: session.id,
        filters: { subject_id: p.subject_id || "computer", codes: p.outline_codes },
      });
      navigate(`/quiz/${quiz.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : String(e));
      setBusy(false);
    }
  }

  async function complete() {
    if (!page) return;
    setCompleting(true);
    try {
      const res = await api.completePage(page.id);
      const [fresh, prog] = await Promise.all([api.page(page.id), api.progress()]);
      setPage(fresh);
      setProgress(prog);
      setPages((prev) => prev.map((p) => (p.id === page.id ? { ...p, completed: true, xp: res.xp } : p)));
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : String(e));
    } finally {
      setCompleting(false);
    }
  }

  const goal = progress?.daily_goal_minutes ?? 30;
  const todayMinutes = progress?.today_minutes ?? 0;

  /* ---------------- 学习路径 ---------------- */

  if (!reading) {
    return (
      <div className="path-page">
        <main className="path-main">
          <header className="path-head">
            <div>
              <p className="eyebrow">学习路径</p>
              <h1>{outlinePage?.title || "第一部分 · C 语言基础语法"}</h1>
              <p className="lede">学完一个节点亮一个；答题和讲义都算进度。</p>
            </div>
            <div className="streak-pill">
              <span aria-hidden="true">🔥</span>
              <b>{progress?.streak ?? 0}</b>
              <span>天连续</span>
            </div>
          </header>

          <section className="goal-row">
            <GoalRing value={todayMinutes} total={goal} />
            <div className="goal-copy">
              <b>
                今日 {todayMinutes} / {goal} 分钟
              </b>
              <span className="muted small">
                {progress?.today_done ? "今天已经达标，可以再加一组" : `还差 ${Math.max(0, goal - todayMinutes)} 分钟`}
              </span>
            </div>
            <div className="xp-pill">
              <span aria-hidden="true">★</span> {progress?.xp ?? 0} XP
            </div>
          </section>

          {error && <div className="alert">{error}</div>}

          {outlinePage && (
            <Link className="path-outline" to={`/console?page=${outlinePage.id}`}>
              <span className="kind-badge kind-outline">大纲</span>
              <b>{outlinePage.title}</b>
              <span className="muted small">{outlinePage.outline_codes.length} 个考点 · 先看全局</span>
            </Link>
          )}

          <div className="path">
            {lessons.map((item, index) => (
              <button
                key={item.id}
                className={`path-node ${item.completed ? "done" : ""} ${item.id === nextLesson?.id ? "current" : ""}`}
                onClick={() => setParams({ page: item.id })}
              >
                <span className="path-dot">{item.completed ? "✓" : index + 1}</span>
                <span className="path-card">
                  <b>{item.title}</b>
                  <small>
                    {item.outline_codes.join(" · ") || "无关联考点"}
                    {" · "}
                    {item.completed ? "已完成" : "+10 XP"}
                  </small>
                </span>
              </button>
            ))}
            {!lessons.length && (
              <div className="empty-state">
                <p>还没有课程。</p>
                <p className="muted small">在对话里让 Agent 写第一课。</p>
              </div>
            )}
          </div>

          {nextLesson && (
            <button className="btn btn-primary continue-btn" onClick={() => setParams({ page: nextLesson.id })}>
              {nextLesson.completed ? "复习最后一课" : `继续学习：${nextLesson.title}`}
            </button>
          )}
        </main>

        <aside className="console-rail">
          <div className="card">
            <div className="card-kicker">本周</div>
            <WeekDots days={progress?.days ?? []} />
            <p className="muted small">
              {progress?.completed_pages ?? 0} / {progress?.total_pages ?? lessons.length} 节课完成
            </p>
          </div>

          <div className="card">
            <div className="card-kicker">题库</div>
            <div className="console-stat-row">
              <div>
                <b>{library?.approved ?? 0}</b>
                <span>已上架</span>
              </div>
              <div>
                <b>{library?.pending ?? 0}</b>
                <span>待审</span>
              </div>
              <div>
                <b>{library?.rejected ?? 0}</b>
                <span>已拒</span>
              </div>
            </div>
            <p className="muted small">AI 生成先入库待审；Agent 审查通过后才进入组卷。</p>
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

          <p className="hint">在对话里说「把这一节写成讲义」，新节点会出现在路径上。</p>
        </aside>
      </div>
    );
  }

  /* ---------------- 阅读 ---------------- */

  return (
    <div className="console-page">
      <aside className="console-side">
        <Link to="/console" className="back-link">
          ← 学习路径
        </Link>
        <div className="console-side-head">
          <h1>课程</h1>
          <span className="muted small">{lessons.length} 节</span>
        </div>
        <div className="console-list">
          {lessons.map((item) => (
            <button
              key={item.id}
              className={`console-item ${page?.id === item.id ? "on" : ""}`}
              onClick={() => setParams({ page: item.id })}
            >
              <span className={`kind-badge kind-${item.kind}`}>{KIND_LABEL[item.kind] || item.kind}</span>
              <b>{item.title}</b>
              <span className="muted small">
                {item.outline_codes.join(" · ")} · {dateLabel(item.created_at)}
                {item.completed ? " · ✓" : ""}
              </span>
            </button>
          ))}
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
                {page.completed && <span className="done-chip">✓ 已完成 · +{page.xp} XP</span>}
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
              {!page.completed ? (
                <button className="btn btn-primary" onClick={complete} disabled={completing}>
                  {completing ? "记录中…" : "完成本课 +10 XP"}
                </button>
              ) : (
                <Link className="btn btn-primary" to="/console">
                  回到路径
                </Link>
              )}
              <button className="btn btn-ghost" onClick={() => practice()} disabled={busy}>
                {busy ? "正在组卷…" : "练这一课"}
              </button>
              <Link className="btn btn-ghost" to="/build">
                手动组卷
              </Link>
              <span className="muted small">练习单会关联一个 Agent 会话，卡住可以直接求助。</span>
            </footer>
          </article>
        ) : (
          <div className="empty-state">
            <p>正在读取课程…</p>
          </div>
        )}
      </main>

      <aside className="console-rail">
        <div className="card">
          <div className="card-kicker">本课</div>
          <dl className="summary-list">
            <div>
              <dt>考点</dt>
              <dd>{page?.outline_codes.join(" ") || "—"}</dd>
            </div>
            <div>
              <dt>状态</dt>
              <dd>{page?.completed ? "已完成" : "未完成"}</dd>
            </div>
            <div>
              <dt>XP</dt>
              <dd>{page?.completed ? `+${page.xp}` : "+10"}</dd>
            </div>
          </dl>
          <div className="mini-goal">
            <span className="muted small">今日 {todayMinutes} / {goal} 分钟</span>
            <span className="muted small">★ {progress?.xp ?? 0} XP</span>
          </div>
        </div>

        <div className="card">
          <div className="card-kicker">最近出的题</div>
          <div className="quiz-mini-list">
            {quizzes.map((q) => (
              <Link key={q.id} className="quiz-mini" to={`/quiz/${q.id}`}>
                <b>{q.title}</b>
                <span className="muted small">
                  {q.question_count} 题 · {q.mode === "exam" ? "考试" : "练习"}
                </span>
              </Link>
            ))}
          </div>
        </div>

        <p className="hint">卡住就点答题页的「卡住了」，我会看到题目编号和本题用时。</p>
      </aside>
    </div>
  );
}

function WeekDots({ days }: { days: Progress["days"] }) {
  return (
    <div className="week-dots">
      {days.map((d) => (
        <div key={d.date} className="week-dot">
          <span className={`dot-day ${d.done ? "done" : ""}`}>{d.done ? "✓" : ""}</span>
          <small>{weekday(d.date)}</small>
        </div>
      ))}
    </div>
  );
}
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { Markdown } from "../components/Markdown";
import { CodeTerminal } from "../components/CodeTerminal";
import type { LibraryStats, PageDetail, PageSummary, Progress, QuizSummary, Subject } from "../types";

const KIND_LABEL: Record<string, string> = {
  outline: "大纲",
  lesson: "讲义",
  daily: "任务",
  note: "笔记",
};

/* ---------------- 阅读计时 ----------------
   只看被选中课程的阅读页：页面可见 + 90 秒内有操作才累计，
   每 15 秒把增量发给 /api/activity，离开时用 sendBeacon 兜底。 */

const READING_FLUSH_SECONDS = 15;
const READING_IDLE_MS = 90_000;
const READING_EVENTS = ["keydown", "click", "scroll", "touchstart", "mousemove", "pointerdown"] as const;

function postActivity(pageId: string, seconds: number) {
  if (seconds <= 0) return;
  const payload = JSON.stringify({ page_id: pageId, seconds, source: "page" });
  if (navigator.sendBeacon) {
    const blob = new Blob([payload], { type: "application/json" });
    if (navigator.sendBeacon("/api/activity", blob)) return;
  }
  fetch("/api/activity", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
    keepalive: true,
  }).catch(() => {});
}

function useReadingTimer(pageId: string | null) {
  const pending = useRef(0);
  const pageRef = useRef<string | null>(pageId);
  const lastAction = useRef(Date.now());

  // 始终按“当前页”上报；切换页面前先 flush 旧页
  const flush = useCallback(() => {
    const id = pageRef.current;
    const seconds = pending.current;
    if (!id || seconds <= 0) return;
    pending.current = 0;
    postActivity(id, seconds);
  }, []);

  useEffect(() => {
    pageRef.current = pageId;
    pending.current = 0;
    lastAction.current = Date.now();
    if (!pageId) return;

    const bump = () => {
      lastAction.current = Date.now();
    };
    const onVisibility = () => {
      if (document.hidden) flush();
      else lastAction.current = Date.now();
    };

    READING_EVENTS.forEach((event) =>
      window.addEventListener(event, bump, { passive: true } as AddEventListenerOptions),
    );
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", flush);
    window.addEventListener("beforeunload", flush);

    const timer = setInterval(() => {
      if (document.hidden || Date.now() - lastAction.current > READING_IDLE_MS) {
        flush();
        return;
      }
      pending.current += 1;
      if (pending.current >= READING_FLUSH_SECONDS) flush();
    }, 1000);

    return () => {
      clearInterval(timer);
      READING_EVENTS.forEach((event) => window.removeEventListener(event, bump));
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", flush);
      window.removeEventListener("beforeunload", flush);
      flush();
    };
  }, [pageId, flush]);
}

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
  const subjectId = params.get("subject") || "computer";
  const reading = !!selectedId;
  useReadingTimer(selectedId);

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

  const subjectPages = useMemo(
    () => pages.filter((p) => (p.subject_id || "computer") === subjectId),
    [pages, subjectId],
  );
  const outlinePage = subjectPages.find((p) => p.kind === "outline");
  const lessons = useMemo(() => subjectPages.filter((p) => p.kind !== "outline"), [subjectPages]);
  const nextLesson = lessons.find((p) => !p.completed) || lessons[lessons.length - 1];
  const pageSubject = page?.subject_id || "computer";
  const readingLessons = useMemo(
    () => pages.filter((p) => p.kind !== "outline" && (p.subject_id || "computer") === pageSubject),
    [pages, pageSubject],
  );
  const subject = useMemo(() => subjects.find((s) => s.id === page?.subject_id), [subjects, page]);
  const pathSubject = subjects.find((s) => s.id === subjectId);

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
          <div className="subject-tabs" role="tablist" aria-label="选择科目">
            {subjects.map((s) => (
              <button
                key={s.id}
                type="button"
                role="tab"
                aria-selected={s.id === subjectId}
                className={`subject-tab ${s.id === subjectId ? "active" : ""}`}
                onClick={() => setParams({ subject: s.id })}
              >
                {s.short || s.name}
              </button>
            ))}
          </div>

          <header className="path-head">
            <div>
              <p className="eyebrow">学习路径</p>
              <h1>{outlinePage?.title || `${pathSubject?.short || subjectId} · 学习路径`}</h1>
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
            <Link className="path-outline" to={`/console?subject=${subjectId}&page=${outlinePage.id}`}>
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
                onClick={() => setParams({ subject: subjectId, page: item.id })}
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
                <p>这一科目还没有课程。</p>
                <p className="muted small">在对话里让 Agent 写第一课。</p>
              </div>
            )}
          </div>

          {nextLesson && (
            <button
              className="btn btn-primary continue-btn"
              onClick={() => setParams({ subject: subjectId, page: nextLesson.id })}
            >
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
    <div className={`console-page reading${pageSubject === "computer" ? "" : " no-code"}`}>
      {pageSubject === "computer" && page && (
        <CodeTerminal key={page.lesson_key || page.id} lessonKey={page.lesson_key || "L01"} />
      )}

      <main className="console-main">
        <div className="lesson-toolbar">
          <Link to={`/console?subject=${pageSubject}`} className="back-link">
            ← 学习路径
          </Link>
          <select
            className="lesson-select"
            value={page?.id || ""}
            onChange={(e) => setParams({ subject: pageSubject, page: e.target.value })}
            aria-label="切换课程"
          >
            {readingLessons.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
                {item.completed ? " ✓" : ""}
              </option>
            ))}
          </select>
        </div>
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
                <Link className="btn btn-primary" to={`/console?subject=${pageSubject}`}>
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
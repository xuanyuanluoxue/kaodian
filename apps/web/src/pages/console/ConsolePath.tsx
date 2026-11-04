import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { LibraryStats, PageSummary, Progress, QuizSummary, Subject } from "../../types";

/* 学习路径视图：科目 tab / 今日目标 / 节点列表 / 右侧统计。 */

interface Props {
  subjects: Subject[];
  subjectsLoaded: boolean;
  subjectId: string;
  pages: PageSummary[];
  progress: Progress | null;
  library: LibraryStats | null;
  quizzes: QuizSummary[];
  error: string;
  onSelectSubject: (id: string) => void;
  onOpenPage: (pageId: string, subjectId: string) => void;
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

export function ConsolePath({
  subjects,
  subjectsLoaded,
  subjectId,
  pages,
  progress,
  library,
  quizzes,
  error,
  onSelectSubject,
  onOpenPage,
}: Props) {
  const subjectPages = useMemo(
    () => pages.filter((p) => (p.subject_id || subjects[0]?.id || "") === subjectId),
    [pages, subjectId, subjects],
  );
  const outlinePage = subjectPages.find((p) => p.kind === "outline");
  const lessons = useMemo(() => subjectPages.filter((p) => p.kind !== "outline"), [subjectPages]);
  const nextLesson = lessons.find((p) => !p.completed) || lessons[lessons.length - 1];
  const pathSubject = subjects.find((s) => s.id === subjectId);
  // subjects 加载完成前不判定“未知科目”，避免加载中被误报
  const unknownSubject =
    subjectsLoaded && subjects.length > 0 && !subjects.some((s) => s.id === subjectId);
  const goal = progress?.daily_goal_minutes ?? 30;
  const todayMinutes = progress?.today_minutes ?? 0;

  const subjectTabs = (
    <div className="subject-tabs" role="tablist" aria-label="选择科目">
      {subjects.map((s) => (
        <button
          key={s.id}
          type="button"
          role="tab"
          aria-selected={s.id === subjectId}
          className={`subject-tab ${s.id === subjectId ? "active" : ""}`}
          onClick={() => onSelectSubject(s.id)}
        >
          {s.short || s.name}
        </button>
      ))}
    </div>
  );

  if (!subjectsLoaded && !subjects.length) {
    return (
      <div className="path-page">
        <main className="path-main">
          <div className="empty-state">
            <p>正在读取科目…</p>
          </div>
        </main>
      </div>
    );
  }

  if (unknownSubject) {
    return (
      <div className="path-page">
        <main className="path-main">
          {subjectTabs}
          <div className="subject-error">
            <p className="subject-error-title">没有这个科目：{subjectId}</p>
            <p>链接可能复制时带上了多余的中文或括号。</p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => subjects[0] && onSelectSubject(subjects[0].id)}
            >
              回到 {subjects[0]?.short || "首个科目"}路径
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="path-page">
      <main className="path-main">
        {subjectTabs}

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
              onClick={() => onOpenPage(item.id, subjectId)}
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
            onClick={() => onOpenPage(nextLesson.id, subjectId)}
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

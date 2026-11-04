import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CodeTerminal } from "../../components/CodeTerminal";
import { Markdown } from "../../components/Markdown";
import type {
  PageDetail,
  PageQuestionCount,
  PageSummary,
  Progress,
  QuizSummary,
  Subject,
} from "../../types";

/* 讲义阅读视图：代码终端 / 课程切换 / 正文 / 右侧本课信息。 */

const KIND_LABEL: Record<string, string> = {
  outline: "大纲",
  lesson: "讲义",
  daily: "任务",
  note: "笔记",
};

function dateLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

/** 剪贴板不可用时退回 execCommand，保证「复制出题提示」在本地和 http 下都能用。 */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    /* 继续走兜底 */
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}

interface Props {
  page: PageDetail | null;
  pages: PageSummary[];
  subjects: Subject[];
  progress: Progress | null;
  quizzes: QuizSummary[];
  questionCount: PageQuestionCount | null;
  error: string;
  busy: boolean;
  completing: boolean;
  onSelectPage: (pageId: string) => void;
  onComplete: () => void;
  onPractice: () => void;
}

export function ConsoleReader({
  page,
  pages,
  subjects,
  progress,
  quizzes,
  questionCount,
  error,
  busy,
  completing,
  onSelectPage,
  onComplete,
  onPractice,
}: Props) {
  const pageSubject = page?.subject_id || subjects[0]?.id || "";
  const readingLessons = useMemo(
    () => pages.filter((p) => p.kind !== "outline" && (p.subject_id || subjects[0]?.id || "") === pageSubject),
    [pages, pageSubject, subjects],
  );
  const subject = useMemo(() => subjects.find((s) => s.id === page?.subject_id), [subjects, page]);
  const codeLanguage = subject?.code_language || null;
  const goal = progress?.daily_goal_minutes ?? 30;
  const todayMinutes = progress?.today_minutes ?? 0;
  const codes = questionCount?.codes?.length ? questionCount.codes : (page?.outline_codes ?? []);
  const total = questionCount?.count ?? null;
  const empty = total === 0;
  const prompt = `按 ${codes.length ? codes.join("，") : "本课考点"} 出 6 道题，难度 2，先入库 pending，题干不要与已有题重复。`;
  const [copied, setCopied] = useState<{ pageId: string; ok: boolean } | null>(null);
  const copyState = copied && copied.pageId === page?.id ? copied.ok : null;

  async function copyPrompt() {
    if (!page) return;
    setCopied({ pageId: page.id, ok: await copyText(prompt) });
  }

  return (
    <div className={`console-page reading${codeLanguage ? "" : " no-code"}`}>
      {codeLanguage && page && (
        <CodeTerminal
          key={`${pageSubject}:${page.id}`}
          subjectId={pageSubject}
          pageId={page.id}
          lessonKey={page.lesson_key || undefined}
          language={codeLanguage}
        />
      )}

      <main className="console-main">
        <div className="lesson-toolbar">
          <Link to={`/console?subject=${pageSubject}`} className="back-link">
            ← 学习路径
          </Link>
          <select
            className="lesson-select"
            value={page?.id || ""}
            onChange={(e) => onSelectPage(e.target.value)}
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
                {page.completed && (
                  <span className="done-chip">
                    ✓ 已完成 · +{page.xp} XP
                  </span>
                )}
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
                <button className="btn btn-primary" onClick={onComplete} disabled={completing}>
                  {completing ? "记录中…" : "完成本课 +10 XP"}
                </button>
              ) : (
                <Link className="btn btn-primary" to={`/console?subject=${pageSubject}`}>
                  回到路径
                </Link>
              )}
              {empty ? (
                <>
                  <button className="btn btn-ghost" disabled>
                    本课暂无题
                  </button>
                  <button className="btn btn-ghost" onClick={() => void copyPrompt()}>
                    {copyState === true ? "已复制" : copyState === false ? "复制失败" : "复制出题提示"}
                  </button>
                  <span className="muted small">在对话里让 Agent 出题，回来刷新即可</span>
                </>
              ) : (
                <>
                  <button className="btn btn-ghost" onClick={onPractice} disabled={busy}>
                    {busy ? "正在组卷…" : "练这一课"}
                  </button>
                  {total !== null && <span className="muted small">本课 {total} 题</span>}
                </>
              )}
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
            <span className="muted small">
              今日 {todayMinutes} / {goal} 分钟
            </span>
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

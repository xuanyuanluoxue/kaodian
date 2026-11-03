import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { formatDuration } from "../lib/format";
import type { DailyStats, Question, Subject } from "../types";

function accuracy(ok: number, n: number): string {
  if (!n) return "—";
  return `${Math.round((ok / n) * 100)}%`;
}

export function Today() {
  const [stats, setStats] = useState<DailyStats | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [due, setDue] = useState<Question[]>([]);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([api.subjects(), api.due()])
      .then(([subs, d]) => {
        setSubjects(subs);
        setDue(d);
      })
      .catch((e) => setError(String(e)));
  }, []);

  // 今日统计：20 秒轮询 + 回到前台立刻刷新（阅读和答题都可能在其他页面产生时间）
  useEffect(() => {
    let alive = true;
    const load = () => {
      api
        .today()
        .then((s) => alive && setStats(s))
        .catch((e) => alive && setError(String(e)));
    };
    load();
    const timer = setInterval(load, 20_000);
    const onVisibility = () => {
      if (!document.hidden) load();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      alive = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  async function startReview() {
    if (!due.length) return;
    setStarting(true);
    try {
      const quiz = await api.buildQuiz({
        title: `今日复习 · ${due.length} 题`,
        mode: "practice",
        count: Math.min(due.length, 30),
        question_ids: due.slice(0, 30).map((q) => q.id),
      });
      navigate(`/quiz/${quiz.id}`);
    } catch (e) {
      setError(String(e));
      setStarting(false);
    }
  }

  const today = new Date().toLocaleDateString("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "long",
  });

  return (
    <div className="page">
      <section className="hero">
        <div className="hero-text">
          <p className="eyebrow">{today}</p>
          <h1>今天学什么</h1>
          <p className="lede">
            在对话里让 Agent 出题，在这里作答。计时和结果会自动回传。
          </p>
        </div>
        <div className="hero-stats">
          <div className="stat">
            <b>{stats?.active_seconds ? formatDuration(stats.active_seconds) : "0 分钟"}</b>
            <span>今日投入</span>
          </div>
          <div className="stat">
            <b>
              {stats?.answered ?? 0}
              <small> 题</small>
            </b>
            <span>已作答</span>
          </div>
          <div className="stat">
            <b>{accuracy(stats?.correct ?? 0, stats?.answered ?? 0)}</b>
            <span>正确率</span>
          </div>
        </div>
      </section>

      {error && <div className="alert">{error}</div>}

      <section className="card review-card">
        <div>
          <div className="card-kicker">到期复习</div>
          {due.length ? (
            <h2>
              {due.length} 道题该回来了
              <span className="muted"> · 约 {Math.max(5, Math.ceil(due.length * 0.8))} 分钟</span>
            </h2>
          ) : (
            <h2>
              今天没有到期复习
              <span className="muted"> · 可以直接开新题</span>
            </h2>
          )}
          <p className="muted small">
            {due.length
              ? "按掌握度排的：越不熟的越靠前。先清这个，再学新的。"
              : "复习队列是空的。学完新内容、答错的题会自动排进来。"}
          </p>
        </div>
        {due.length > 0 && (
          <button className="btn btn-primary" onClick={startReview} disabled={starting}>
            {starting ? "正在组卷…" : `开始复习（${Math.min(due.length, 30)} 题）`}
          </button>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>四科</h2>
          <span className="muted small">按考纲编号组卷，题不够会提示</span>
        </div>
        <div className="subject-grid">
          {subjects.map((s) => (
            <Link key={s.id} to={`/build?subject=${s.id}`} className="subject-card">
              <div className="subject-top">
                <span className={`dot dot-${s.id}`} />
                <span className="muted small">{s.exam_score} 分</span>
              </div>
              <h3>{s.short}</h3>
              <p className="muted small">
                {s.node_count} 个考点 · 题库 {s.question_count} 题
              </p>
              <span className="subject-go">去组卷 →</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>和 Agent 一起用</h2>
        </div>
        <div className="steps">
          <div className="step">
            <span>01</span>
            <p>
              <b>对话里要题</b>
              <br />
              跟 Agent 说「按 C-08 出 10 道」，它会组好卷，把链接发你。
            </p>
          </div>
          <div className="step">
            <span>02</span>
            <p>
              <b>网页里作答</b>
              <br />
              自动计时，切走暂停。卡住点「卡住了」，Agent 能看到题目和用时。
            </p>
          </div>
          <div className="step">
            <span>03</span>
            <p>
              <b>结果回传</b>
              <br />
              交卷即写入会话，Agent 直接读结果，接着安排下一组或讲解。
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
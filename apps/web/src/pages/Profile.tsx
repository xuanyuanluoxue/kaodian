import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { errorText, formatDuration } from "../lib/format";
import type {
  Profile as ProfileData,
  ProfileDynamic,
  ProfileStatic,
  Subject,
} from "../types";

interface FormState {
  target_exam: string;
  target_date: string;
  target_score: string;
  daily_minutes: string;
  subjects: string[];
  notes: string;
  preferred_tone: string;
  preferred_examples: string;
}

function formFromStatic(value: ProfileStatic | null | undefined): FormState {
  return {
    target_exam: value?.target_exam ?? "",
    target_date: value?.target_date ?? "",
    target_score: value?.target_score == null ? "" : String(value.target_score),
    daily_minutes: value ? String(value.daily_minutes) : "30",
    subjects: value?.subjects ?? [],
    notes: value?.notes ?? "",
    preferred_tone: value?.preferred_tone ?? "",
    preferred_examples: value?.preferred_examples ?? "",
  };
}

function percentText(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

function barWidth(value: number | null): string {
  if (value == null || Number.isNaN(value) || value <= 0) return "0%";
  return `${Math.min(100, Math.round(value * 100))}%`;
}

function durationText(seconds: number): string {
  return seconds > 0 ? formatDuration(Math.round(seconds)) : "0 分钟";
}

function countdownText(dynamic: ProfileDynamic): string {
  if (dynamic.days_to_exam == null) return "设置日期";
  if (dynamic.days_to_exam < 0) return `目标日期已过 ${-dynamic.days_to_exam} 天`;
  return `距目标还有 ${dynamic.days_to_exam} 天`;
}

export function Profile() {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [subjectList, setSubjectList] = useState<Subject[]>([]);
  const [codeSubjects, setCodeSubjects] = useState<Record<string, string>>({});
  const [form, setForm] = useState<FormState>(() => formFromStatic(null));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    let alive = true;
    void Promise.allSettled([api.profile(), api.subjects(), api.outline()]).then(
      ([profileResult, subjectsResult, outlineResult]) => {
        if (!alive) return;
        const failed: string[] = [];
        if (profileResult.status === "fulfilled") {
          setProfile(profileResult.value);
          setForm(formFromStatic(profileResult.value.static));
        } else {
          failed.push(`画像（${errorText(profileResult.reason)}）`);
        }
        if (subjectsResult.status === "fulfilled") {
          setSubjectList(subjectsResult.value);
        } else {
          failed.push(`科目（${errorText(subjectsResult.reason)}）`);
        }
        if (outlineResult.status === "fulfilled") {
          const map: Record<string, string> = {};
          outlineResult.value.forEach((node) => {
            map[node.code] = node.subject_id;
          });
          setCodeSubjects(map);
        }
        setLoadError(failed.length ? `部分数据加载失败：${failed.join("；")}` : "");
        setLoading(false);
      },
    );
    return () => {
      alive = false;
    };
  }, []);

  const subjectOptions = useMemo<Pick<Subject, "id" | "name" | "short">[]>(() => {
    if (subjectList.length) return subjectList;
    return profile?.dynamic.subjects ?? [];
  }, [subjectList, profile]);

  const baseline = useMemo(() => formFromStatic(profile?.static), [profile]);
  const dirty = profile != null && JSON.stringify(form) !== JSON.stringify(baseline);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function patch<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setSaved(false);
    setSaveError("");
  }

  function toggleSubject(id: string) {
    setForm((current) => {
      const next = new Set(current.subjects);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      const ordered = subjectOptions.map((s) => s.id).filter((sid) => next.has(sid));
      current.subjects.forEach((sid) => {
        if (next.has(sid) && !ordered.includes(sid)) ordered.push(sid);
      });
      return { ...current, subjects: ordered };
    });
    setSaved(false);
    setSaveError("");
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const minutes = Number(form.daily_minutes);
    if (!form.daily_minutes.trim() || !Number.isInteger(minutes) || minutes < 1 || minutes > 600) {
      setSaveError("每日目标需在 1–600 分钟之间");
      return;
    }
    let score: number | null = null;
    if (form.target_score.trim()) {
      score = Number(form.target_score);
      if (!Number.isFinite(score) || score < 0) {
        setSaveError("目标分需是非负数字");
        return;
      }
    }
    const targetDate = form.target_date.trim();
    if (targetDate && !/^\d{4}-\d{2}-\d{2}$/.test(targetDate)) {
      setSaveError("日期格式需为 YYYY-MM-DD");
      return;
    }

    setSaving(true);
    setSaved(false);
    setSaveError("");
    try {
      const next = await api.updateProfile({
        target_exam: form.target_exam.trim() || null,
        target_date: targetDate || null,
        target_score: score,
        daily_minutes: minutes,
        subjects: form.subjects,
        notes: form.notes,
        preferred_tone: form.preferred_tone.trim(),
        preferred_examples: form.preferred_examples.trim(),
      });
      setProfile(next);
      setForm(formFromStatic(next.static));
      setSaved(true);
    } catch (error) {
      setSaveError(errorText(error));
    } finally {
      setSaving(false);
    }
  }

  const dynamic = profile?.dynamic;
  const recent = dynamic?.recent ?? [];
  const recentSeconds = recent.reduce((sum, day) => sum + day.seconds, 0);
  const recentAnswered = recent.reduce((sum, day) => sum + day.answered, 0);
  const hasRecent = recentSeconds > 0 || recentAnswered > 0;
  const maxRecent = Math.max(1, ...recent.map((day) => day.seconds));
  const todayKey = recent.length ? recent[recent.length - 1].date : "";
  const fallbackSubject = subjectOptions[0]?.id ?? "";

  return (
    <div className="page profile-page">
      <div className="page-head">
        <p className="eyebrow">画像</p>
        <h1>目标与学情</h1>
        <p className="lede">目标自己定，数据从每一次作答和阅读里来。</p>
      </div>

      {loadError && <div className="alert">{loadError}</div>}

      {loading ? (
        <p className="muted">正在加载画像…</p>
      ) : !profile || !dynamic ? (
        <div className="empty-state">
          <p>画像加载失败，稍后刷新再试。</p>
          <Link to="/" className="btn">
            回到今天
          </Link>
        </div>
      ) : (
        <>
          <section className="card profile-target">
            <div className="profile-target-main">
              <p className="card-kicker">目标考试</p>
              <h2>{profile.static.target_exam || "未设置目标"}</h2>
              <p className="profile-countdown">
                {dynamic.days_to_exam == null ? (
                  <a href="#profile-form">{countdownText(dynamic)}</a>
                ) : (
                  countdownText(dynamic)
                )}
              </p>
            </div>
            <dl className="profile-target-meta">
              <div>
                <dt>目标分</dt>
                <dd>{profile.static.target_score ?? "—"}</dd>
              </div>
              <div>
                <dt>每日目标</dt>
                <dd>{profile.static.daily_minutes} 分钟</dd>
              </div>
              <div>
                <dt>今日已学</dt>
                <dd>{dynamic.today_minutes} 分钟</dd>
              </div>
            </dl>
          </section>

          <section className="section" id="profile-form">
            <div className="section-head">
              <h2>目标设置</h2>
              <span className={dirty ? "profile-dirty" : "muted small"}>
                {dirty ? "有未保存修改" : saved ? "已保存" : "改动后记得保存"}
              </span>
            </div>
            <form className="card profile-form" onSubmit={handleSubmit}>
              <div className="profile-form-grid">
                <div className="field">
                  <label htmlFor="profile-exam">考试名称</label>
                  <input
                    id="profile-exam"
                    value={form.target_exam}
                    onChange={(e) => patch("target_exam", e.target.value)}
                    placeholder="如 2028 广东专升本"
                  />
                </div>
                <div className="field">
                  <label htmlFor="profile-date">考试日期</label>
                  <input
                    id="profile-date"
                    type="date"
                    value={form.target_date}
                    onChange={(e) => patch("target_date", e.target.value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="profile-score">目标分</label>
                  <input
                    id="profile-score"
                    type="number"
                    inputMode="decimal"
                    step="0.5"
                    min="0"
                    value={form.target_score}
                    onChange={(e) => patch("target_score", e.target.value)}
                    placeholder="如 425"
                  />
                </div>
                <div className="field">
                  <label htmlFor="profile-minutes">每日目标（分钟）</label>
                  <input
                    id="profile-minutes"
                    type="number"
                    inputMode="numeric"
                    step="1"
                    min="1"
                    max="600"
                    value={form.daily_minutes}
                    onChange={(e) => patch("daily_minutes", e.target.value)}
                  />
                </div>
                <div className="field profile-span-2">
                  <label>科目</label>
                  <div className="profile-checks" role="group" aria-label="科目多选">
                    {subjectOptions.length ? (
                      subjectOptions.map((subject) => (
                        <label key={subject.id} className="profile-check">
                          <input
                            type="checkbox"
                            checked={form.subjects.includes(subject.id)}
                            onChange={() => toggleSubject(subject.id)}
                          />
                          <span>{subject.short || subject.name}</span>
                        </label>
                      ))
                    ) : (
                      <span className="muted small">暂无科目数据。</span>
                    )}
                  </div>
                  <p className="hint">只勾选这次要准备的科目，不影响已有记录。</p>
                </div>
                <div className="field profile-span-2">
                  <label htmlFor="profile-notes">备注</label>
                  <textarea
                    id="profile-notes"
                    rows={3}
                    maxLength={2000}
                    value={form.notes}
                    onChange={(e) => patch("notes", e.target.value)}
                    placeholder="学习基础、薄弱环节、时间安排……只写学习相关的内容"
                  />
                </div>
                <div className="field">
                  <label htmlFor="profile-tone">讲解语气</label>
                  <input
                    id="profile-tone"
                    maxLength={200}
                    value={form.preferred_tone}
                    onChange={(e) => patch("preferred_tone", e.target.value)}
                    placeholder="如 直接、少废话"
                  />
                </div>
                <div className="field">
                  <label htmlFor="profile-examples">例子偏好</label>
                  <input
                    id="profile-examples"
                    maxLength={200}
                    value={form.preferred_examples}
                    onChange={(e) => patch("preferred_examples", e.target.value)}
                    placeholder="如 先具体再一般"
                  />
                </div>
              </div>

              {saveError && <div className="alert profile-form-error">{saveError}</div>}

              <div className="profile-form-actions">
                <button className="btn btn-primary" type="submit" disabled={saving || !dirty}>
                  {saving ? "保存中…" : "保存"}
                </button>
                {saved && <span className="profile-save-ok">已保存</span>}
              </div>
            </form>
          </section>

          <section className="section">
            <div className="section-head">
              <h2>学情概览</h2>
              <span className="muted small">实时统计</span>
            </div>
            <div className="profile-metrics">
              <div className="card profile-metric">
                <span>总正确率</span>
                <b>{percentText(dynamic.accuracy)}</b>
                <small>
                  {dynamic.answered ? `${dynamic.correct} / ${dynamic.answered} 题` : "还没有作答"}
                </small>
              </div>
              <div className="card profile-metric">
                <span>作答数</span>
                <b>{dynamic.answered}</b>
                <small>题</small>
              </div>
              <div className="card profile-metric">
                <span>连续天数</span>
                <b>{dynamic.streak}</b>
                <small>天</small>
              </div>
              <div className="card profile-metric">
                <span>XP</span>
                <b>{dynamic.xp}</b>
                <small>经验</small>
              </div>
              <div className="card profile-metric">
                <span>完成课数</span>
                <b>{dynamic.completed_pages}</b>
                <small>课</small>
              </div>
              <div className="card profile-metric">
                <span>到期复习</span>
                <b>{dynamic.due_reviews}</b>
                <small>题</small>
              </div>
            </div>
          </section>

          <section className="section">
            <div className="section-head">
              <h2>科目</h2>
              <span className="muted small">正确率与投入时长</span>
            </div>
            <div className="profile-subjects">
              {dynamic.subjects.map((subject) => (
                <article key={subject.id} className="card profile-subject">
                  <div className="profile-subject-head">
                    <span
                      className="dot"
                      style={{ background: subject.color || "var(--accent)" }}
                      aria-hidden="true"
                    />
                    <h3>{subject.short || subject.name}</h3>
                    <span className="profile-subject-accuracy">
                      {percentText(subject.accuracy)}
                    </span>
                  </div>
                  <div className="stat-track">
                    <span
                      className="stat-fill"
                      style={{
                        width: barWidth(subject.accuracy),
                        background: subject.color || "var(--accent)",
                      }}
                    />
                  </div>
                  <div className="profile-subject-meta muted small">
                    <span>
                      {subject.answered
                        ? `${subject.answered} 题 · ${subject.correct} 对`
                        : "暂无作答"}
                    </span>
                    <span>{durationText(subject.seconds)}</span>
                  </div>
                </article>
              ))}
            </div>
            {!dynamic.subjects.length && <p className="muted small">还没有科目数据。</p>}
          </section>

          <section className="section">
            <div className="section-head">
              <h2>薄弱考点 Top 5</h2>
              <span className="muted small">按答错次数排序</span>
            </div>
            <div className="card profile-weak">
              {dynamic.weak_codes.length ? (
                dynamic.weak_codes.map((item) => {
                  const subjectId = codeSubjects[item.code] || fallbackSubject;
                  return (
                    <Link
                      key={item.code}
                      className="profile-weak-row"
                      to={subjectId ? `/build?subject=${encodeURIComponent(subjectId)}` : "/build"}
                      title="去组卷练这个科目"
                    >
                      <span className="profile-weak-code">{item.code}</span>
                      <span className="profile-weak-title">{item.title}</span>
                      <span className="profile-weak-wrong">{item.wrong} 错</span>
                    </Link>
                  );
                })
              ) : (
                <p className="muted small">还没有错题记录，继续保持。</p>
              )}
            </div>
          </section>

          <section className="section">
            <div className="section-head">
              <h2>近 7 天</h2>
              <span className="muted small">
                {hasRecent
                  ? `共 ${durationText(recentSeconds)} · ${recentAnswered} 题`
                  : "还没有记录"}
              </span>
            </div>
            <div className="card profile-chart-card">
              {hasRecent ? (
                <div className="profile-chart" role="img" aria-label="近 7 天学习时长柱状图">
                  {recent.map((day) => {
                    const height =
                      day.seconds > 0 ? Math.max(4, Math.round((day.seconds / maxRecent) * 100)) : 0;
                    return (
                      <div key={day.date} className="profile-chart-col">
                        <div
                          className="profile-chart-track"
                          title={`${day.date} · ${durationText(day.seconds)} · ${day.answered} 题`}
                        >
                          <span
                            className={`profile-chart-bar ${
                              day.date === todayKey ? "is-today" : ""
                            }`}
                            style={{ height: `${height}%` }}
                          />
                        </div>
                        <span
                          className={`profile-chart-label ${
                            day.date === todayKey ? "is-today" : ""
                          }`}
                        >
                          {day.date.slice(5)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="muted small">近 7 天还没有学习记录，答一套题或读一节课就有了。</p>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

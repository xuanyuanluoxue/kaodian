import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { errorText, formatDuration } from "../lib/format";
import type {
  Profile as ProfileData,
  ProfileDynamic,
  ProfileStatic,
  ProfileUpdate,
  Subject,
} from "../types";

interface FormState {
  target_exam: string;
  target_date: string;
  target_score: string;
  target_school: string;
  target_major: string;
  target_region: string;
  backup_school: string;
  backup_major: string;
  exam_type: string;
  current_education: string;
  graduation_year: string;
  daily_minutes: string;
  subjects: string[];
  study_window: string;
  constraints: string;
  strengths: string;
  weaknesses: string;
  motivation: string;
  notes: string;
  preferred_tone: string;
  preferred_examples: string;
}

const FIELD_LABELS: Record<string, string> = {
  target_exam: "考试名称",
  target_date: "考试日期",
  target_score: "目标分",
  target_school: "目标院校",
  target_major: "目标专业",
  target_region: "目标地区",
  backup_school: "保底院校",
  backup_major: "保底专业",
  exam_type: "升学类型",
  current_education: "当前学历",
  graduation_year: "毕业年份",
  daily_minutes: "每日分钟",
  subjects: "科目",
  study_window: "学习时段",
  constraints: "限制",
  strengths: "优势",
  weaknesses: "薄弱点",
  motivation: "动机",
  notes: "备注",
};

function labelOf(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

function formFromStatic(value: ProfileStatic | null | undefined): FormState {
  return {
    target_exam: value?.target_exam ?? "",
    target_date: value?.target_date ?? "",
    target_score: value?.target_score == null ? "" : String(value.target_score),
    target_school: value?.target_school ?? "",
    target_major: value?.target_major ?? "",
    target_region: value?.target_region ?? "",
    backup_school: value?.backup_school ?? "",
    backup_major: value?.backup_major ?? "",
    exam_type: value?.exam_type ?? "",
    current_education: value?.current_education ?? "",
    graduation_year: value?.graduation_year == null ? "" : String(value.graduation_year),
    daily_minutes: value ? String(value.daily_minutes) : "30",
    subjects: value?.subjects ?? [],
    study_window: value?.study_window ?? "",
    constraints: value?.constraints ?? "",
    strengths: value?.strengths ?? "",
    weaknesses: value?.weaknesses ?? "",
    motivation: value?.motivation ?? "",
    notes: value?.notes ?? "",
    preferred_tone: value?.preferred_tone ?? "",
    preferred_examples: value?.preferred_examples ?? "",
  };
}

/** 只提交相对上次保存发生变化的字段，避免误覆盖其他端写入的内容。 */
function diffForm(form: FormState, baseline: FormState): ProfileUpdate {
  const body: ProfileUpdate = {};
  const text = (key: keyof FormState) => String(form[key]).trim();

  const nullable = <K extends keyof FormState>(key: K) => {
    if (String(form[key]) === String(baseline[key])) return;
    const value = String(form[key]).trim();
    // 这些字段后端接受 null；空串落库也是 null，这里传 null 更明确。
    (body as Record<string, unknown>)[key] = value || null;
  };

  if (form.target_exam !== baseline.target_exam) {
    body.target_exam = text("target_exam") || null;
  }
  if (form.target_date !== baseline.target_date) {
    body.target_date = text("target_date") || null;
  }
  if (form.target_score !== baseline.target_score) {
    const value = text("target_score");
    body.target_score = value ? Number(value) : null;
  }
  if (form.graduation_year !== baseline.graduation_year) {
    const value = text("graduation_year");
    body.graduation_year = value ? Number(value) : null;
  }
  nullable("target_school");
  nullable("target_major");
  nullable("target_region");
  nullable("backup_school");
  nullable("backup_major");
  nullable("exam_type");
  nullable("current_education");
  nullable("study_window");
  nullable("constraints");
  nullable("strengths");
  nullable("weaknesses");
  nullable("motivation");

  if (form.daily_minutes !== baseline.daily_minutes) {
    body.daily_minutes = Number(text("daily_minutes"));
  }
  if (JSON.stringify(form.subjects) !== JSON.stringify(baseline.subjects)) {
    body.subjects = [...form.subjects];
  }
  if (form.notes !== baseline.notes) {
    body.notes = form.notes.trim();
  }
  if (form.preferred_tone !== baseline.preferred_tone) {
    body.preferred_tone = form.preferred_tone.trim();
  }
  if (form.preferred_examples !== baseline.preferred_examples) {
    body.preferred_examples = form.preferred_examples.trim();
  }
  return body;
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

function summaryText(staticProfile: ProfileStatic, subjectNames: Record<string, string>): string {
  const parts: string[] = [];
  if (staticProfile.target_exam) parts.push(`考试：${staticProfile.target_exam}`);
  if (staticProfile.target_date) parts.push(`日期：${staticProfile.target_date}`);
  if (staticProfile.target_score != null) parts.push(`目标分：${staticProfile.target_score}`);
  if (staticProfile.target_school) parts.push(`目标院校：${staticProfile.target_school}`);
  if (staticProfile.target_major) parts.push(`目标专业：${staticProfile.target_major}`);
  if (staticProfile.target_region) parts.push(`目标地区：${staticProfile.target_region}`);
  if (staticProfile.backup_school) parts.push(`保底院校：${staticProfile.backup_school}`);
  if (staticProfile.exam_type) parts.push(`升学类型：${staticProfile.exam_type}`);
  if (staticProfile.current_education) parts.push(`当前学历：${staticProfile.current_education}`);
  if (staticProfile.graduation_year != null) parts.push(`毕业年份：${staticProfile.graduation_year}`);
  parts.push(`每日目标：${staticProfile.daily_minutes} 分钟`);
  if (staticProfile.subjects.length) {
    parts.push(
      `科目：${staticProfile.subjects.map((id) => subjectNames[id] || id).join("、")}`,
    );
  }
  if (staticProfile.study_window) parts.push(`学习时段：${staticProfile.study_window}`);
  if (staticProfile.constraints) parts.push(`限制：${staticProfile.constraints}`);
  if (staticProfile.strengths) parts.push(`优势：${staticProfile.strengths}`);
  if (staticProfile.weaknesses) parts.push(`薄弱点：${staticProfile.weaknesses}`);
  if (staticProfile.motivation) parts.push(`动机：${staticProfile.motivation}`);
  return parts.join("；");
}

async function writeClipboard(value: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    /* 退回到 execCommand */
  }
  try {
    const area = document.createElement("textarea");
    area.value = value;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-9999px";
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
  const [copyState, setCopyState] = useState<"idle" | "done" | "error">("idle");
  const copyTimer = useRef<number | null>(null);

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

  useEffect(() => {
    return () => {
      if (copyTimer.current != null) window.clearTimeout(copyTimer.current);
    };
  }, []);

  const subjectOptions = useMemo<Pick<Subject, "id" | "name" | "short">[]>(() => {
    if (subjectList.length) return subjectList;
    return profile?.dynamic.subjects ?? [];
  }, [subjectList, profile]);

  const subjectNames = useMemo<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    subjectOptions.forEach((subject) => {
      map[subject.id] = subject.short || subject.name;
    });
    return map;
  }, [subjectOptions]);

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

  function validate(): string {
    const minutes = Number(form.daily_minutes);
    if (
      !form.daily_minutes.trim() ||
      !Number.isInteger(minutes) ||
      minutes < 1 ||
      minutes > 600
    ) {
      return "每日目标需在 1–600 分钟之间";
    }
    if (form.target_score.trim()) {
      const score = Number(form.target_score);
      if (!Number.isFinite(score) || score < 0) {
        return "目标分需是非负数字";
      }
    }
    const targetDate = form.target_date.trim();
    if (targetDate && !/^\d{4}-\d{2}-\d{2}$/.test(targetDate)) {
      return "日期格式需为 YYYY-MM-DD";
    }
    if (form.graduation_year.trim()) {
      const year = Number(form.graduation_year);
      if (!Number.isInteger(year) || year < 1950 || year > 2100) {
        return "毕业年份需是 1950–2100 的整数";
      }
    }
    return "";
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const invalid = validate();
    if (invalid) {
      setSaveError(invalid);
      return;
    }
    const body = diffForm(form, baseline);
    body.source = "user";
    setSaving(true);
    setSaved(false);
    setSaveError("");
    try {
      const next = await api.updateProfile(body);
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
  const completeness = profile ? Math.round(profile.completeness * 100) : 0;
  const missing = profile?.missing ?? [];
  const nextQuestions = (profile?.next_questions ?? []).slice(0, 3);
  const aiSummary = profile?.static.ai_summary?.trim() ?? "";

  const aiPrompt = useMemo(() => {
    if (!profile) return "";
    const summary = summaryText(profile.static, subjectNames) || "尚未填写";
    const missingText = profile.missing.length ? profile.missing.join("、") : "无";
    return [
      "请根据我的学习画像补全缺失信息。",
      `当前缺失：${missingText}`,
      `当前画像：${summary}`,
      '一次问我 2-3 个问题；我回答后，用 update_profile(source="agent", ai_summary="...") 更新。',
    ].join("\n");
  }, [profile, subjectNames]);

  async function copyAiPrompt() {
    const ok = await writeClipboard(aiPrompt);
    setCopyState(ok ? "done" : "error");
    if (copyTimer.current != null) window.clearTimeout(copyTimer.current);
    copyTimer.current = window.setTimeout(() => setCopyState("idle"), 3000);
  }

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

          <section className="card profile-completeness">
            <div className="profile-completeness-head">
              <div>
                <p className="card-kicker">画像完整度</p>
                <p className="profile-completeness-value">
                  {completeness}%
                  <span className="profile-completeness-sep"> · </span>
                  <span className="muted">
                    {missing.length ? `还差 ${missing.length} 项` : "必填项已齐全"}
                  </span>
                </p>
              </div>
              <span
                className={`profile-source ${
                  profile.static.updated_by === "agent" ? "is-agent" : ""
                }`}
              >
                {profile.static.updated_by === "agent" ? "由 AI 整理" : "由你更新"}
              </span>
            </div>
            <div
              className="stat-track profile-completeness-track"
              role="progressbar"
              aria-label="画像完整度"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={completeness}
            >
              <span className="stat-fill" style={{ width: `${completeness}%` }} />
            </div>
            {missing.length ? (
              <div className="profile-missing">
                {missing.map((field) => (
                  <span key={field} className="profile-missing-chip">
                    {labelOf(field)}
                    {" "}
                    <code>{field}</code>
                  </span>
                ))}
              </div>
            ) : (
              <p className="muted small profile-completeness-foot">
                必填信息已完成，可以继续补充选填项让 AI 更懂你。
              </p>
            )}
          </section>

          <section className="section">
            <div className="section-head">
              <h2>让 AI 完善画像</h2>
              <span className="muted small">复制提示词，交给 Agent 追问</span>
            </div>
            <div className={`profile-ai-grid ${aiSummary ? "" : "is-single"}`}>
              <div className="card profile-ai">
                <div className="profile-ai-head">
                  <p className="card-kicker">接下来可以补</p>
                  <span className="muted small">一次问 2–3 个</span>
                </div>
                {nextQuestions.length ? (
                  <ol className="profile-ai-questions">
                    {nextQuestions.map((item) => (
                      <li key={item.field}>
                        <span className="profile-ai-field">
                          {labelOf(item.field)}
                          {" "}
                          <code>{item.field}</code>
                        </span>
                        <p>{item.question}</p>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="muted small">必填项已经齐全，可以让 AI 继续了解你的学习习惯。</p>
                )}
                <div className="profile-ai-actions">
                  <button className="btn" type="button" onClick={() => void copyAiPrompt()}>
                    复制补全提示
                  </button>
                  {copyState === "done" && (
                    <span className="profile-save-ok" role="status">
                      已复制补全提示
                    </span>
                  )}
                  {copyState === "error" && (
                    <span className="warn-text small" role="status">
                      复制失败，请手动选择提示词
                    </span>
                  )}
                </div>
              </div>
              {aiSummary && (
                <div className="card profile-ai-summary">
                  <div className="profile-ai-head">
                    <p className="card-kicker">AI 整理</p>
                    <span className="muted small">只读</span>
                  </div>
                  <p className="profile-ai-summary-body">{aiSummary}</p>
                  <p className="hint">由 AI 在对话后写入，你自己保存时不会覆盖。</p>
                </div>
              )}
            </div>
          </section>

          <section className="section" id="profile-form">
            <div className="section-head">
              <h2>画像信息</h2>
              <span className={dirty ? "profile-dirty" : "muted small"}>
                {dirty ? "有未保存修改" : saved ? "已保存" : "改动后记得保存"}
              </span>
            </div>
            <form className="card profile-form" onSubmit={handleSubmit}>
              <div className="profile-group">
                <div className="profile-group-head">
                  <h3>升学目标</h3>
                  <p className="muted small">只填和这次考试有关的信息。</p>
                </div>
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
                    <label htmlFor="profile-school">目标院校</label>
                    <input
                      id="profile-school"
                      maxLength={100}
                      value={form.target_school}
                      onChange={(e) => patch("target_school", e.target.value)}
                      placeholder="如 广东技术师范大学"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="profile-major">目标专业</label>
                    <input
                      id="profile-major"
                      maxLength={100}
                      value={form.target_major}
                      onChange={(e) => patch("target_major", e.target.value)}
                      placeholder="如 计算机科学与技术"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="profile-region">目标地区</label>
                    <input
                      id="profile-region"
                      maxLength={50}
                      value={form.target_region}
                      onChange={(e) => patch("target_region", e.target.value)}
                      placeholder="如 广州"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="profile-backup-school">保底院校</label>
                    <input
                      id="profile-backup-school"
                      maxLength={100}
                      value={form.backup_school}
                      onChange={(e) => patch("backup_school", e.target.value)}
                      placeholder="可留空"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="profile-backup-major">保底专业</label>
                    <input
                      id="profile-backup-major"
                      maxLength={100}
                      value={form.backup_major}
                      onChange={(e) => patch("backup_major", e.target.value)}
                      placeholder="可留空"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="profile-exam-type">升学类型</label>
                    <input
                      id="profile-exam-type"
                      maxLength={100}
                      value={form.exam_type}
                      onChange={(e) => patch("exam_type", e.target.value)}
                      placeholder="如 专升本 / 自考 / 考研"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="profile-education">当前学历</label>
                    <input
                      id="profile-education"
                      maxLength={100}
                      value={form.current_education}
                      onChange={(e) => patch("current_education", e.target.value)}
                      placeholder="如 专科"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="profile-graduation">毕业年份</label>
                    <input
                      id="profile-graduation"
                      type="number"
                      inputMode="numeric"
                      step="1"
                      min="1950"
                      max="2100"
                      value={form.graduation_year}
                      onChange={(e) => patch("graduation_year", e.target.value)}
                      placeholder="如 2028"
                    />
                  </div>
                </div>
              </div>

              <div className="profile-group">
                <div className="profile-group-head">
                  <h3>学习条件</h3>
                  <p className="muted small">按现实能投入的时间来定。</p>
                </div>
                <div className="profile-form-grid">
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
                    <label htmlFor="profile-window">学习时段</label>
                    <input
                      id="profile-window"
                      maxLength={200}
                      value={form.study_window}
                      onChange={(e) => patch("study_window", e.target.value)}
                      placeholder="如 工作日晚上 2h + 周末 4h"
                    />
                  </div>
                  <div className="field profile-span-2">
                    <label htmlFor="profile-constraints">限制</label>
                    <textarea
                      id="profile-constraints"
                      rows={3}
                      maxLength={1000}
                      value={form.constraints}
                      onChange={(e) => patch("constraints", e.target.value)}
                      placeholder="时间、工作、家庭等现实限制，如 白天上班"
                    />
                  </div>
                </div>
              </div>

              <div className="profile-group">
                <div className="profile-group-head">
                  <h3>自我评估</h3>
                  <p className="muted small">你怎么看自己，决定先补哪里。</p>
                </div>
                <div className="profile-form-grid">
                  <div className="field">
                    <label htmlFor="profile-strengths">优势</label>
                    <textarea
                      id="profile-strengths"
                      rows={3}
                      maxLength={1000}
                      value={form.strengths}
                      onChange={(e) => patch("strengths", e.target.value)}
                      placeholder="如 英语单词记得快"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="profile-weaknesses">薄弱点</label>
                    <textarea
                      id="profile-weaknesses"
                      rows={3}
                      maxLength={1000}
                      value={form.weaknesses}
                      onChange={(e) => patch("weaknesses", e.target.value)}
                      placeholder="如 数学基础弱"
                    />
                  </div>
                  <div className="field profile-span-2">
                    <label htmlFor="profile-motivation">动机</label>
                    <textarea
                      id="profile-motivation"
                      rows={2}
                      maxLength={1000}
                      value={form.motivation}
                      onChange={(e) => patch("motivation", e.target.value)}
                      placeholder="如 想换到计算机相关岗位"
                    />
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
                    <p className="hint">备注只由你手写，AI 摘要不会覆盖它。</p>
                  </div>
                </div>
              </div>

              <div className="profile-group">
                <div className="profile-group-head">
                  <h3>教学偏好</h3>
                  <p className="muted small">影响 AI 讲解和组卷的风格。</p>
                </div>
                <div className="profile-form-grid">
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
              </div>

              {saveError && <div className="alert profile-form-error">{saveError}</div>}

              <div className="profile-form-actions">
                <button className="btn btn-primary" type="submit" disabled={saving || !dirty}>
                  {saving ? "保存中…" : "保存"}
                </button>
                {saved && <span className="profile-save-ok">已保存，只提交了改动的字段</span>}
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

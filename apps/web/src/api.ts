import type { AgentEvent, Attempt, ContentValidation, DailyStats, HeatmapDay, LibraryStats, OutlineNode, PageDetail, PageDraftInput, PageDraftResponse, PageQuestionCount, PageSummary, Profile, ProfileStatic, Progress, PublishResult, Question, QuestionType, Quiz, QuizSummary, Subject, SubjectStats, TypeStats } from "./types";

const BASE = "/api";

function messageOf(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  if (Array.isArray(detail)) {
    const parts = detail.map((item) =>
      typeof item === "string" ? item : (item as { msg?: unknown })?.msg,
    );
    if (parts.every((part) => typeof part === "string")) return parts.join("；");
  }
  return JSON.stringify(detail);
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(messageOf(detail));
    this.status = status;
    this.detail = detail;
  }
}

/** Agent 事件 SSE 地址；EventSource 重连时带上当前游标。 */
export function agentStreamUrl(sessionId: string, afterId = 0): string {
  return `${BASE}/agent/stream?session_id=${encodeURIComponent(sessionId)}&after_id=${afterId}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export interface BuildQuizBody {
  title?: string;
  mode: "practice" | "exam";
  time_limit?: number | null;
  count: number;
  agent_session_id?: string;
  filters?: {
    subject_id?: string;
    codes?: string[];
    types?: string[];
    exclude_days?: number;
    verified_only?: boolean;
  };
  question_ids?: string[];
}

export const api = {
  profile: () => request<Profile>("/profile"),
  updateProfile: (body: Partial<ProfileStatic>) =>
    request<Profile>("/profile", { method: "PUT", body: JSON.stringify(body) }),
  subjects: () => request<Subject[]>("/subjects"),
  questionTypes: () => request<QuestionType[]>("/question-types"),
  outline: (subjectId?: string) =>
    request<OutlineNode[]>(`/outline${subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : ""}`),
  questions: (params: { subject_id?: string; code?: string; type?: string; limit?: number }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v != null && q.set(k, String(v)));
    return request<Question[]>(`/questions?${q.toString()}`);
  },
  buildQuiz: (body: BuildQuizBody) =>
    request<Quiz>("/quizzes", { method: "POST", body: JSON.stringify(body) }),
  startAttempt: (quizId: string) =>
    request<Attempt>("/attempts", { method: "POST", body: JSON.stringify({ quiz_id: quizId }) }),
  patchAttempt: (attemptId: string, body: { active_seconds?: number; answers?: unknown[] }) =>
    request<{ ok: boolean }>(`/attempts/${attemptId}`, { method: "PATCH", body: JSON.stringify(body) }),
  submitAttempt: (
    attemptId: string,
    body: { active_seconds: number; answers: unknown[] },
  ) => request<Attempt>(`/attempts/${attemptId}/submit`, { method: "POST", body: JSON.stringify(body) }),
  attempt: (attemptId: string) => request<Attempt>(`/attempts/${attemptId}`),
  quiz: (quizId: string) => request<Quiz>(`/quizzes/${quizId}`),
  /** 草稿兜底：页面隐藏 / 卸载时用 keepalive 发，失败不阻塞。 */
  saveDraftBeacon: (attemptId: string, answers: unknown[]) =>
    fetch(`${BASE}/attempts/${attemptId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
      keepalive: true,
    }).then((res) => {
      if (!res.ok) throw new ApiError(res.status, res.statusText);
      return res.json() as Promise<{ ok: boolean }>;
    }),
  due: (subjectId?: string) =>
    request<Question[]>(`/reviews/due${subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : ""}`),
  today: () => request<DailyStats>("/stats/today"),
  statsSubjects: (days = 30) => request<SubjectStats[]>(`/stats/subjects?days=${days}`),
  statsHeatmap: (days = 90) => request<HeatmapDay[]>(`/stats/heatmap?days=${days}`),
  statsTypes: (days = 30) => request<TypeStats[]>(`/stats/types?days=${days}`),
  pages: (subjectId?: string) =>
    request<PageSummary[]>(`/pages${subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : ""}`),
  page: (pageId: string) => request<PageDetail>(`/pages/${pageId}`),
  pageDraft: (pageId: string) => request<PageDraftResponse>(`/pages/${pageId}/draft`),
  savePageDraft: (pageId: string, body: PageDraftInput, keepalive = false) =>
    request<PageDraftResponse>(`/pages/${pageId}/draft`, {
      method: "PUT",
      body: JSON.stringify(body),
      keepalive,
    }),
  discardPageDraft: (pageId: string) =>
    request<{ ok: boolean; page_id: string }>(`/pages/${pageId}/draft`, { method: "DELETE" }),
  publishPageDraft: (pageId: string, message?: string, commit = false) =>
    request<PublishResult>(`/pages/${pageId}/publish`, {
      method: "POST",
      body: JSON.stringify({ message, commit }),
    }),
  /** 草稿版本 SSE；page_id 只用于拼地址。 */
  pageDraftStreamUrl: (pageId: string) =>
    `${BASE}/pages/${encodeURIComponent(pageId)}/draft/stream`,
  validateContent: () => request<ContentValidation>("/content/validate", { method: "POST" }),
  pageQuestionCount: (pageId: string) =>
    request<PageQuestionCount>(`/pages/${pageId}/question-count`),
  completePage: (pageId: string) =>
    request<{ completed_at: string; xp: number; already: boolean }>(`/pages/${pageId}/complete`, {
      method: "POST",
    }),
  progress: () => request<Progress>("/progress"),
  library: () => request<LibraryStats>("/stats/library"),
  quizzes: (limit = 10) => request<QuizSummary[]>(`/quizzes?limit=${limit}`),
  createAgentSession: (title: string) =>
    request<{ id: string; title: string }>("/agent/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  agentFeed: (sessionId: string, afterId = 0) =>
    request<AgentEvent[]>(`/agent/feed?session_id=${encodeURIComponent(sessionId)}&after_id=${afterId}`),
  sendHelp: (attemptId: string, questionId: string, body: string) =>
    request<{ id: number }>("/agent/help", {
      method: "POST",
      body: JSON.stringify({ attempt_id: attemptId, question_id: questionId, body }),
    }),
};
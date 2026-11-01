import type { Attempt, DailyStats, OutlineNode, Question, Quiz, Subject } from "./types";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
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
  subjects: () => request<Subject[]>("/subjects"),
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
  due: (subjectId?: string) =>
    request<Question[]>(`/reviews/due${subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : ""}`),
  today: () => request<DailyStats>("/stats/today"),
};
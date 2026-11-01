export type QType =
  | "single"
  | "multiple"
  | "judge"
  | "fill"
  | "short"
  | "calc"
  | "code"
  | "essay";

export interface RubricPoint {
  point: string;
  score: number;
}

export interface Subject {
  id: string;
  name: string;
  short: string;
  exam_score: number;
  exam_minutes: number;
  node_count: number;
  hours: number;
  question_count: number;
}

export interface OutlineNode {
  code: string;
  subject_id: string;
  section: string;
  title: string;
  requirement: string | null;
  frequency: string | null;
  hours: number | null;
  stage: string | null;
  assessment: string | null;
  kind: "point" | "training";
  sort: number;
  question_count: number;
}

export interface Question {
  id: string;
  subject_id: string;
  outline_code: string;
  type: QType;
  stem: string;
  options?: string[] | null;
  score: number;
  difficulty: number;
  tags: string[];
  verified: boolean;
  source?: Record<string, unknown> | null;
  answer?: string[] | null;
  explanation?: string;
  reference_answer?: string | null;
  rubric?: RubricPoint[] | null;
}

export interface Quiz {
  id: string;
  title: string;
  mode: "practice" | "exam";
  time_limit: number | null;
  agent_session_id?: string | null;
  created_at: string;
  question_count: number;
  questions: Question[];
}

export interface AnswerState {
  response: unknown;
  correct: boolean | null;
  score: number | null;
  time_spent: number;
  flagged: boolean;
  self_grade: number[] | null;
}

export interface ResultItem {
  question: Question;
  response: unknown;
  self_grade: number[] | null;
  correct: boolean | null;
  score: number;
  max_score: number;
  time_spent?: number;
  flagged?: boolean;
}

export interface Attempt {
  id: string;
  quiz_id: string;
  started_at: string;
  ended_at: string | null;
  active_seconds: number;
  status: "active" | "submitted";
  score: number | null;
  max_score: number | null;
  quiz: Quiz;
  answers: Record<string, AnswerState>;
  results?: ResultItem[];
  weak?: { code: string; wrong: number }[];
}

export interface DailyStats {
  date: string;
  active_seconds: number;
  attempts: number;
  score: number;
  max_score: number;
  answered: number;
  correct: number;
  by_subject: { subject_id: string; n: number; ok: number }[];
}

export const TYPE_LABEL: Record<QType, string> = {
  single: "单选",
  multiple: "多选",
  judge: "判断",
  fill: "填空",
  short: "简答",
  calc: "计算",
  code: "编程",
  essay: "写作",
};

export const LETTERS = "ABCDEFGH";

export interface AgentEvent {
  id: number;
  session_id: string;
  kind: "note" | "help" | "submitted" | "started";
  role: "agent" | "user" | "system";
  body: string | null;
  ref: string | null;
  created_at: string;
}

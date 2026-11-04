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
  color: string | null;
  icon: string | null;
  sort: number;
  code_language: string | null;
}

export interface QuestionType {
  id: string;
  label: string;
  input: "choice" | "judge" | "text" | "code";
  grading: "auto" | "agent";
  answer_schema: "letters" | "boolean" | "blanks" | "rubric" | "code" | "text";
  min_options?: number;
  max_options?: number;
  requires_rubric?: boolean;
  allow_partial?: boolean;
  language?: string;
  sort?: number;
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
  parent_code?: string | null;
  depth?: number;
}

export interface QuestionMedia {
  type: "image" | "audio" | "video";
  url: string;
  alt?: string | null;
  license?: string | null;
  source?: string | null;
}

/** 材料题 / 复合题的分组：一段材料（可带图 / 音频 / 视频）挂多道小题。 */
export interface QuestionGroup {
  id: string;
  subject_id?: string | null;
  title?: string | null;
  material: string;
  media: QuestionMedia[];
  question_ids?: string[];
}

export interface Question {
  id: string;
  subject_id: string;
  outline_code: string;
  type: string;
  stem: string;
  options?: string[] | null;
  score: number;
  difficulty: number;
  tags: string[];
  verified: boolean;
  source?: Record<string, unknown> | null;
  answer?: Array<string | string[]> | null;
  explanation?: string;
  reference_answer?: string | null;
  rubric?: RubricPoint[] | null;
  /** 材料题归属；group_position 决定同组小题顺序。 */
  group_id?: string | null;
  group_position?: number;
  media?: QuestionMedia[] | null;
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
  /** 材料 / 复合题分组。 */
  groups?: QuestionGroup[];
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
  score: number | null;
  max_score: number;
  pending?: boolean;
  graded_by?: string | null;
  feedback?: string | null;
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
  grading_status?: "none" | "pending" | "done";
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


export interface PageSummary {
  id: string;
  subject_id: string | null;
  lesson_key?: string | null;
  title: string;
  summary: string | null;
  outline_codes: string[];
  kind: "outline" | "lesson" | "daily" | "note";
  status: "draft" | "published";
  sort_order?: number;
  created_at: string;
  updated_at: string;
  excerpt?: string;
  completed: boolean;
  completed_at: string | null;
  xp: number;
}

export interface PageDetail extends PageSummary {
  body: string;
}

/** 本课考点下可用于组卷的题量；codes 为页面考点（缺省时回退页面自身）。 */
export interface PageQuestionCount {
  count: number;
  codes: string[];
}

export interface QuizSummary {
  id: string;
  title: string;
  mode: "practice" | "exam";
  time_limit: number | null;
  agent_session_id: string | null;
  created_at: string;
  question_count: number;
}


export interface Progress {
  streak: number;
  today_done: boolean;
  today_minutes: number;
  daily_goal_minutes: number;
  xp: number;
  completed_pages: number;
  total_pages: number;
  days: { date: string; minutes: number; done: boolean }[];
}


export interface LibraryStats {
  total: number;
  approved: number;
  pending: number;
  rejected: number;
  by_type: { type: string; n: number }[];
}

/** 分科目统计：无数据的科目也返回，数值补 0。 */
export interface SubjectStats {
  subject_id: string;
  name: string;
  short: string;
  color: string | null;
  icon: string | null;
  answered: number;
  correct: number;
  seconds: number;
  attempts: number;
}

/** 热力图每日一格，按日期升序，长度等于请求的 days。 */
export interface HeatmapDay {
  date: string;
  seconds: number;
  answered: number;
}

/** 分题型统计：只含有作答记录的题型。 */
export interface TypeStats {
  type: string;
  label: string;
  answered: number;
  correct: number;
}

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

export type BlockType =
  | "markdown"
  | "callout"
  | "columns"
  | "tabs"
  | "steps"
  | "cards"
  | "timeline"
  | "image"
  | "video"
  | "audio"
  | "code"
  | "mermaid"
  | "math-graph"
  | "sandbox"
  | "divider";

export type CalloutTone = "info" | "warn" | "danger" | "success";

export interface MarkdownBlock {
  type: "markdown";
  text: string;
}

export interface CalloutBlock {
  type: "callout";
  tone: CalloutTone;
  title?: string;
  text: string;
}

export interface ColumnsBlock {
  type: "columns";
  cols: Block[][];
}

export interface TabsBlock {
  type: "tabs";
  items: { label: string; blocks: Block[] }[];
}

export interface StepsBlock {
  type: "steps";
  items: { title: string; text: string }[];
}

export interface CardsBlock {
  type: "cards";
  items: { title: string; text: string; link?: string }[];
}

export interface TimelineBlock {
  type: "timeline";
  items: { time: string; title: string; text: string }[];
}

export interface ImageBlock {
  type: "image";
  url: string;
  alt?: string;
  caption?: string;
  license?: string;
}

export interface VideoBlock {
  type: "video";
  url: string;
  poster?: string;
}

export interface AudioBlock {
  type: "audio";
  url: string;
  title?: string;
}

export interface CodeBlock {
  type: "code";
  language: string;
  code: string;
  title?: string;
}

export interface MermaidBlock {
  type: "mermaid";
  code: string;
}

export interface MathGraphBlock {
  type: "math-graph";
  spec: string | Record<string, unknown>;
}

export interface SandboxBlock {
  type: "sandbox";
  html: string;
  height?: number;
  title?: string;
}

export interface DividerBlock {
  type: "divider";
}

/** 讲义 JSON 块；Markdown 页不会用到。契约见 docs/dev/blocks.md。 */
export type Block =
  | MarkdownBlock
  | CalloutBlock
  | ColumnsBlock
  | TabsBlock
  | StepsBlock
  | CardsBlock
  | TimelineBlock
  | ImageBlock
  | VideoBlock
  | AudioBlock
  | CodeBlock
  | MermaidBlock
  | MathGraphBlock
  | SandboxBlock
  | DividerBlock;

export interface PageTheme {
  accent?: string;
  density?: string;
  font?: string;
}

/** 网页编辑器保存草稿的请求体；base_version 用于并发检测。 */
export interface PageDraftInput {
  body?: string;
  blocks?: Block[] | null;
  layout?: string;
  theme?: PageTheme | null;
  base_version?: number;
}

export interface PageDraft {
  page_id: string;
  body: string | null;
  blocks: Block[] | null;
  layout: string | null;
  theme: PageTheme | null;
  version: number;
  updated_at: string;
}

export interface PageDraftResponse {
  page: PageDetail;
  draft: PageDraft | null;
}

export interface PublishResult {
  page: PageDetail;
  file: string | null;
  committed: boolean;
}

export interface ContentValidation {
  ok: boolean;
  packs: { id: string; ok: boolean; errors: string[] }[];
}

export interface PageDetail extends PageSummary {
  body: string;
  /** 块页为 Block[]，Markdown 页为 null / 缺省。 */
  blocks?: Block[] | null;
  layout?: string;
  theme?: PageTheme | null;
  format?: "markdown" | "blocks";
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

/** 学习画像静态目标，存 profile 单行表。 */
export interface ProfileStatic {
  target_exam: string | null;
  target_date: string | null;
  target_score: number | null;
  target_school: string | null;
  target_major: string | null;
  target_region: string | null;
  backup_school: string | null;
  backup_major: string | null;
  exam_type: string | null;
  current_education: string | null;
  graduation_year: number | null;
  daily_minutes: number;
  subjects: string[];
  study_window: string | null;
  constraints: string | null;
  strengths: string | null;
  weaknesses: string | null;
  motivation: string | null;
  notes: string;
  /** 只由 AI 维护，用户保存时不要回传。 */
  ai_summary: string;
  preferred_tone: string;
  preferred_examples: string;
  updated_by: "user" | "agent";
}

/** PUT /api/profile 可写字段；ai_summary / updated_by 不由此接口的页面表单发送。 */
export type ProfileUpdate = Omit<
  Partial<ProfileStatic>,
  "ai_summary" | "updated_by"
> & { source?: "user" | "agent" };

export interface ProfileQuestion {
  field: string;
  question: string;
}

export interface SubjectProfile {
  id: string;
  name: string;
  short: string;
  color: string | null;
  answered: number;
  correct: number;
  accuracy: number | null;
  seconds: number;
}

export interface WeakCode {
  code: string;
  title: string;
  wrong: number;
}

export interface RecentDay {
  date: string;
  seconds: number;
  answered: number;
}

/** 动态学情实时计算，不落库。 */
export interface ProfileDynamic {
  days_to_exam: number | null;
  today_minutes: number;
  streak: number;
  xp: number;
  completed_pages: number;
  answered: number;
  correct: number;
  accuracy: number | null;
  due_reviews: number;
  subjects: SubjectProfile[];
  weak_codes: WeakCode[];
  recent: RecentDay[];
}

export interface Profile {
  static: ProfileStatic;
  dynamic: ProfileDynamic;
  /** 必填 8 项的完成比例，0–1。 */
  completeness: number;
  /** 尚未填写的字段，必填优先。 */
  missing: string[];
  next_questions: ProfileQuestion[];
}

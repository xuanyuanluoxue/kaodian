import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api";
import { errorText } from "../../lib/format";
import { useQuestionTypes } from "../../lib/useQuestionTypes";
import type { AgentEvent, Attempt, Question } from "../../types";
import { hasAnswer } from "./helpers";

/* 答题会话：attempt 加载 / 时钟 / 草稿 / 提交 / Agent feed。
   组件只负责渲染，状态与副作用都在这里。 */

const DRAFT_DEBOUNCE_MS = 1200;
const ACTIVE_PATCH_MS = 15_000;
const IDLE_MS = 90_000;

export interface Clock {
  subscribe: (fn: () => void) => () => void;
  getSnapshot: () => number;
}

export interface DraftAnswer {
  question_id: string;
  response: unknown;
  time_spent: number;
  flagged: boolean;
  self_grade: number[] | null;
}

export interface SubmitOptions {
  /** 超时自动交卷：跳过「还有未答题」确认，且只触发一次。 */
  auto?: boolean;
}

/** 恢复练习单的 rubric / 解析：进行中的 attempt 为了不泄题只返回精简题目。
    练习模式本来就即时批改，重新取一次 quiz 让自评和反馈刷新后仍在。 */
async function withPracticeDetail(attempt: Attempt): Promise<Attempt> {
  if (attempt.quiz.mode !== "practice") return attempt;
  try {
    const full = await api.quiz(attempt.quiz_id);
    const byId = new Map(full.questions.map((item) => [item.id, item]));
    return {
      ...attempt,
      quiz: {
        ...attempt.quiz,
        questions: attempt.quiz.questions.map((item) => {
          const extra = byId.get(item.id);
          return extra
            ? {
                ...item,
                answer: extra.answer,
                explanation: extra.explanation,
                reference_answer: extra.reference_answer,
                rubric: extra.rubric,
              }
            : item;
        }),
      },
    };
  } catch {
    return attempt;
  }
}

export function useQuizSession(quizId: string | undefined) {
  const navigate = useNavigate();
  const { byId, label, loading: typesLoading } = useQuestionTypes();

  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [index, setIndex] = useState(0);
  const [responses, setResponses] = useState<Record<string, unknown>>({});
  const [selfGrades, setSelfGrades] = useState<Record<string, number[]>>({});
  const [flagged, setFlagged] = useState<Record<string, boolean>>({});
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [manualPause, setManualPause] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [idle, setIdle] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);

  const attemptRef = useRef<Attempt | null>(null);
  const questionsRef = useRef<Question[]>([]);
  const indexRef = useRef(0);
  const responsesRef = useRef<Record<string, unknown>>({});
  const flaggedRef = useRef<Record<string, boolean>>({});
  const selfGradesRef = useRef<Record<string, number[]>>({});
  const hydrated = useRef(false);

  const activeSeconds = useRef(0);
  const pausedRef = useRef(false);
  const lastActivity = useRef(Date.now());
  const enterAt = useRef(Date.now());
  const timeMs = useRef<Record<string, number>>({});
  const times = useRef<Record<string, number>>({});

  const submitted = useRef(false);
  const submittingLock = useRef(false);
  const autoFired = useRef(false);
  const submitRef = useRef<(opts?: SubmitOptions) => void>(() => {});
  const agentCursor = useRef(0);
  const draftTimer = useRef<number | null>(null);

  const listeners = useRef<Set<() => void>>(new Set());
  const notifyClock = useCallback(() => {
    listeners.current.forEach((fn) => fn());
  }, []);
  const clock = useMemo<Clock>(
    () => ({
      subscribe: (fn) => {
        listeners.current.add(fn);
        return () => {
          listeners.current.delete(fn);
        };
      },
      getSnapshot: () => activeSeconds.current,
    }),
    [],
  );

  const questions = attempt?.quiz.questions ?? [];
  questionsRef.current = questions;
  indexRef.current = index;
  responsesRef.current = responses;
  flaggedRef.current = flagged;
  selfGradesRef.current = selfGrades;

  const paused = manualPause || hidden || idle;
  pausedRef.current = paused;

  const practice = attempt?.quiz.mode === "practice";
  const limit = attempt?.quiz.time_limit ?? null;

  /* ---------- attempt 加载 + 草稿 hydrate ---------- */

  useEffect(() => {
    if (!quizId) {
      setError("缺少练习单编号");
      setLoading(false);
      return;
    }
    let alive = true;
    const key = `kaodian:attempt:${quizId}`;
    const saved = sessionStorage.getItem(key);
    setLoading(true);
    setAttempt(null);
    submitted.current = false;
    submittingLock.current = false;
    autoFired.current = false;
    hydrated.current = false;

    const load = async (): Promise<Attempt> => {
      if (saved) {
        try {
          const existing = await api.attempt(saved);
          if (existing.status === "active") return withPracticeDetail(existing);
          sessionStorage.removeItem(key);
        } catch (e) {
          if (e instanceof ApiError && e.status === 404) {
            // 记录已不存在（换库 / 清理），允许新开一次
            sessionStorage.removeItem(key);
          } else if (e instanceof ApiError && e.status === 409) {
            sessionStorage.removeItem(key);
          } else {
            // 网络错误：不要新建 attempt，避免丢草稿
            throw new Error(`读取上次作答失败：${errorText(e)}`);
          }
        }
      }
      return api.startAttempt(quizId);
    };

    load()
      .then((a) => {
        if (!alive) return;
        sessionStorage.setItem(key, a.id);
        const nextResponses: Record<string, unknown> = {};
        const nextFlagged: Record<string, boolean> = {};
        const nextSelf: Record<string, number[]> = {};
        const nextMs: Record<string, number> = {};
        Object.entries(a.answers || {}).forEach(([qid, answer]) => {
          nextResponses[qid] = answer?.response ?? null;
          nextFlagged[qid] = !!answer?.flagged;
          nextSelf[qid] = answer?.self_grade ?? [];
          const seconds = answer?.time_spent || 0;
          times.current[qid] = seconds;
          nextMs[qid] = seconds * 1000;
        });
        timeMs.current = nextMs;
        activeSeconds.current = a.active_seconds || 0;
        enterAt.current = Date.now();
        agentCursor.current = 0;
        setAgentEvents([]);
        setAttempt(a);
        setResponses(nextResponses);
        setFlagged(nextFlagged);
        setSelfGrades(nextSelf);
        setIndex(0);
        hydrated.current = true;
        setLoading(false);
        notifyClock();
      })
      .catch((e) => {
        if (!alive) return;
        setError(errorText(e));
        setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [quizId, notifyClock]);

  /* ---------- 计时 ---------- */

  useEffect(() => {
    if (!attempt || attempt.status !== "active") return;
    const timer = window.setInterval(() => {
      if (pausedRef.current || document.hidden || submitted.current) return;
      activeSeconds.current += 1;
      notifyClock();
      const timeLimit = attempt.quiz.time_limit;
      if (
        timeLimit &&
        attempt.quiz.mode === "exam" &&
        activeSeconds.current >= timeLimit &&
        !autoFired.current
      ) {
        autoFired.current = true;
        submitRef.current({ auto: true });
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [attempt, notifyClock]);

  // 加载完成时可能已经超时（例如离开页面很久后回来）
  useEffect(() => {
    if (!attempt || attempt.quiz.mode !== "exam") return;
    const timeLimit = attempt.quiz.time_limit;
    if (timeLimit && (attempt.active_seconds || 0) >= timeLimit && !autoFired.current) {
      autoFired.current = true;
      submitRef.current({ auto: true });
    }
  }, [attempt]);

  useEffect(() => {
    const bump = () => {
      lastActivity.current = Date.now();
      setIdle(false);
    };
    const events: (keyof WindowEventMap)[] = ["keydown", "click", "scroll", "touchstart"];
    events.forEach((e) => window.addEventListener(e, bump, { passive: true } as AddEventListenerOptions));
    const timer = window.setInterval(() => {
      if (Date.now() - lastActivity.current > IDLE_MS) setIdle(true);
    }, 5000);
    return () => {
      events.forEach((e) => window.removeEventListener(e, bump));
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const onVis = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", onVis);
    onVis();
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  useEffect(() => {
    if (!attempt || attempt.status !== "active") return;
    const timer = window.setInterval(() => {
      if (submitted.current) return;
      api.patchAttempt(attempt.id, { active_seconds: activeSeconds.current }).catch(() => {});
    }, ACTIVE_PATCH_MS);
    return () => window.clearInterval(timer);
  }, [attempt]);

  /* ---------- 草稿 ---------- */

  const captureCurrentTime = useCallback(() => {
    const now = Date.now();
    const delta = Math.max(0, now - enterAt.current);
    enterAt.current = now;
    const current = questionsRef.current[indexRef.current];
    if (!current) return;
    timeMs.current[current.id] = (timeMs.current[current.id] || 0) + delta;
    times.current[current.id] = Math.round(timeMs.current[current.id] / 1000);
  }, []);

  const buildAnswers = useCallback((): DraftAnswer[] => {
    return questionsRef.current.map((item) => ({
      question_id: item.id,
      response: responsesRef.current[item.id] ?? null,
      time_spent: times.current[item.id] || 0,
      flagged: !!flaggedRef.current[item.id],
      self_grade: selfGradesRef.current[item.id] ?? null,
    }));
  }, []);

  const saveDraft = useCallback(
    (keepalive = false) => {
      const current = attemptRef.current;
      if (!current || current.status !== "active" || submitted.current || !hydrated.current) return;
      const answers = buildAnswers();
      if (keepalive) {
        api.saveDraftBeacon(current.id, answers).catch(() => {});
        return;
      }
      api.patchAttempt(current.id, { answers }).catch(() => {});
    },
    [buildAnswers],
  );

  /** 立刻落盘：切题、页面隐藏、pagehide、卸载。 */
  const flushDraft = useCallback(
    (keepalive = false) => {
      if (draftTimer.current !== null) {
        window.clearTimeout(draftTimer.current);
        draftTimer.current = null;
      }
      captureCurrentTime();
      saveDraft(keepalive);
    },
    [captureCurrentTime, saveDraft],
  );

  useEffect(() => {
    attemptRef.current = attempt;
  }, [attempt]);

  useEffect(() => {
    if (!hydrated.current || !attemptRef.current || submitted.current) return;
    if (draftTimer.current !== null) window.clearTimeout(draftTimer.current);
    draftTimer.current = window.setTimeout(() => {
      draftTimer.current = null;
      saveDraft();
    }, DRAFT_DEBOUNCE_MS);
    return () => {
      if (draftTimer.current !== null) {
        window.clearTimeout(draftTimer.current);
        draftTimer.current = null;
      }
    };
  }, [responses, flagged, selfGrades, saveDraft]);

  useEffect(() => {
    const onHide = () => {
      if (document.hidden) flushDraft(true);
    };
    const onLeave = () => flushDraft(true);
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", onLeave);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", onLeave);
      flushDraft(true);
    };
  }, [flushDraft]);

  /* ---------- Agent feed ---------- */

  useEffect(() => {
    const sid = attempt?.quiz.agent_session_id;
    if (!sid) return;
    let alive = true;
    const load = () => {
      api
        .agentFeed(sid, agentCursor.current)
        .then((list) => {
          if (!alive || !list.length) return;
          agentCursor.current = list[list.length - 1].id;
          setAgentEvents((prev) => [...prev, ...list]);
        })
        .catch(() => {});
    };
    load();
    const timer = window.setInterval(load, 5000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [attempt?.quiz.agent_session_id]);

  /* ---------- 交互 ---------- */

  const go = useCallback(
    (next: number) => {
      const list = questionsRef.current;
      if (!list.length) return;
      flushDraft();
      const target = Math.max(0, Math.min(next, list.length - 1));
      indexRef.current = target;
      enterAt.current = Date.now();
      setIndex(target);
    },
    [flushDraft],
  );

  const setResponse = useCallback((qid: string, value: unknown) => {
    setResponses((prev) => ({ ...prev, [qid]: value }));
  }, []);

  const reveal = useCallback((qid: string) => {
    setRevealed((prev) => new Set(prev).add(qid));
  }, []);

  const toggleOption = useCallback(
    (question: Question, letter: string) => {
      const meta = byId[question.type];
      if (!meta) return;
      if (meta.input === "judge") {
        setResponse(question.id, [letter === "A" ? "true" : "false"]);
        if (practice) reveal(question.id);
        return;
      }
      if (meta.input !== "choice") return;
      // 注册表暂未区分单选/多选，沿用已知的 multiple 题型 id 作为多选开关
      const multiple = question.type === "multiple";
      if (!multiple) {
        setResponse(question.id, [letter]);
        if (practice) reveal(question.id);
        return;
      }
      const current = Array.isArray(responsesRef.current[question.id])
        ? (responsesRef.current[question.id] as string[])
        : [];
      const next = current.includes(letter) ? current.filter((x) => x !== letter) : [...current, letter];
      setResponse(question.id, next);
      if (practice && revealed.has(question.id)) {
        // 改答案后收起批改，等重新核对
        setRevealed((prev) => {
          const copy = new Set(prev);
          copy.delete(question.id);
          return copy;
        });
      }
    },
    [byId, practice, reveal, setResponse, revealed],
  );

  const toggleFlag = useCallback((qid: string) => {
    setFlagged((prev) => ({ ...prev, [qid]: !prev[qid] }));
  }, []);

  const toggleSelfGrade = useCallback((qid: string, pointIndex: number) => {
    setSelfGrades((prev) => {
      const current = prev[qid] || [];
      const next = current.includes(pointIndex)
        ? current.filter((x) => x !== pointIndex)
        : [...current, pointIndex];
      return { ...prev, [qid]: next };
    });
  }, []);

  const togglePause = useCallback(() => setManualPause((p) => !p), []);

  /* ---------- 交卷 ---------- */

  const submit = useCallback(
    async (opts?: SubmitOptions) => {
      const current = attemptRef.current;
      if (!current || submitted.current || submittingLock.current) return;
      const list = questionsRef.current;
      if (!opts?.auto) {
        const unanswered = list.filter(
          (item) => !hasAnswer(byId[item.type]?.input, responsesRef.current[item.id]),
        ).length;
        if (unanswered > 0 && !window.confirm(`还有 ${unanswered} 题没有作答，确定交卷？`)) return;
      }
      submittingLock.current = true;
      setSubmitting(true);
      setError("");
      captureCurrentTime();
      try {
        await api.submitAttempt(current.id, {
          active_seconds: activeSeconds.current,
          answers: buildAnswers(),
        });
        submitted.current = true;
        if (draftTimer.current !== null) {
          window.clearTimeout(draftTimer.current);
          draftTimer.current = null;
        }
        sessionStorage.removeItem(`kaodian:attempt:${quizId}`);
        navigate(`/result/${current.id}`);
      } catch (e) {
        setError(errorText(e));
        submittingLock.current = false;
        setSubmitting(false);
      }
    },
    [byId, buildAnswers, captureCurrentTime, navigate, quizId],
  );

  submitRef.current = submit;

  const sendHelp = useCallback(
    async (text: string) => {
      const current = attemptRef.current;
      const question = questionsRef.current[indexRef.current];
      if (!current || !question || !text.trim()) return false;
      const spent = times.current[question.id] || 0;
      await api.sendHelp(
        current.id,
        question.id,
        `${text.trim()}\n\n[${question.outline_code} · ${label(question.type)} · 本题已用 ${spent}s]`,
      );
      return true;
    },
    [label],
  );

  const latestNote = useMemo(
    () => [...agentEvents].reverse().find((e) => e.kind === "note"),
    [agentEvents],
  );

  const answeredCount = questions.filter((item) =>
    hasAnswer(byId[item.type]?.input, responses[item.id]),
  ).length;

  return {
    attempt,
    loading: loading || typesLoading,
    error,
    setError,
    index,
    go,
    questions,
    q: questions[index],
    byId,
    label,
    responses,
    setResponse,
    revealed,
    reveal,
    toggleOption,
    flagged,
    toggleFlag,
    selfGrades,
    toggleSelfGrade,
    practice,
    limit,
    paused,
    togglePause,
    clock,
    submitting,
    submit,
    answeredCount,
    agentEvents,
    latestNote,
    sendHelp,
  };
}

export type QuizSession = ReturnType<typeof useQuizSession>;

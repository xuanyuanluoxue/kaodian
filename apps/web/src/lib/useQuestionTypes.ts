import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { QuestionType } from "../types";

/* 题型注册表：模块级缓存，整个会话只请求一次。
   请求失败时退回内置的 8 种，仅用于降级，页面里不再各自维护题型。 */
const FALLBACK: QuestionType[] = [
  { id: "single", label: "单选", input: "choice", grading: "auto", answer_schema: "letters", sort: 10 },
  { id: "multiple", label: "多选", input: "choice", grading: "auto", answer_schema: "letters", sort: 20 },
  { id: "judge", label: "判断", input: "judge", grading: "auto", answer_schema: "boolean", sort: 30 },
  { id: "fill", label: "填空", input: "text", grading: "auto", answer_schema: "blanks", sort: 40 },
  { id: "short", label: "简答", input: "text", grading: "agent", answer_schema: "rubric", sort: 50 },
  { id: "calc", label: "计算", input: "text", grading: "agent", answer_schema: "rubric", sort: 60 },
  { id: "code", label: "代码", input: "code", grading: "agent", answer_schema: "code", sort: 70 },
  { id: "essay", label: "论述", input: "text", grading: "agent", answer_schema: "rubric", sort: 80 },
];

let cache: Promise<QuestionType[]> | null = null;

function load(): Promise<QuestionType[]> {
  if (!cache) {
    cache = api
      .questionTypes()
      .then((types) => (Array.isArray(types) && types.length ? types : FALLBACK))
      .catch(() => FALLBACK);
  }
  return cache;
}

export function useQuestionTypes() {
  const [types, setTypes] = useState<QuestionType[] | null>(null);

  useEffect(() => {
    let alive = true;
    load().then((list) => {
      if (alive) setTypes(list);
    });
    return () => {
      alive = false;
    };
  }, []);

  const list = useMemo(() => types ?? [], [types]);
  const byId = useMemo(() => {
    const map: Record<string, QuestionType> = {};
    list.forEach((type) => {
      map[type.id] = type;
    });
    return map;
  }, [list]);
  const label = useCallback((id: string) => byId[id]?.label ?? id, [byId]);

  return { types: list, byId, label, loading: types === null };
}

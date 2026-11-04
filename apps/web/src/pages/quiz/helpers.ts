import type { Question } from "../../types";

/** 判分与「是否已答」的纯函数，QuestionView / QuizRail 共用。 */

export function normalize(value: unknown): string {
  return String(value ?? "")
    .normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/[，。；：、,.;:!?！？"'“”‘’（）()[\]【】]/g, "");
}

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const sa = new Set(a.map((x) => x.toUpperCase()));
  const sb = new Set(b.map((x) => x.toUpperCase()));
  return [...sa].every((x) => sb.has(x));
}

/** 练习模式的本地核对；信息不足时返回 null（不显示对错）。 */
export function localCorrect(q: Question, response: unknown, schema?: string): boolean | null {
  if (!q.answer) return null;
  if (schema === "blanks") {
    const accepted = q.answer.flat().map(normalize);
    return accepted.includes(normalize(response));
  }
  if (schema === "boolean") {
    const got = Array.isArray(response) ? response[0] : response;
    return normalize(got) === normalize(q.answer[0]);
  }
  if (schema === "letters") {
    const got = Array.isArray(response) ? response.map(String) : [String(response)];
    return sameSet(got, q.answer.flat().map(String));
  }
  return null;
}

export function hasAnswer(input: string | undefined, response: unknown): boolean {
  if (input === "text" || input === "code") {
    return typeof response === "string" && response.trim().length > 0;
  }
  if (input === "choice" || input === "judge") return Array.isArray(response) && response.length > 0;
  // 未知题型：字符串或数组都算已作答
  if (typeof response === "string") return response.trim().length > 0;
  return Array.isArray(response) && response.length > 0;
}

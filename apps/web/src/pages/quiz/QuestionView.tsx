import { GroupMaterial } from "../../components/GroupMaterial";
import { MathText } from "../../components/MathText";
import { QuestionMedia } from "../../components/QuestionMedia";
import { LETTERS } from "../../types";
import type { Question, QuestionGroup, QuestionType } from "../../types";
import { localCorrect } from "./helpers";

/* 单题渲染：材料 / 题干 / 媒体 / 选项 / 填空 / 主观题 / 自评 / 练习模式反馈。 */

interface Props {
  question: Question;
  /** 当前题所属的材料组（材料题）。 */
  group?: QuestionGroup | null;
  meta?: QuestionType;
  response: unknown;
  selfGrade: number[];
  revealed: boolean;
  practice: boolean;
  onResponse: (value: unknown) => void;
  onToggleOption: (letter: string) => void;
  onReveal: () => void;
  onToggleSelfGrade: (pointIndex: number) => void;
  /** 填空框里按回车：练习模式核对，否则下一题。 */
  onEnter: () => void;
}

export function QuestionView({
  question,
  group,
  meta,
  response,
  selfGrade,
  revealed,
  practice,
  onResponse,
  onToggleOption,
  onReveal,
  onToggleSelfGrade,
  onEnter,
}: Props) {
  const q = question;
  const input = meta?.input;
  const schema = meta?.answer_schema;
  const subjective = meta?.grading === "agent";
  const multiChoice = q.type === "multiple";
  const correct = practice ? localCorrect(q, response, schema) : null;
  const isRevealed = practice && (revealed || correct === true);
  const rubric = q.rubric || [];
  const selfScore = selfGrade.reduce((sum, i) => sum + (rubric[i]?.score || 0), 0);
  const optionValues = input === "judge" ? ["true", "false"] : (q.options || []).map((_, i) => LETTERS[i]);
  const textValue = typeof response === "string" ? response : "";

  return (
    <>
      <GroupMaterial group={group} />
      <article className="question-card">
          <div className="question-stem">
            <MathText text={q.stem} />
          </div>

          <QuestionMedia media={q.media} />

        {input === "text" && schema === "blanks" && (
          <input
            className="answer-input"
            aria-label="答案"
            placeholder="填答案，回车下一题"
            value={textValue}
            onChange={(e) => onResponse(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onEnter();
              }
            }}
          />
        )}

        {input === "judge" && (
          <div className="options judge-options" role="group" aria-label="判断选项">
            {["对", "错"].map((text, i) => {
              const value = optionValues[i];
              const picked = Array.isArray(response) && (response as string[])[0] === value;
              const showCorrect = isRevealed && q.answer?.[0] === value;
              const showWrong = isRevealed && picked && q.answer?.[0] !== value;
              return (
                <button
                  key={value}
                  type="button"
                  aria-pressed={!!picked}
                  className={`option ${picked ? "picked" : ""} ${showCorrect ? "correct" : ""} ${showWrong ? "wrong" : ""}`}
                  onClick={() => onToggleOption(i === 0 ? "A" : "B")}
                >
                  <span className="option-key">{i === 0 ? "1" : "2"}</span>
                  {text}
                </button>
              );
            })}
          </div>
        )}

        {input === "choice" && q.options && (
          <div className="options" role="group" aria-label="选项">
            {q.options.map((opt, i) => {
              const letter = LETTERS[i];
              const picked = Array.isArray(response) && (response as string[]).includes(letter);
              const showCorrect = isRevealed && !!q.answer?.includes(letter);
              const showWrong = isRevealed && picked && !q.answer?.includes(letter);
              return (
                <button
                  key={letter}
                  type="button"
                  aria-pressed={!!picked}
                  className={`option ${picked ? "picked" : ""} ${showCorrect ? "correct" : ""} ${showWrong ? "wrong" : ""}`}
                  onClick={() => onToggleOption(letter)}
                >
                  <span className="option-key">{letter}</span>
                  <span>
                    <MathText text={opt} />
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {practice &&
          meta?.grading === "auto" &&
          (multiChoice || schema === "blanks") &&
          !revealed && (
            <button className="btn btn-ghost check-btn" onClick={onReveal}>
              核对本题
            </button>
          )}

        {subjective && (
          <>
            <div className="answer-box">
              <label htmlFor={`ans-${q.id}`}>
                你的解答 <span className="muted small">· Agent 会读这段来评分</span>
              </label>
              <textarea
                id={`ans-${q.id}`}
                rows={5}
                value={textValue}
                onChange={(e) => onResponse(e.target.value)}
                placeholder={
                  input === "code"
                    ? "贴出你的代码；写清思路和边界情况。"
                    : "写出完整解答：关键步骤、依据和最终结论。公式可以用 $...$。"
                }
              />
            </div>
            <div className="self-grade">
              <div className="self-grade-head">
                <b>自评</b>
                <span className="muted small">可选，供 Agent 参考</span>
                <span className="self-score">
                  {selfScore} / {q.score}
                </span>
              </div>
              <ul>
                {rubric.map((point, i) => (
                  <li key={i}>
                    <label>
                      <input
                        type="checkbox"
                        checked={selfGrade.includes(i)}
                        onChange={() => onToggleSelfGrade(i)}
                      />
                      <span>{point.point}</span>
                      <b>{point.score} 分</b>
                    </label>
                  </li>
                ))}
              </ul>
              {!rubric.length && selfGrade.length > 0 && (
                <p className="muted small">已保存自评（{selfGrade.length} 项），刷新后 rubric 由服务端恢复前仍可交卷。</p>
              )}
              <details>
                <summary>参考答案</summary>
                <pre className="reference">{q.reference_answer}</pre>
              </details>
            </div>
          </>
        )}

        {!meta && (
          <div className="answer-box">
            <label htmlFor={`ans-${q.id}`}>你的答案</label>
            <textarea
              id={`ans-${q.id}`}
              rows={5}
              value={textValue}
              onChange={(e) => onResponse(e.target.value)}
              placeholder="当前前端未适配该题型，答案仍会提交。"
            />
          </div>
        )}

        {meta && input === "text" && schema !== "blanks" && !subjective && (
          <div className="answer-box">
            <label htmlFor={`ans-${q.id}`}>你的答案</label>
            <textarea
              id={`ans-${q.id}`}
              rows={5}
              value={textValue}
              onChange={(e) => onResponse(e.target.value)}
              placeholder="写出你的答案，提交后统一判分。"
            />
          </div>
        )}

        {practice && isRevealed && correct !== null && (
          <div className={`feedback ${correct ? "ok" : "bad"}`}>
            <b>{correct ? "答对了" : "答错了"}</b>
            <p>
              <MathText text={q.explanation || ""} />
            </p>
            {q.reference_answer && (
              <details>
                <summary>参考答案</summary>
                <pre className="reference">{q.reference_answer}</pre>
              </details>
            )}
          </div>
        )}
      </article>
    </>
  );
}

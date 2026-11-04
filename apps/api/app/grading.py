from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from .question_types import get_type, needs_rubric, type_ids

_LETTERS = "ABCDEFGH"


def normalize(text: object) -> str:
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).strip().lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[，。；：、,.;:!?！？\"'“”‘’（）()\[\]【】]", "", s)
    return s


def fingerprint(stem: str) -> str:
    return hashlib.sha1(normalize(stem).encode("utf-8")).hexdigest()[:20]


def _answer_set(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value.strip().upper()}
    return {str(v).strip().upper() for v in value}


def _literal(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _score(ok: bool, max_score: float, detail: dict | None = None) -> dict:
    return {
        "correct": ok,
        "score": max_score if ok else 0.0,
        "max_score": max_score,
        "detail": detail or {},
    }


def _grade_letters(answer: object, response: object, max_score: float) -> dict:
    got = _answer_set(response)
    want = _answer_set(answer)
    return _score(got == want and bool(want), max_score)


def _grade_boolean(answer: object, response: object, max_score: float) -> dict:
    raw = response[0] if isinstance(response, list) and response else response
    got = normalize(raw)
    if got in {"true", "t", "1", "对", "正确", "是"}:
        got = "true"
    elif got in {"false", "f", "0", "错", "错误", "否"}:
        got = "false"
    want = _answer_set(answer)
    expected = next(iter(want), "")
    return _score(got == normalize(expected), max_score)


def _grade_blanks(answer: object, response: object, max_score: float, partial: bool) -> dict:
    """answer 支持两种形态：
    - ["答案1", "答案2"]：单空，任一同义答案算对
    - [["a", "b"], ["c"]]：多空，每空一组可接受答案
    """
    accepted = answer if isinstance(answer, list) else [answer]
    multi = bool(accepted) and all(isinstance(a, list) for a in accepted)
    if not multi:
        got = normalize(response)
        ok = bool(got) and any(got == normalize(a) for a in accepted)
        return _score(ok, max_score)

    replies = response if isinstance(response, list) else [response]
    total = len(accepted)
    hits = 0
    for i, choices in enumerate(accepted):
        got = normalize(replies[i] if i < len(replies) else "")
        if got and any(got == normalize(c) for c in choices):
            hits += 1
    if partial:
        score = round(max_score * hits / total, 2) if total else 0.0
        return {"correct": hits == total, "score": score, "max_score": max_score,
                "detail": {"hits": hits, "total": total}}
    return _score(hits == total, max_score, {"hits": hits, "total": total})


def grade(question: dict, response: object, self_grade: object = None) -> dict:
    """按题型注册表的 answer_schema 判分；agent 题型返回待评分。"""
    qtype = question["type"]
    spec = get_type(qtype) or {}
    max_score = float(question.get("score") or 1)
    answer = _literal(question.get("answer"))
    rubric = _literal(question.get("rubric")) or []
    schema = spec.get("answer_schema")

    if spec.get("grading") == "agent" or schema in {"rubric", "code", "text"}:
        if needs_rubric(qtype):
            picked: list[int] = []
            if isinstance(self_grade, list):
                picked = [int(x) for x in self_grade
                          if isinstance(x, (int, float, str)) and str(x).isdigit()]
            elif isinstance(self_grade, dict):
                picked = [int(k) for k, v in self_grade.items() if v and str(k).isdigit()]
            earned = sum(float(rubric[i].get("score", 0)) for i in picked if 0 <= i < len(rubric))
            earned = min(earned, max_score)
            return {
                "correct": earned >= max_score * 0.6 if max_score else None,
                "score": round(earned, 2),
                "max_score": max_score,
                "detail": {"picked": picked},
            }
        return {"correct": None, "score": None, "max_score": max_score, "detail": {}}

    if schema == "letters":
        return _grade_letters(answer, response, max_score)
    if schema == "boolean":
        return _grade_boolean(answer, response, max_score)
    if schema == "blanks":
        return _grade_blanks(answer, response, max_score, bool(spec.get("allow_partial")))
    return {"correct": None, "score": None, "max_score": max_score, "detail": {}}


def validate_question(payload: dict, outline: dict[str, str]) -> list[str]:
    """outline: code -> subject_id"""
    errors: list[str] = []
    qtype = payload.get("type")
    spec = get_type(qtype) if isinstance(qtype, str) else None
    if not spec:
        errors.append(f"type 必须是 {type_ids()} 之一")
        return errors

    code = payload.get("outline_code")
    if not code:
        errors.append("outline_code 必填")
    elif code not in outline:
        errors.append(f"outline_code {code} 不在大纲里")
    elif payload.get("subject_id") and payload["subject_id"] != outline[code]:
        errors.append(f"outline_code {code} 属于 {outline[code]}，与 subject_id 不符")

    stem = (payload.get("stem") or "").strip()
    if len(stem) < 5:
        errors.append("stem 太短")
    explanation = (payload.get("explanation") or "").strip()
    if len(explanation) < 10:
        errors.append("explanation 至少 10 个字")
    difficulty = payload.get("difficulty", 2)
    if not isinstance(difficulty, int) or not 1 <= difficulty <= 5:
        errors.append("difficulty 必须是 1-5 的整数")

    options = payload.get("options") or []
    answer = payload.get("answer")
    schema = spec.get("answer_schema")

    if spec.get("input") == "choice":
        lo = int(spec.get("min_options", 2))
        hi = int(spec.get("max_options", 8))
        if not isinstance(options, list) or not lo <= len(options) <= hi:
            errors.append(f"options 必须是 {lo}-{hi} 个选项")
        elif len({normalize(o) for o in options}) != len(options):
            errors.append("options 有重复项")
        elif any(not str(o).strip() for o in options):
            errors.append("options 不能有空项")

    if schema == "letters":
        if not isinstance(answer, list) or not answer:
            errors.append("answer 必须是非空数组")
        else:
            want = _answer_set(answer)
            if qtype == "single":
                if len(want) != 1:
                    errors.append("单选题只能有 1 个答案")
                elif isinstance(options, list) and want - set(_LETTERS[: len(options)]):
                    errors.append("单选题答案超出选项范围")
            elif qtype == "multiple":
                if len(want) < 2:
                    errors.append("多选题至少 2 个答案")
                elif isinstance(options, list) and want == set(_LETTERS[: len(options)]):
                    errors.append("多选题答案不能等于全部选项")
                elif isinstance(options, list) and want - set(_LETTERS[: len(options)]):
                    errors.append("多选题答案超出选项范围")

    if schema == "boolean":
        if not isinstance(answer, list) or not answer:
            errors.append("判断题 answer 必须是非空数组")
        elif _answer_set(answer) - {"TRUE", "FALSE"}:
            errors.append('判断题答案只能是 ["true"] 或 ["false"]')

    if schema == "blanks":
        if not isinstance(answer, list) or not answer:
            errors.append("填空题 answer 必须是非空数组")
        elif all(isinstance(a, list) for a in answer):
            if any(not a or any(not str(x).strip() for x in a) for a in answer):
                errors.append("多空填空每空都要有非空答案")
        elif any(not str(a).strip() for a in answer):
            errors.append("填空题 answer 不能有空项")

    if spec.get("input") == "code":
        language = payload.get("language") or spec.get("language")
        if not isinstance(language, str) or not language.strip():
            errors.append("代码题必须有 language")

    if needs_rubric(qtype):
        if not (payload.get("reference_answer") or "").strip():
            errors.append("主观题必须有 reference_answer")
        rubric = payload.get("rubric") or []
        if not isinstance(rubric, list) or not rubric:
            errors.append("主观题必须有 rubric 评分点")
        else:
            for i, point in enumerate(rubric):
                if not str(point.get("point", "")).strip():
                    errors.append(f"rubric[{i}] 缺少 point")
                if not isinstance(point.get("score", 0), (int, float)) or point.get("score", 0) <= 0:
                    errors.append(f"rubric[{i}] score 必须大于 0")
            total = sum(float(p.get("score", 0)) for p in rubric)
            score = payload.get("score", total)
            if abs(total - float(score)) > 1e-6:
                errors.append(f"rubric 总分 {total} 与 score {score} 不一致")
    return errors

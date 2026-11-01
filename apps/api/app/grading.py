from __future__ import annotations

import hashlib
import json
import re
import unicodedata

TYPES = {"single", "multiple", "judge", "fill", "short", "calc", "code", "essay"}
OBJECTIVE = {"single", "multiple", "judge", "fill"}
SUBJECTIVE = {"short", "calc", "code", "essay"}
TYPE_LABEL = {
    "single": "单选", "multiple": "多选", "judge": "判断", "fill": "填空",
    "short": "简答", "calc": "计算", "code": "编程", "essay": "写作",
}
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


def grade(question: dict, response: object, self_grade: object = None) -> dict:
    """返回 {correct, score, max_score, detail}。主观题以自评得分点为准。"""
    qtype = question["type"]
    max_score = float(question.get("score") or 1)
    answer = _literal(question.get("answer"))
    rubric = _literal(question.get("rubric")) or []

    if qtype in SUBJECTIVE:
        picked: list[int] = []
        if isinstance(self_grade, list):
            picked = [int(x) for x in self_grade if isinstance(x, (int, float, str)) and str(x).isdigit()]
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

    if qtype == "fill":
        accepted = answer if isinstance(answer, list) else [answer]
        got = normalize(response)
        ok = bool(got) and any(got == normalize(a) for a in accepted)
        return {"correct": ok, "score": max_score if ok else 0.0, "max_score": max_score, "detail": {}}

    if qtype == "judge":
        raw = response
        if isinstance(raw, list) and raw:
            raw = raw[0]
        got = normalize(raw)
        if got in {"true", "t", "1", "对", "正确", "是"}:
            got = "true"
        elif got in {"false", "f", "0", "错", "错误", "否"}:
            got = "false"
        ok = got == normalize((answer or [""])[0])
        return {"correct": ok, "score": max_score if ok else 0.0, "max_score": max_score, "detail": {}}

    got = _answer_set(response)
    want = _answer_set(answer)
    ok = got == want and bool(want)
    return {"correct": ok, "score": max_score if ok else 0.0, "max_score": max_score, "detail": {}}


def validate_question(payload: dict, outline: dict[str, str]) -> list[str]:
    """outline: code -> subject_id"""
    errors: list[str] = []
    qtype = payload.get("type")
    code = payload.get("outline_code")
    if qtype not in TYPES:
        errors.append(f"type 必须是 {sorted(TYPES)} 之一")
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
    if not isinstance(payload.get("difficulty", 2), int) or not 1 <= payload.get("difficulty", 2) <= 5:
        errors.append("difficulty 必须是 1-5 的整数")

    options = payload.get("options") or []
    answer = payload.get("answer")
    if qtype in {"single", "multiple", "judge"}:
        if qtype != "judge":
            if not isinstance(options, list) or not 2 <= len(options) <= 8:
                errors.append("options 必须是 2-8 个选项")
            elif len({normalize(o) for o in options}) != len(options):
                errors.append("options 有重复项")
            elif any(not str(o).strip() for o in options):
                errors.append("options 不能有空项")
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
            elif qtype == "judge":
                if want - {"TRUE", "FALSE"}:
                    errors.append('判断题答案只能是 ["true"] 或 ["false"]')

    if qtype == "fill":
        if not isinstance(answer, list) or not answer or any(not str(a).strip() for a in answer):
            errors.append("填空题 answer 必须是非空字符串数组")

    if qtype in SUBJECTIVE:
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
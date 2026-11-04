from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import db

FALLBACK: list[dict[str, Any]] = [
    {"id": "single", "label": "单选", "input": "choice", "grading": "auto",
     "answer_schema": "letters", "min_options": 2, "max_options": 8, "sort": 10},
    {"id": "multiple", "label": "多选", "input": "choice", "grading": "auto",
     "answer_schema": "letters", "min_options": 2, "max_options": 8, "sort": 20},
    {"id": "judge", "label": "判断", "input": "judge", "grading": "auto",
     "answer_schema": "boolean", "sort": 30},
    {"id": "fill", "label": "填空", "input": "text", "grading": "auto",
     "answer_schema": "blanks", "sort": 40},
    {"id": "short", "label": "简答", "input": "text", "grading": "agent",
     "answer_schema": "rubric", "requires_rubric": True, "sort": 50},
    {"id": "calc", "label": "计算", "input": "text", "grading": "agent",
     "answer_schema": "rubric", "requires_rubric": True, "sort": 60},
    {"id": "code", "label": "代码", "input": "code", "grading": "agent",
     "answer_schema": "code", "requires_rubric": True, "language": "c", "sort": 70},
    {"id": "essay", "label": "论述", "input": "text", "grading": "agent",
     "answer_schema": "rubric", "requires_rubric": True, "sort": 80},
]


def load_types() -> list[dict[str, Any]]:
    """题型注册表：config/question_types.json 是唯一来源，缺失时用内置默认。"""
    path: Path = db.config_dir() / "question_types.json"
    if not path.is_file():
        return sorted(FALLBACK, key=lambda t: t.get("sort", 0))
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError(f"{path} 必须是非空数组")
    seen: set[str] = set()
    for i, item in enumerate(data):
        if not isinstance(item, dict) or not item.get("id"):
            raise ValueError(f"{path}[{i}] 缺少 id")
        if item["id"] in seen:
            raise ValueError(f"{path} 题型 id 重复：{item['id']}")
        seen.add(item["id"])
        for key in ("label", "input", "grading", "answer_schema"):
            if not item.get(key):
                raise ValueError(f"{path}[{i}] 缺少 {key}")
    return sorted(data, key=lambda t: (t.get("sort", 1000), t["id"]))


def type_map() -> dict[str, dict[str, Any]]:
    return {t["id"]: t for t in load_types()}


def get_type(type_id: str) -> dict[str, Any] | None:
    return type_map().get(type_id)


def type_ids(*, grading: str | None = None, objective: bool | None = None) -> list[str]:
    out = []
    for t in load_types():
        if grading and t["grading"] != grading:
            continue
        if objective is not None and (t["grading"] == "auto") != objective:
            continue
        out.append(t["id"])
    return out


def is_objective(type_id: str) -> bool:
    t = get_type(type_id)
    return bool(t and t["grading"] == "auto")


def needs_rubric(type_id: str) -> bool:
    t = get_type(type_id)
    return bool(t and (t.get("requires_rubric") or t["answer_schema"] == "rubric"))


def agent_graded_ids() -> list[str]:
    return type_ids(grading="agent")

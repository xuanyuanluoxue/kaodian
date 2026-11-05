from __future__ import annotations

import asyncio
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import content as content_packs
from . import db as database
from . import paths
from . import profile as profiles
from . import question_types
from .blocks import validate_blocks, validate_layout, validate_theme
from .grading import fingerprint, grade, validate_media, validate_question
from .review import apply_result

ROOT = Path(__file__).resolve().parents[3]
WEB_DIST = ROOT / "apps" / "web" / "dist"


# ---------------------------------------------------------------- models

class QuestionIn(BaseModel):
    outline_code: str
    outline_codes: list[str] = Field(default_factory=list)
    subject_id: str | None = None
    type: str
    stem: str
    options: list[str] | None = None
    answer: list[Any] | None = None
    explanation: str = ""
    reference_answer: str | None = None
    rubric: list[dict] | None = None
    score: float = 1
    difficulty: int = 2
    source: dict | None = None
    tags: list[str] = Field(default_factory=list)
    verified: bool = False
    language: str | None = None
    group_id: str | None = None
    group_position: int = 0
    media: list[dict] = Field(default_factory=list)
    client_ref: str | None = None


class QuestionGroupIn(BaseModel):
    subject_id: str | None = None
    title: str | None = None
    material: str = ""
    media: list[dict] = Field(default_factory=list)


class QuestionGroupPatch(BaseModel):
    subject_id: str | None = None
    title: str | None = None
    material: str | None = None
    media: list[dict] | None = None


class BatchIn(BaseModel):
    questions: list[QuestionIn]


class Filters(BaseModel):
    subject_id: str | None = None
    codes: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    exclude_days: int = 0
    verified_only: bool = False


class QuizIn(BaseModel):
    title: str | None = None
    mode: Literal["practice", "exam"] = "practice"
    time_limit: int | None = None
    count: int = Field(default=10, ge=1, le=100)
    agent_session_id: str | None = None
    filters: Filters = Field(default_factory=Filters)
    question_ids: list[str] = Field(default_factory=list)


class AttemptIn(BaseModel):
    quiz_id: str


class AnswerIn(BaseModel):
    question_id: str
    response: Any | None = None
    time_spent: int = 0
    flagged: bool = False
    self_grade: Any | None = None


class PatchIn(BaseModel):
    active_seconds: int | None = None
    answers: list[AnswerIn] = Field(default_factory=list)


class SubmitIn(BaseModel):
    active_seconds: int = 0
    answers: list[AnswerIn] = Field(default_factory=list)


class ActivityIn(BaseModel):
    page_id: str | None = None
    seconds: int = Field(ge=1, le=600)
    source: Literal["page", "code"] = "page"


class AgentSessionIn(BaseModel):
    title: str = Field(default="未命名会话", max_length=100)


class AgentEventIn(BaseModel):
    session_id: str
    kind: Literal["note"] = "note"
    role: Literal["agent"] = "agent"
    body: str = Field(min_length=1, max_length=2000)


class HelpIn(BaseModel):
    attempt_id: str
    question_id: str | None = None
    body: str = Field(min_length=1, max_length=2000)


class QuestionReviewIn(BaseModel):
    ids: list[str]
    decision: Literal["approve", "reject"]
    note: str | None = None


class GradeIn(BaseModel):
    score: float = Field(ge=0)
    feedback: str = ""
    correct: bool | None = None


class CodeRunIn(BaseModel):
    code: str = Field(min_length=1, max_length=20000)
    stdin: str = Field(default="", max_length=10000)
    language: str = "c"


class PageIn(BaseModel):
    subject_id: str | None = None
    lesson_key: str | None = Field(default=None, max_length=20)
    title: str = Field(min_length=1, max_length=120)
    summary: str | None = None
    body: str = ""
    blocks: list[dict[str, Any]] | None = None
    layout: str = "article"
    theme: dict[str, Any] | None = None
    outline_codes: list[str] = Field(default_factory=list)
    kind: Literal["outline", "lesson", "daily", "note"] = "lesson"
    status: Literal["draft", "published", "archived"] = "published"
    sort_order: int = 1000


class PagePatch(BaseModel):
    lesson_key: str | None = Field(default=None, max_length=20)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    summary: str | None = None
    body: str | None = None
    blocks: list[dict[str, Any]] | None = None
    layout: str | None = None
    theme: dict[str, Any] | None = None
    outline_codes: list[str] | None = None
    kind: Literal["outline", "lesson", "daily", "note"] | None = None
    status: Literal["draft", "published", "archived"] | None = None
    sort_order: int | None = None


class ImportIn(BaseModel):
    format: str = "kaodian-export"
    version: int = database.SCHEMA_VERSION
    scope: Literal["content", "progress", "all"] = "content"
    overwrite: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class DraftIn(BaseModel):
    body: str | None = None
    blocks: list[dict[str, Any]] | None = None
    layout: str | None = None
    theme: dict[str, Any] | None = None
    base_version: int | None = None


class PublishIn(BaseModel):
    message: str | None = Field(default=None, max_length=200)
    commit: bool = False


class ProfileIn(BaseModel):
    target_exam: str | None = None
    target_date: str | None = None
    target_score: float | None = None
    targets: list[dict[str, Any]] | None = None
    exam_total: int | None = None
    subject_targets: dict[str, int] | None = None
    hard_lines: str | None = None
    plan_phase: str | None = None
    phase_start: str | None = None
    phase_end: str | None = None
    phase_daily_minutes: int | None = None
    phase_goal: str | None = None
    total_hours: int | None = None
    target_school: str | None = Field(default=None, max_length=100)
    target_major: str | None = Field(default=None, max_length=100)
    target_region: str | None = Field(default=None, max_length=50)
    backup_school: str | None = Field(default=None, max_length=100)
    backup_major: str | None = Field(default=None, max_length=100)
    exam_type: str | None = Field(default=None, max_length=100)
    current_education: str | None = Field(default=None, max_length=100)
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)
    daily_minutes: int | None = Field(default=None, ge=1, le=600)
    subjects: list[str] | None = None
    study_window: str | None = Field(default=None, max_length=200)
    constraints: str | None = Field(default=None, max_length=1000)
    strengths: str | None = Field(default=None, max_length=1000)
    weaknesses: str | None = Field(default=None, max_length=1000)
    motivation: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)
    ai_summary: str | None = Field(default=None, max_length=2000)
    preferred_tone: str | None = Field(default=None, max_length=200)
    preferred_examples: str | None = Field(default=None, max_length=200)
    source: Literal["user", "agent"] = "user"


# ---------------------------------------------------------------- helpers

def row_to_question(row: sqlite3.Row, reveal: bool = True,
                    conn: sqlite3.Connection | None = None) -> dict:
    def load(value):
        if value is None:
            return None
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value

    codes = None
    if conn is not None:
        codes = [
            r["outline_code"]
            for r in conn.execute(
                """SELECT outline_code FROM question_outline
                   WHERE question_id = ?
                   ORDER BY CASE WHEN outline_code = ? THEN 0 ELSE 1 END,
                            weight DESC, outline_code""",
                (row["id"], row["outline_code"]),
            )
        ]
    if not codes:
        codes = [row["outline_code"]]

    item = {
        "id": row["id"],
        "subject_id": row["subject_id"],
        "outline_code": row["outline_code"],
        "outline_codes": codes,
        "group_id": row["group_id"] if "group_id" in row.keys() else None,
        "group_position": row["group_position"] if "group_position" in row.keys() else 0,
        "type": row["type"],
        "stem": row["stem"],
        "options": load(row["options"]),
        "media": (load(row["media"]) if "media" in row.keys() else None) or [],
        "score": row["score"],
        "difficulty": row["difficulty"],
        "tags": load(row["tags"]) or [],
        "verified": bool(row["verified"]),
        "language": row["language"] if "language" in row.keys() else None,
        "status": row["status"] if "status" in row.keys() else "approved",
        "reviewed_at": row["reviewed_at"] if "reviewed_at" in row.keys() else None,
        "review_note": row["review_note"] if "review_note" in row.keys() else None,
        "source": load(row["source"]),
    }
    if reveal:
        item["answer"] = load(row["answer"])
        item["explanation"] = row["explanation"]
        item["reference_answer"] = row["reference_answer"]
        item["rubric"] = load(row["rubric"])
    return item


def group_dict(row: sqlite3.Row) -> dict:
    media = None
    if row["media"]:
        try:
            media = json.loads(row["media"])
        except (TypeError, json.JSONDecodeError):
            media = row["media"]
    return {
        "id": row["id"],
        "subject_id": row["subject_id"],
        "title": row["title"],
        "material": row["material"] or "",
        "media": media or [],
        "source_key": row["source_key"] if "source_key" in row.keys() else None,
        "created_at": row["created_at"],
    }


def page_dict(row: sqlite3.Row, full: bool = True) -> dict:
    blocks = _decode_json(row["blocks"]) if "blocks" in row.keys() else None
    theme = _decode_json(row["theme"]) if "theme" in row.keys() else None
    stored_format = row["format"] if "format" in row.keys() else None
    item = {
        "id": row["id"],
        "subject_id": row["subject_id"],
        "title": row["title"],
        "summary": row["summary"],
        "lesson_key": row["lesson_key"] if "lesson_key" in row.keys() else None,
        "outline_codes": json.loads(row["outline_codes"]) if row["outline_codes"] else [],
        "kind": row["kind"],
        "status": row["status"],
        "blocks": blocks,
        "layout": row["layout"] if "layout" in row.keys() else "article",
        "theme": theme,
        # 有 blocks 就是块页；旧数据没有 blocks 时沿用存储的 format。
        "format": "blocks" if blocks is not None else (stored_format or "markdown"),
        "sort_order": row["sort_order"] if "sort_order" in row.keys() else 1000,
        "file": row["file"] if "file" in row.keys() else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed": row["completed_at"] is not None if "completed_at" in row.keys() else False,
        "completed_at": row["completed_at"] if "completed_at" in row.keys() else None,
        "xp": row["xp"] if "xp" in row.keys() else 0,
    }
    if full:
        item["body"] = row["body"]
    else:
        body = row["body"] or ""
        item["excerpt"] = body[:180].replace("\n", " ")
    return item


def draft_dict(row: sqlite3.Row) -> dict:
    return {
        "page_id": row["page_id"],
        "body": row["body"],
        "blocks": _decode_json(row["blocks"]),
        "layout": row["layout"],
        "theme": _decode_json(row["theme"]),
        "version": row["version"],
        "updated_at": row["updated_at"],
    }


def draft_payload(conn: sqlite3.Connection, page_id: str) -> dict:
    page = conn.execute("SELECT * FROM page WHERE id = ?", (page_id,)).fetchone()
    if not page:
        raise HTTPException(404, "学习页不存在")
    draft = conn.execute(
        "SELECT * FROM page_draft WHERE page_id = ?", (page_id,)
    ).fetchone()
    return {
        "page": page_dict(page),
        "draft": draft_dict(draft) if draft else None,
    }


def _git_commit(content_dir: Path, file: str, message: str) -> bool:
    """在内容仓库提交单个文件；失败时说明文件已经写好。"""
    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            args, cwd=str(content_dir), capture_output=True, text=True,
        )

    added = run("git", "add", "--", file)
    if added.returncode != 0:
        detail = (added.stderr or added.stdout).strip()
        raise HTTPException(500, f"文件已写入，但 git add 失败：{detail}")
    committed = run("git", "commit", "-m", message)
    if committed.returncode != 0:
        detail = (committed.stderr or committed.stdout).strip()
        raise HTTPException(500, f"文件已写入，但 git commit 失败：{detail}")
    return True


def get_quiz(conn: sqlite3.Connection, quiz_id: str) -> dict:
    quiz = conn.execute("SELECT * FROM quiz WHERE id = ?", (quiz_id,)).fetchone()
    if not quiz:
        raise HTTPException(404, "练习单不存在")
    items = conn.execute(
        """SELECT q.* FROM quiz_item i JOIN question q ON q.id = i.question_id
           WHERE i.quiz_id = ? ORDER BY i.position""",
        (quiz_id,),
    ).fetchall()

    questions = [
        row_to_question(r, reveal=(quiz["mode"] == "practice"), conn=conn)
        for r in items
    ]

    groups: list[dict] = []
    group_ids = list(dict.fromkeys(q["group_id"] for q in questions if q["group_id"]))
    if group_ids:
        marks = ",".join("?" * len(group_ids))
        rows = conn.execute(
            f"SELECT * FROM question_group WHERE id IN ({marks})", group_ids
        ).fetchall()
        by_id = {row["id"]: group_dict(row) for row in rows}
        members: dict[str, list[str]] = {}
        for q in questions:
            if q["group_id"]:
                members.setdefault(q["group_id"], []).append(q["id"])
        for gid in group_ids:
            if gid not in by_id:
                continue
            groups.append({**by_id[gid], "question_ids": members.get(gid, [])})

    return {
        "id": quiz["id"],
        "title": quiz["title"],
        "mode": quiz["mode"],
        "time_limit": quiz["time_limit"],
        "agent_session_id": quiz["agent_session_id"],
        "created_at": quiz["created_at"],
        "question_count": len(items),
        "questions": questions,
        "groups": groups,
    }


def get_attempt(conn: sqlite3.Connection, attempt_id: str, reveal: bool = True) -> dict:
    row = conn.execute("SELECT * FROM attempt WHERE id = ?", (attempt_id,)).fetchone()
    if not row:
        raise HTTPException(404, "作答记录不存在")
    quiz = get_quiz(conn, row["quiz_id"])
    answers = {}
    for a in conn.execute("SELECT * FROM answer WHERE attempt_id = ?", (attempt_id,)):
        answers[a["question_id"]] = {
            "response": json.loads(a["response"]) if a["response"] else None,
            "correct": None if a["correct"] is None else bool(a["correct"]),
            "score": a["score"],
            "time_spent": a["time_spent"],
            "flagged": bool(a["flagged"]),
            "self_grade": json.loads(a["self_grade"]) if a["self_grade"] else None,
            "graded_by": a["graded_by"] if "graded_by" in a.keys() else None,
            "feedback": a["feedback"] if "feedback" in a.keys() else None,
        }
    return {
        "id": row["id"],
        "quiz_id": row["quiz_id"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "active_seconds": row["active_seconds"],
        "status": row["status"],
        "score": row["score"],
        "max_score": row["max_score"],
        "grading_status": row["grading_status"] if "grading_status" in row.keys() else "none",
        "quiz": quiz if reveal or row["status"] == "submitted" else {
            **quiz, "questions": [{k: v for k, v in q.items() if k in
                                   {"id", "subject_id", "outline_code", "outline_codes", "group_id",
                                    "group_position", "type", "stem", "options", "media",
                                    "score", "difficulty", "tags"}}
                                  for q in quiz["questions"]],
        },
        "answers": answers,
    }




def _diagnose(msg: str) -> tuple[str, str]:
    """把常见 gcc 诊断翻成「为什么错 / 怎么改」。"""
    if "invalid preprocessing directive" in msg:
        m = re.search(r"directive (#\w+)", msg)
        directive = m.group(1) if m else "这个指令"
        low = directive.lower()
        if "did you mean #include" in msg.lower() or (low.startswith("#incl") and low != "#include"):
            return (
                f"{directive} 不是合法的预处理指令，你是不是想写 #include？",
                "改成 #include <stdio.h>（拼写是 i-n-c-l-u-d-e）。",
            )
        return (
            f"{directive} 不是合法的预处理指令。",
            "常见指令只有 #include、#define、#if / #ifdef / #endif。",
        )
    if "expected" in msg and ";" in msg:
        return ("上一条语句少了分号，gcc 通常把错误指到下一行。", "在报错位置的上一行末尾补 ;。")
    if "implicit declaration of function" in msg:
        m = re.search(r"function ['‘]?(\w+)", msg)
        fn = m.group(1) if m else "该函数"
        if fn in {"printf", "scanf", "puts", "gets", "fgets"}:
            return (f"{fn} 没有声明：缺少 <stdio.h>。", "在文件开头加 #include <stdio.h>。")
        return (f"{fn} 在使用前没有声明。", "先定义函数，或包含对应头文件。")
    if "unknown type name" in msg:
        return ("类型名不认识。", "检查拼写（int/float/double/char），或包含定义它的头文件。")
    if "undeclared" in msg:
        return ("变量/函数没有声明就用了。", "检查拼写和大小写；变量要先定义。")
    if "expected declaration or statement at end of input" in msg:
        return ("括号没有闭合，通常是少了右花括号 }。", "数一数 { 和 } 是否成对。")
    if "missing terminating" in msg or "stray" in msg:
        return ("字符串或字符没有闭合，或混入了中文标点。", "检查引号是否成对，标点用英文半角。")
    if "format" in msg and "expects argument" in msg:
        return ("printf 的格式符和参数类型不匹配。", "int 用 %d，double 用 %f/%lf，char 用 %c。")
    if "too few arguments" in msg:
        return ("格式符比参数多。", "检查 printf 中 % 的数量与后面的变量是否一一对应。")
    if "undefined reference to" in msg:
        m = re.search(r"undefined reference to ['‘]?(\w+)", msg)
        fn = m.group(1) if m else "符号"
        if fn == "main":
            return ("链接器找不到 main 函数。", "检查是不是把 main 写成了 mian，或大小写不对。")
        return (f"链接器找不到 {fn} 的定义。", "检查函数是否只声明没定义，或缺少链接库。")
    if "expected expression" in msg:
        return ("表达式不完整。", "检查运算符两边是否都有值，括号是否成对。")
    return ("编译器在这一行发现了语法问题。", "对照报错行和上一行，检查分号、括号、引号、拼写。")


def explain_diagnostics(text: str) -> list[dict]:
    hints: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for line in text.splitlines():
        m = re.match(r"main\.c:(\d+):(\d+): (error|warning): (.+)", line)
        if not m:
            continue
        line_no, col, kind, msg = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
        key = (line_no, msg)
        if key in seen:
            continue
        seen.add(key)
        reason, fix = _diagnose(msg)
        hints.append({
            "line": line_no, "column": col, "kind": kind,
            "message": msg, "reason": reason, "fix": fix,
        })
        if len(hints) >= 8:
            break
    # 编译失败时只解释 error；warning 通常是被 error 连带出来的
    errors = [h for h in hints if h["kind"] == "error"]
    return (errors or hints)[:5]

def results_for(conn: sqlite3.Connection, attempt_id: str) -> list[dict]:
    items = conn.execute(
        """SELECT q.* FROM quiz_item i JOIN question q ON q.id = i.question_id
           JOIN attempt t ON t.quiz_id = i.quiz_id
           WHERE t.id = ? ORDER BY i.position""",
        (attempt_id,),
    ).fetchall()
    out = []
    for q in items:
        a = conn.execute(
            "SELECT * FROM answer WHERE attempt_id = ? AND question_id = ?", (attempt_id, q["id"])
        ).fetchone()
        out.append({
            "question": row_to_question(q, reveal=True, conn=conn),
            "response": json.loads(a["response"]) if a and a["response"] else None,
            "self_grade": json.loads(a["self_grade"]) if a and a["self_grade"] else None,
            "correct": None if not a or a["correct"] is None else bool(a["correct"]),
            "score": a["score"] if a else 0.0,
            "max_score": q["score"],
            "time_spent": a["time_spent"] if a else 0,
            "flagged": bool(a["flagged"]) if a else False,
            "graded_by": a["graded_by"] if a and "graded_by" in a.keys() else None,
            "feedback": a["feedback"] if a and "feedback" in a.keys() else None,
        })
    return out


def weak_for(results: list[dict]) -> list[dict]:
    weak: dict[str, int] = {}
    for r in results:
        if r["correct"] is False:
            code = r["question"]["outline_code"]
            weak[code] = weak.get(code, 0) + 1
    return [{"code": k, "wrong": v} for k, v in sorted(weak.items(), key=lambda x: -x[1])]

def upsert_answer(conn: sqlite3.Connection, attempt_id: str, a: AnswerIn) -> None:
    quiz = conn.execute("SELECT quiz_id FROM attempt WHERE id = ?", (attempt_id,)).fetchone()
    if not quiz:
        raise HTTPException(404, "作答记录不存在")
    belongs = conn.execute(
        "SELECT 1 FROM quiz_item WHERE quiz_id = ? AND question_id = ?",
        (quiz["quiz_id"], a.question_id),
    ).fetchone()
    if not belongs:
        raise HTTPException(422, "题目不在本次练习中")
    conn.execute(
        """INSERT INTO answer(attempt_id, question_id, response, time_spent, flagged, self_grade)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(attempt_id, question_id) DO UPDATE SET
             response=excluded.response, time_spent=excluded.time_spent,
             flagged=excluded.flagged, self_grade=excluded.self_grade""",
        (
            attempt_id, a.question_id,
            json.dumps(a.response, ensure_ascii=False) if a.response is not None else None,
            max(0, a.time_spent), 1 if a.flagged else 0,
            json.dumps(a.self_grade, ensure_ascii=False) if a.self_grade is not None else None,
        ),
    )


def add_agent_event(
    conn: sqlite3.Connection,
    session_id: str | None,
    kind: str,
    role: str,
    body: str | None = None,
    ref: str | None = None,
) -> int | None:
    if not session_id:
        return None
    cur = conn.execute(
        "INSERT INTO agent_event(session_id, kind, role, body, ref, created_at) VALUES (?,?,?,?,?,?)",
        (session_id, kind, role, body, ref, database.now_iso()),
    )
    return int(cur.lastrowid or 0)


def log_event(conn: sqlite3.Connection, attempt_id: str | None, kind: str, payload: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO event(attempt_id, kind, payload, at) VALUES (?,?,?,?)",
        (attempt_id, kind, json.dumps(payload or {}, ensure_ascii=False), database.now_iso()),
    )


# ---------------------------------------------------------------- export / import

_EXPORT_SPECS: dict[str, list[tuple[str, str, tuple[str, ...], str]]] = {
    "content": [
        ("subjects", "subject", (), "sort, id"),
        ("outline", "outline_node", (), "subject_id, sort, code"),
        ("groups", "question_group", ("media",), "created_at, id"),
        ("questions", "question",
         ("options", "answer", "rubric", "source", "tags", "media"), "created_at, id"),
        ("question_outline", "question_outline", (), "question_id, outline_code"),
        ("pages", "page", ("outline_codes", "blocks", "theme"),
         "subject_id, sort_order, created_at, id"),
    ],
    "progress": [
        ("page_progress", "page_progress", (), "page_id"),
        ("review", "review", (), "question_id"),
        ("study_time", "study_time", (), "day, source, ref"),
    ],
}


def _decode_json(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def export_data(conn: sqlite3.Connection, scope: Literal["content", "progress", "all"]) -> dict:
    scopes = ("content", "progress") if scope == "all" else (scope,)
    data: dict[str, list[dict]] = {}
    for name in scopes:
        for key, table, json_cols, order in _EXPORT_SPECS[name]:
            rows = []
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order}"):
                item = dict(row)
                for column in json_cols:
                    item[column] = _decode_json(item.get(column))
                rows.append(item)
            data[key] = rows
    return data


_REQUIRED = object()
_NOW = object()

# 导入只接受这些列；JSON 列在写入前统一编码，未知字段忽略。
_IMPORT_SPECS: dict[str, tuple[str, str, dict[str, Any], tuple[str, ...]]] = {
    "subjects": ("subject", "id", {
        "id": _REQUIRED, "name": _REQUIRED, "short": _REQUIRED,
        "exam_score": 100, "exam_minutes": 120, "color": None, "icon": None,
        "sort": 0, "code_language": None,
    }, ()),
    "outline": ("outline_node", "code", {
        "code": _REQUIRED, "subject_id": _REQUIRED, "section": None,
        "title": _REQUIRED, "requirement": None, "frequency": None, "hours": None,
        "stage": None, "assessment": None, "kind": "point", "sort": 0,
        "parent_code": None, "depth": 0,
    }, ()),
    "groups": ("question_group", "id", {
        "id": _REQUIRED, "subject_id": None, "title": None, "material": "",
        "media": None, "source_key": None, "created_at": _NOW,
    }, ("media",)),
    "questions": ("question", "id", {
        "id": _REQUIRED, "subject_id": None, "outline_code": _REQUIRED,
        "group_id": None, "group_position": 0, "type": _REQUIRED,
        "stem": _REQUIRED, "options": None, "answer": None, "explanation": "",
        "reference_answer": None, "rubric": None, "score": 1, "difficulty": 2,
        "source": None, "tags": None, "verified": 0, "language": None,
        "media": None, "status": "approved", "reviewed_at": None,
        "review_note": None, "fingerprint": None, "created_at": _NOW,
    }, ("options", "answer", "rubric", "source", "tags", "media")),
    "question_outline": ("question_outline", "question_id", {
        "question_id": _REQUIRED, "outline_code": _REQUIRED, "weight": 1,
    }, ()),
    "pages": ("page", "id", {
        "id": _REQUIRED, "subject_id": None, "title": _REQUIRED, "summary": None,
        "body": "", "blocks": None, "layout": "article", "theme": None,
        "format": "markdown", "lesson_key": None, "outline_codes": None,
        "kind": "lesson", "status": "published", "sort_order": 1000,
        "created_at": _NOW, "updated_at": _NOW,
    }, ("outline_codes", "blocks", "theme")),
    "page_progress": ("page_progress", "page_id", {
        "page_id": _REQUIRED, "completed_at": _NOW, "xp": 10,
    }, ()),
    "review": ("review", "question_id", {
        "question_id": _REQUIRED, "due_date": _REQUIRED, "interval_days": 0,
        "mastery": 0, "streak": 0, "lapses": 0, "last_result": None,
        "updated_at": _NOW,
    }, ()),
    "study_time": ("study_time", "day", {
        "day": _REQUIRED, "source": _REQUIRED, "ref": "", "seconds": 0,
        "updated_at": _NOW,
    }, ()),
}


def _json_text(value: Any) -> Any:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _row_values(table: str, index: int, row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise HTTPException(422, f"{table}[{index}] 必须是对象")
    _, _, columns, json_cols = _IMPORT_SPECS[table]
    values: dict[str, Any] = {}
    for column, default in columns.items():
        if column in row:
            value = row[column]
        elif default is _REQUIRED:
            raise HTTPException(422, f"{table}[{index}].{column} 不能为空")
        elif default is _NOW:
            value = database.now_iso()
        else:
            value = default
        if column in json_cols:
            value = _json_text(value)
        if column == "verified":
            value = 1 if value else 0
        values[column] = value
    return values


def _check_ref(conn: sqlite3.Connection, table: str, column: str, value: Any,
               label: str) -> None:
    if value is None:
        return
    if not conn.execute(f"SELECT 1 FROM {table} WHERE {column} = ?", (value,)).fetchone():
        raise HTTPException(422, f"{label}: {value} 不存在")


def _store_row(conn: sqlite3.Connection, table: str, pk: str,
               values: dict[str, Any], overwrite: bool) -> bool:
    exists = conn.execute(
        f"SELECT 1 FROM {table} WHERE {pk} = ?", (values[pk],)
    ).fetchone()
    if exists:
        if not overwrite:
            return False
        fields = [key for key in values if key != pk]
        if fields:
            conn.execute(
                f"UPDATE {table} SET {', '.join(f'{key} = ?' for key in fields)} WHERE {pk} = ?",
                [values[key] for key in fields] + [values[pk]],
            )
        return True
    columns = list(values)
    conn.execute(
        f"INSERT INTO {table}({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        [values[key] for key in columns],
    )
    return True


def _store_group(conn: sqlite3.Connection, values: dict[str, Any], overwrite: bool) -> bool:
    existing = conn.execute(
        "SELECT id FROM question_group WHERE id = ?", (values["id"],)
    ).fetchone()
    if not existing and values["source_key"] is not None:
        existing = conn.execute(
            "SELECT id FROM question_group WHERE source_key = ? AND subject_id IS ?",
            (values["source_key"], values["subject_id"]),
        ).fetchone()
    if existing:
        if not overwrite:
            return False
        fields = [key for key in values if key != "id"]
        conn.execute(
            f"UPDATE question_group SET {', '.join(f'{key} = ?' for key in fields)} WHERE id = ?",
            [values[key] for key in fields] + [existing["id"]],
        )
        return True
    return _store_row(conn, "question_group", "id", values, True)


def _store_question(conn: sqlite3.Connection, values: dict[str, Any], overwrite: bool,
                    index: int) -> bool:
    by_id = conn.execute(
        "SELECT id FROM question WHERE id = ?", (values["id"],)
    ).fetchone()
    by_fp = None
    if values["fingerprint"]:
        by_fp = conn.execute(
            "SELECT id FROM question WHERE fingerprint = ?", (values["fingerprint"],)
        ).fetchone()
    if by_id and by_fp and by_id["id"] != by_fp["id"]:
        raise HTTPException(
            422,
            f"questions[{index}].fingerprint 已被题目 {by_fp['id']} 占用",
        )
    existing = by_id or by_fp
    if existing:
        if not overwrite:
            return False
        fields = [key for key in values if key != "id"]
        conn.execute(
            f"UPDATE question SET {', '.join(f'{key} = ?' for key in fields)} WHERE id = ?",
            [values[key] for key in fields] + [existing["id"]],
        )
        return True
    return _store_row(conn, "question", "id", values, True)


def import_data(conn: sqlite3.Connection, body: ImportIn) -> dict:
    if body.format != "kaodian-export":
        raise HTTPException(422, "format 必须是 kaodian-export")
    if body.version < 1:
        raise HTTPException(422, f"version {body.version} 不合法")
    if body.version > database.SCHEMA_VERSION:
        raise HTTPException(
            422,
            f"导出文件版本 {body.version} 高于当前支持的 {database.SCHEMA_VERSION}",
        )
    if not isinstance(body.data, dict):
        raise HTTPException(422, "data 必须是对象")

    content_keys = ["subjects", "outline", "groups", "questions",
                    "question_outline", "pages"]
    progress_keys = ["page_progress", "review", "study_time"]
    if body.scope == "content":
        keys = content_keys
    elif body.scope == "progress":
        keys = progress_keys
    else:
        keys = content_keys + progress_keys

    imported = {key: 0 for key in keys}
    skipped = {key: 0 for key in keys}
    subjects_touched: set[str] = set()

    def rows_of(key: str) -> list:
        value = body.data.get(key, [])
        if value is None:
            return []
        if not isinstance(value, list):
            raise HTTPException(422, f"data.{key} 必须是数组")
        return value

    if "subjects" in keys:
        for index, row in enumerate(rows_of("subjects")):
            values = _row_values("subjects", index, row)
            if _store_row(conn, "subject", "id", values, body.overwrite):
                imported["subjects"] += 1
            else:
                skipped["subjects"] += 1

    if "outline" in keys:
        for index, row in enumerate(rows_of("outline")):
            values = _row_values("outline", index, row)
            _check_ref(conn, "subject", "id", values["subject_id"],
                       f"outline[{index}].subject_id")
            if _store_row(conn, "outline_node", "code", values, body.overwrite):
                imported["outline"] += 1
                subjects_touched.add(values["subject_id"])
            else:
                skipped["outline"] += 1
        for subject_id in subjects_touched:
            database._update_depths(conn, subject_id)

    if "groups" in keys:
        for index, row in enumerate(rows_of("groups")):
            values = _row_values("groups", index, row)
            _check_ref(conn, "subject", "id", values["subject_id"],
                       f"groups[{index}].subject_id")
            if _store_group(conn, values, body.overwrite):
                imported["groups"] += 1
            else:
                skipped["groups"] += 1

    if "questions" in keys:
        for index, row in enumerate(rows_of("questions")):
            values = _row_values("questions", index, row)
            label = f"questions[{index}]"
            if not values["subject_id"]:
                subject = conn.execute(
                    "SELECT subject_id FROM outline_node WHERE code = ?",
                    (values["outline_code"],),
                ).fetchone()
                if subject:
                    values["subject_id"] = subject["subject_id"]
            _check_ref(conn, "subject", "id", values["subject_id"],
                       f"{label}.subject_id")
            _check_ref(conn, "outline_node", "code", values["outline_code"],
                       f"{label}.outline_code")
            _check_ref(conn, "question_group", "id", values["group_id"],
                       f"{label}.group_id")
            if not values["fingerprint"]:
                values["fingerprint"] = fingerprint(values["stem"])
            if _store_question(conn, values, body.overwrite, index):
                imported["questions"] += 1
            else:
                skipped["questions"] += 1

    if "question_outline" in keys:
        for index, row in enumerate(rows_of("question_outline")):
            values = _row_values("question_outline", index, row)
            label = f"question_outline[{index}]"
            _check_ref(conn, "question", "id", values["question_id"],
                       f"{label}.question_id")
            _check_ref(conn, "outline_node", "code", values["outline_code"],
                       f"{label}.outline_code")
            exists = conn.execute(
                """SELECT 1 FROM question_outline
                   WHERE question_id = ? AND outline_code = ?""",
                (values["question_id"], values["outline_code"]),
            ).fetchone()
            if exists:
                if body.overwrite:
                    conn.execute(
                        """UPDATE question_outline SET weight = ?
                           WHERE question_id = ? AND outline_code = ?""",
                        (values["weight"], values["question_id"], values["outline_code"]),
                    )
                    imported["question_outline"] += 1
                else:
                    skipped["question_outline"] += 1
                continue
            conn.execute(
                """INSERT INTO question_outline(question_id, outline_code, weight)
                   VALUES (?,?,?)""",
                (values["question_id"], values["outline_code"], values["weight"]),
            )
            imported["question_outline"] += 1

    if "pages" in keys:
        for index, row in enumerate(rows_of("pages")):
            values = _row_values("pages", index, row)
            label = f"pages[{index}]"
            _check_ref(conn, "subject", "id", values["subject_id"],
                       f"{label}.subject_id")
            codes = _decode_json(values["outline_codes"]) or []
            if not isinstance(codes, list):
                raise HTTPException(422, f"{label}.outline_codes 必须是数组")
            for code in codes:
                _check_ref(conn, "outline_node", "code", code,
                           f"{label}.outline_codes")
            if values.get("blocks") is not None:
                values["format"] = "blocks"
            if _store_row(conn, "page", "id", values, body.overwrite):
                imported["pages"] += 1
            else:
                skipped["pages"] += 1

    if "page_progress" in keys:
        for index, row in enumerate(rows_of("page_progress")):
            values = _row_values("page_progress", index, row)
            label = f"page_progress[{index}]"
            if not conn.execute("SELECT 1 FROM page WHERE id = ?",
                                (values["page_id"],)).fetchone():
                # 进度依赖页面已存在；单独导入进度时跳过悬空记录。
                skipped["page_progress"] += 1
                continue
            if _store_row(conn, "page_progress", "page_id", values, body.overwrite):
                imported["page_progress"] += 1
            else:
                skipped["page_progress"] += 1

    if "review" in keys:
        for index, row in enumerate(rows_of("review")):
            values = _row_values("review", index, row)
            if not conn.execute("SELECT 1 FROM question WHERE id = ?",
                                (values["question_id"],)).fetchone():
                skipped["review"] += 1
                continue
            if _store_row(conn, "review", "question_id", values, body.overwrite):
                imported["review"] += 1
            else:
                skipped["review"] += 1

    if "study_time" in keys:
        for index, row in enumerate(rows_of("study_time")):
            values = _row_values("study_time", index, row)
            key = (values["day"], values["source"], values["ref"])
            exists = conn.execute(
                "SELECT 1 FROM study_time WHERE day = ? AND source = ? AND ref = ?", key
            ).fetchone()
            if exists:
                if body.overwrite:
                    conn.execute(
                        """UPDATE study_time SET seconds = ?, updated_at = ?
                           WHERE day = ? AND source = ? AND ref = ?""",
                        (values["seconds"], values["updated_at"], *key),
                    )
                    imported["study_time"] += 1
                else:
                    skipped["study_time"] += 1
                continue
            conn.execute(
                """INSERT INTO study_time(day, source, ref, seconds, updated_at)
                   VALUES (?,?,?,?,?)""",
                (values["day"], values["source"], values["ref"],
                 values["seconds"], values["updated_at"]),
            )
            imported["study_time"] += 1

    return {"imported": imported, "skipped": skipped}


# ---------------------------------------------------------------- app

def create_app(db_file: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.init_db(db_file)
        yield

    app = FastAPI(title="考点 Kaodian", version="0.1.0", lifespan=lifespan)
    app.state.db_file = db_file
    origins = [
        item.strip()
        for item in os.environ.get(
            "KAODIAN_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if item.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https:; media-src 'self' https:; font-src 'self' data:; connect-src 'self'; "
            "frame-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )
        return response

    @app.middleware("http")
    async def cache_policy(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith("/media/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith("/sandbox/"):
            response.headers["Cache-Control"] = "no-store"
        elif path.endswith("/stream"):
            # SSE：禁止代理缓存，但也不要 no-store（某些代理会直接断流）
            response.headers["Cache-Control"] = "no-cache"
        elif path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response

    def conn() -> sqlite3.Connection:
        c = database.connect(app.state.db_file)
        c.execute("PRAGMA foreign_keys = ON")
        return c

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": app.version, "schema_version": database.SCHEMA_VERSION}

    @app.get("/media/{pack_id}/{path:path}")
    def media(pack_id: str, path: str):
        """内容包素材：只读、只返回文件，禁止 ../ 逃逸。"""
        base = (paths.content_dir() / "packs" / pack_id / "assets").resolve()
        if not base.is_dir():
            raise HTTPException(404, "内容包或素材目录不存在")
        target = (base / path).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            raise HTTPException(404, "素材不存在")
        return FileResponse(
            target,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @app.get("/sandbox/{page_id}/{index}")
    def sandbox(page_id: str, index: int):
        """隔离实验页：独立响应 + 独立 CSP，只允许内联脚本，不能访问 API/Cookie。"""
        with conn() as c:
            row = c.execute("SELECT blocks FROM page WHERE id = ?", (page_id,)).fetchone()
        if not row or not row["blocks"]:
            raise HTTPException(404, "实验页不存在")
        try:
            blocks = json.loads(row["blocks"])
        except (TypeError, json.JSONDecodeError):
            raise HTTPException(404, "实验页不存在")
        if not isinstance(blocks, list) or not 0 <= index < len(blocks):
            raise HTTPException(404, "实验页不存在")
        block = blocks[index]
        if not isinstance(block, dict) or block.get("type") != "sandbox":
            raise HTTPException(404, "实验页不存在")
        html = block.get("html")
        if not isinstance(html, str):
            raise HTTPException(404, "实验页不存在")
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store",
                "X-Frame-Options": "SAMEORIGIN",
                "Content-Security-Policy": (
                    "default-src 'none'; script-src 'unsafe-inline'; "
                    "style-src 'unsafe-inline'; img-src 'self' data: https:; "
                    "media-src 'self' https:; font-src data:; connect-src 'none'; "
                    "frame-ancestors 'self'"
                ),
            },
        )

    @app.get("/api/subjects")
    def subjects():
        with conn() as c:
            rows = c.execute(
                """SELECT s.*, COUNT(n.code) AS node_count, COALESCE(SUM(n.hours),0) AS hours
                   FROM subject s LEFT JOIN outline_node n ON n.subject_id = s.id
                   GROUP BY s.id ORDER BY s.sort, s.id"""
            ).fetchall()
            counts = {r["subject_id"]: r["n"] for r in c.execute(
                "SELECT subject_id, COUNT(*) AS n FROM question GROUP BY subject_id")}
        return [{**dict(r), "question_count": counts.get(r["id"], 0)} for r in rows]

    @app.get("/api/question-types")
    def question_type_list():
        return question_types.load_types()

    @app.get("/api/outline")
    def outline(subject_id: str | None = None):
        sql = "SELECT * FROM outline_node"
        args: list = []
        if subject_id:
            sql += " WHERE subject_id = ?"
            args.append(subject_id)
        sql += " ORDER BY subject_id, sort"
        with conn() as c:
            rows = c.execute(sql, args).fetchall()
            counts = {r["outline_code"]: r["n"] for r in c.execute(
                "SELECT outline_code, COUNT(*) AS n FROM question GROUP BY outline_code")}
        return [{**dict(r), "question_count": counts.get(r["code"], 0)} for r in rows]

    # -------- questions

    @app.get("/api/questions")
    def list_questions(
        subject_id: str | None = None,
        code: str | None = None,
        type: str | None = None,
        status: str = "approved",
        limit: int = Query(50, ge=1, le=200),
    ):
        sql = "SELECT * FROM question WHERE 1=1"
        args: list = []
        if status != "all":
            sql += " AND status = ?"
            args.append(status)
        for column, value in (("subject_id", subject_id), ("type", type)):
            if value:
                sql += f" AND {column} = ?"
                args.append(value)
        if code:
            sql += (" AND (outline_code = ? OR EXISTS ("
                    "SELECT 1 FROM question_outline qo"
                    " WHERE qo.question_id = question.id AND qo.outline_code = ?))")
            args += [code, code]
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with conn() as c:
            return [row_to_question(r, conn=c) for r in c.execute(sql, args)]

    @app.post("/api/questions/validate")
    def validate(body: BatchIn):
        with conn() as c:
            outline = {r["code"]: r["subject_id"] for r in c.execute("SELECT code, subject_id FROM outline_node")}
        result = []
        for i, q in enumerate(body.questions):
            errors = validate_question(q.model_dump(), outline)
            result.append({"index": i, "ok": not errors, "errors": errors})
        return {"ok": all(r["ok"] for r in result), "results": result}

    @app.post("/api/questions/batch", status_code=201)
    def create_questions(body: BatchIn):
        with conn() as c:
            outline = {r["code"]: r["subject_id"] for r in c.execute("SELECT code, subject_id FROM outline_node")}
            groups = {
                r["id"]: r["subject_id"]
                for r in c.execute("SELECT id, subject_id FROM question_group")
            }
            errors = []
            for i, q in enumerate(body.questions):
                errs = validate_question(q.model_dump(), outline)
                if q.group_id:
                    if q.group_id not in groups:
                        errs.append(f"group_id {q.group_id} 不存在")
                    else:
                        subject_id = q.subject_id or outline.get(q.outline_code)
                        if groups[q.group_id] and groups[q.group_id] != subject_id:
                            errs.append(
                                f"group_id {q.group_id} 属于 {groups[q.group_id]}，"
                                f"与题目科目 {subject_id} 不符"
                            )
                if errs:
                    errors.append({"index": i, "errors": errs})
            if errors:
                raise HTTPException(422, detail={"message": "有题目未通过校验，整批未入库", "errors": errors})

            created, skipped = [], []
            for q in body.questions:
                fp = fingerprint(q.stem)
                subject_id = q.subject_id or outline[q.outline_code]
                qid = database.new_id("q")
                try:
                    c.execute(
                        """INSERT INTO question
                           (id, subject_id, outline_code, group_id, group_position, type, stem,
                            options, answer, explanation, reference_answer, rubric, score, difficulty,
                            source, tags, verified, language, media, status, fingerprint, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            qid, subject_id, q.outline_code, q.group_id, q.group_position,
                            q.type, q.stem,
                            json.dumps(q.options, ensure_ascii=False) if q.options is not None else None,
                            json.dumps(q.answer, ensure_ascii=False) if q.answer is not None else None,
                            q.explanation, q.reference_answer,
                            json.dumps(q.rubric, ensure_ascii=False) if q.rubric is not None else None,
                            q.score, q.difficulty,
                            json.dumps(q.source or {"kind": "ai"}, ensure_ascii=False),
                            json.dumps(q.tags, ensure_ascii=False),
                            1 if q.verified else 0, q.language,
                            json.dumps(q.media, ensure_ascii=False) if q.media else None,
                            "pending", fp, database.now_iso(),
                        ),
                    )
                except sqlite3.IntegrityError:
                    skipped.append(q.stem[:40])
                    continue
                linked = [q.outline_code]
                linked += [code for code in q.outline_codes if code not in linked]
                for code in linked:
                    c.execute(
                        "INSERT OR IGNORE INTO question_outline(question_id, outline_code) VALUES (?,?)",
                        (qid, code),
                    )
                created.append(qid)
            log_event(c, None, "questions.created", {"created": len(created), "skipped": len(skipped)})
        return {"created": len(created), "skipped": len(skipped), "ids": created}


    @app.post("/api/questions/review")
    def review_questions(body: QuestionReviewIn):
        if not body.ids:
            raise HTTPException(422, "ids 不能为空")
        status = "approved" if body.decision == "approve" else "rejected"
        with conn() as c:
            placeholders = ",".join("?" * len(body.ids))
            found = {r["id"] for r in c.execute(
                f"SELECT id FROM question WHERE id IN ({placeholders})", body.ids)}
            missing = [i for i in body.ids if i not in found]
            if missing:
                raise HTTPException(404, f"题目不存在：{', '.join(missing)}")
            c.execute(
                f"""UPDATE question SET status = ?, verified = ?, reviewed_at = ?, review_note = ?
                    WHERE id IN ({placeholders})""",
                [status, 1 if status == "approved" else 0, database.now_iso(), body.note, *body.ids],
            )
            log_event(c, None, "questions.reviewed", {"ids": body.ids, "status": status})
        return {"updated": len(body.ids), "status": status, "ids": body.ids}

    @app.get("/api/stats/library")
    def library_stats():
        with conn() as c:
            rows = c.execute("SELECT status, COUNT(*) AS n FROM question GROUP BY status").fetchall()
            by_type = c.execute(
                "SELECT type, COUNT(*) AS n FROM question WHERE status = 'approved' GROUP BY type"
            ).fetchall()
        counts = {r["status"]: r["n"] for r in rows}
        return {
            "total": sum(counts.values()),
            "approved": counts.get("approved", 0),
            "pending": counts.get("pending", 0),
            "rejected": counts.get("rejected", 0),
            "by_type": [dict(r) for r in by_type],
        }

    # -------- question groups（材料题 / 一拖多）

    @app.post("/api/question-groups", status_code=201)
    def create_question_group(body: QuestionGroupIn):
        errors = validate_media(body.media)
        if errors:
            raise HTTPException(422, "；".join(errors))
        with conn() as c:
            if body.subject_id and not c.execute(
                "SELECT 1 FROM subject WHERE id = ?", (body.subject_id,)
            ).fetchone():
                raise HTTPException(422, f"subject_id {body.subject_id} 不存在")
            gid = database.new_id("g")
            c.execute(
                """INSERT INTO question_group
                   (id, subject_id, title, material, media, source_key, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (gid, body.subject_id, body.title, body.material,
                 json.dumps(body.media, ensure_ascii=False) if body.media else None,
                 None, database.now_iso()),
            )
            row = c.execute("SELECT * FROM question_group WHERE id = ?", (gid,)).fetchone()
            return {**group_dict(row), "questions": []}

    @app.get("/api/question-groups")
    def list_question_groups(subject_id: str | None = None,
                             limit: int = Query(50, ge=1, le=200)):
        sql = """SELECT g.*, (SELECT COUNT(*) FROM question q WHERE q.group_id = g.id)
                        AS question_count
                 FROM question_group g WHERE 1=1"""
        args: list = []
        if subject_id:
            sql += " AND g.subject_id = ?"
            args.append(subject_id)
        sql += " ORDER BY g.created_at DESC LIMIT ?"
        args.append(limit)
        with conn() as c:
            return [
                {**group_dict(r), "question_count": r["question_count"]}
                for r in c.execute(sql, args)
            ]

    def read_group(conn: sqlite3.Connection, group_id: str) -> dict:
        row = conn.execute(
            "SELECT * FROM question_group WHERE id = ?", (group_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "材料组不存在")
        questions = conn.execute(
            """SELECT * FROM question
               WHERE group_id = ? ORDER BY group_position, created_at""",
            (group_id,),
        ).fetchall()
        return {
            **group_dict(row),
            "question_count": len(questions),
            "questions": [row_to_question(q, conn=conn) for q in questions],
        }

    @app.get("/api/question-groups/{group_id}")
    def get_question_group(group_id: str):
        with conn() as c:
            return read_group(c, group_id)

    @app.patch("/api/question-groups/{group_id}")
    def update_question_group(group_id: str, body: QuestionGroupPatch):
        data = body.model_dump(exclude_unset=True)
        with conn() as c:
            row = c.execute(
                "SELECT * FROM question_group WHERE id = ?", (group_id,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "材料组不存在")
            if not data:
                return read_group(c, group_id)
            if "subject_id" in data and data["subject_id"] and not c.execute(
                "SELECT 1 FROM subject WHERE id = ?", (data["subject_id"],)
            ).fetchone():
                raise HTTPException(422, f"subject_id {data['subject_id']} 不存在")
            if data.get("media") is not None:
                errors = validate_media(data["media"])
                if errors:
                    raise HTTPException(422, "；".join(errors))
                data["media"] = json.dumps(data["media"], ensure_ascii=False) if data["media"] else None
            fields = ", ".join(f"{k} = ?" for k in data)
            c.execute(f"UPDATE question_group SET {fields} WHERE id = ?",
                      [*data.values(), group_id])
            return read_group(c, group_id)

    @app.delete("/api/question-groups/{group_id}")
    def delete_question_group(group_id: str):
        with conn() as c:
            row = c.execute(
                "SELECT 1 FROM question_group WHERE id = ?", (group_id,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "材料组不存在")
            c.execute("DELETE FROM question_group WHERE id = ?", (group_id,))
        return {"ok": True}

    # -------- quizzes

    @app.get("/api/quizzes")
    def list_quizzes(limit: int = Query(20, ge=1, le=100)):
        with conn() as c:
            rows = c.execute(
                """SELECT q.*, (SELECT COUNT(*) FROM quiz_item i WHERE i.quiz_id = q.id) AS question_count
                   FROM quiz q ORDER BY q.created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    @app.post("/api/quizzes", status_code=201)
    def create_quiz(body: QuizIn):
        with conn() as c:
            if body.question_ids:
                placeholders = ",".join("?" * len(body.question_ids))
                rows = c.execute(
                    f"SELECT * FROM question WHERE id IN ({placeholders}) AND status = 'approved'",
                    body.question_ids,
                ).fetchall()
                by_id = {r["id"]: r for r in rows}
                rows = [by_id[i] for i in body.question_ids if i in by_id]
            else:
                sql = "SELECT q.* FROM question q WHERE q.status = 'approved'"
                args: list = []
                f = body.filters
                if f.subject_id:
                    sql += " AND q.subject_id = ?"
                    args.append(f.subject_id)
                if f.codes:
                    marks = ",".join("?" * len(f.codes))
                    sql += (
                        f" AND (q.outline_code IN ({marks}) OR EXISTS ("
                        f"SELECT 1 FROM question_outline qo"
                        f" WHERE qo.question_id = q.id AND qo.outline_code IN ({marks})))"
                    )
                    args += f.codes + f.codes
                if f.types:
                    sql += f" AND q.type IN ({','.join('?' * len(f.types))})"
                    args += f.types
                if f.verified_only:
                    sql += " AND q.verified = 1"
                if f.exclude_days > 0:
                    since = (datetime.now() - timedelta(days=f.exclude_days)).isoformat(timespec="seconds")
                    sql += """ AND q.id NOT IN (
                        SELECT a.question_id FROM answer a JOIN attempt t ON t.id = a.attempt_id
                        WHERE t.started_at >= ?)"""
                    args.append(since)
                rows = c.execute(sql, args).fetchall()
                rows = list(rows)
                random.shuffle(rows)
                rows = rows[: body.count]

            if not rows:
                raise HTTPException(422, detail={"message": "题库里没有符合条件的题目", "missing": body.count})

            qid = database.new_id("z")
            title = body.title or f"{len(rows)} 题 · {date.today().isoformat()}"
            limit = body.time_limit
            if limit is None and body.mode == "exam":
                limit = len(rows) * 90
            c.execute(
                "INSERT INTO quiz(id, title, mode, time_limit, agent_session_id, created_at) VALUES (?,?,?,?,?,?)",
                (qid, title, body.mode, limit, body.agent_session_id, database.now_iso()),
            )
            for pos, row in enumerate(rows):
                c.execute("INSERT INTO quiz_item(quiz_id, question_id, position) VALUES (?,?,?)",
                          (qid, row["id"], pos))
            log_event(c, None, "quiz.created", {"quiz_id": qid, "count": len(rows), "mode": body.mode})
            payload = get_quiz(c, qid)
        return payload

    @app.get("/api/quizzes/{quiz_id}")
    def read_quiz(quiz_id: str):
        c = conn()
        try:
            return get_quiz(c, quiz_id)
        finally:
            c.close()

    # -------- attempts

    @app.post("/api/attempts", status_code=201)
    def start_attempt(body: AttemptIn):
        with conn() as c:
            quiz = c.execute("SELECT * FROM quiz WHERE id = ?", (body.quiz_id,)).fetchone()
            if not quiz:
                raise HTTPException(404, "练习单不存在")
            aid = database.new_id("a")
            c.execute(
                "INSERT INTO attempt(id, quiz_id, started_at, active_seconds, status) VALUES (?,?,?,0,'active')",
                (aid, body.quiz_id, database.now_iso()),
            )
            log_event(c, aid, "attempt.started", {"quiz_id": body.quiz_id})
            add_agent_event(
                c, quiz["agent_session_id"], "started", "system",
                json.dumps({"attempt_id": aid, "quiz_title": quiz["title"]}, ensure_ascii=False), aid,
            )
            payload = get_attempt(c, aid, reveal=True)
        return payload

    @app.patch("/api/attempts/{attempt_id}")
    def patch_attempt(attempt_id: str, body: PatchIn):
        with conn() as c:
            row = c.execute("SELECT * FROM attempt WHERE id = ?", (attempt_id,)).fetchone()
            if not row:
                raise HTTPException(404, "作答记录不存在")
            if row["status"] != "active":
                raise HTTPException(409, "已交卷，不能再修改")
            for a in body.answers:
                upsert_answer(c, attempt_id, a)
            if body.active_seconds is not None:
                c.execute("UPDATE attempt SET active_seconds = ? WHERE id = ?",
                          (max(0, body.active_seconds), attempt_id))
            if body.answers:
                log_event(c, attempt_id, "answer.saved", {"count": len(body.answers)})
        return {"ok": True}

    @app.post("/api/attempts/{attempt_id}/submit")
    def submit_attempt(attempt_id: str, body: SubmitIn):
        with conn() as c:
            attempt = c.execute("SELECT * FROM attempt WHERE id = ?", (attempt_id,)).fetchone()
            if not attempt:
                raise HTTPException(404, "作答记录不存在")
            if attempt["status"] == "submitted":
                return get_attempt(c, attempt_id, reveal=True)

            for a in body.answers:
                upsert_answer(c, attempt_id, a)

            items = c.execute(
                """SELECT q.* FROM quiz_item i JOIN question q ON q.id = i.question_id
                   WHERE i.quiz_id = ? ORDER BY i.position""",
                (attempt["quiz_id"],),
            ).fetchall()
            total = 0.0
            max_total = 0.0
            pending_grading = 0
            results = []
            for q in items:
                a = c.execute("SELECT * FROM answer WHERE attempt_id = ? AND question_id = ?",
                              (attempt_id, q["id"])).fetchone()
                response = json.loads(a["response"]) if a and a["response"] else None
                self_grade = json.loads(a["self_grade"]) if a and a["self_grade"] else None
                subjective = not question_types.is_objective(q["type"])
                answered = (isinstance(response, str) and response.strip() != "") or bool(self_grade)

                if subjective and answered:
                    g = {"correct": None, "score": None, "max_score": float(q["score"])}
                    pending_grading += 1
                elif subjective:
                    g = {"correct": None, "score": 0.0, "max_score": float(q["score"])}
                else:
                    g = grade(dict(q), response, self_grade)
                    if response is None and self_grade is None:
                        g = {"correct": None, "score": 0.0, "max_score": g["max_score"]}

                if g["score"] is not None:
                    total += g["score"]
                max_total += g["max_score"]
                c.execute("UPDATE answer SET correct = ?, score = ? WHERE attempt_id = ? AND question_id = ?",
                          (None if g["correct"] is None else 1 if g["correct"] else 0, g["score"], attempt_id, q["id"]))
                if g["correct"] is not None and (response is not None or self_grade is not None):
                    apply_result(c, q["id"], g["correct"])
                results.append({
                    "question": row_to_question(q, reveal=True, conn=c),
                    "response": response,
                    "self_grade": self_grade,
                    "correct": g["correct"],
                    "score": g["score"],
                    "max_score": g["max_score"],
                    "pending": subjective and answered,
                    "time_spent": a["time_spent"] if a else 0,
                    "flagged": bool(a["flagged"]) if a else False,
                })

            active = max(body.active_seconds, attempt["active_seconds"] or 0)
            grading_status = "pending" if pending_grading else "done"
            c.execute(
                """UPDATE attempt SET ended_at = ?, active_seconds = ?, status='submitted',
                   score=?, max_score=?, grading_status=? WHERE id = ?""",
                (database.now_iso(), active, round(total, 2), round(max_total, 2), grading_status, attempt_id),
            )
            log_event(c, attempt_id, "attempt.submitted", {"score": total, "max": max_total})
            quiz_row = c.execute("SELECT agent_session_id FROM quiz WHERE id = ?", (attempt["quiz_id"],)).fetchone()
            add_agent_event(
                c, quiz_row["agent_session_id"] if quiz_row else None, "submitted", "system",
                json.dumps(
                    {"attempt_id": attempt_id, "score": round(total, 2), "max_score": round(max_total, 2),
                     "question_count": len(items), "pending_grading": pending_grading},
                    ensure_ascii=False,
                ),
                attempt_id,
            )

            result = get_attempt(c, attempt_id, reveal=True)
            result["results"] = results_for(c, attempt_id)
            result["weak"] = weak_for(result["results"])
        return result

    @app.get("/api/attempts/{attempt_id}")
    def read_attempt(attempt_id: str):
        c = conn()
        try:
            payload = get_attempt(c, attempt_id)
            if payload["status"] == "submitted":
                payload["results"] = results_for(c, attempt_id)
                payload["weak"] = weak_for(payload["results"])
            return payload
        finally:
            c.close()

    # -------- reviews / stats

    @app.get("/api/reviews/due")
    def due_reviews(subject_id: str | None = None):
        sql = """SELECT q.*, r.due_date, r.mastery, r.interval_days
                 FROM review r JOIN question q ON q.id = r.question_id
                 WHERE r.due_date <= date('now','localtime')"""
        args: list = []
        if subject_id:
            sql += " AND q.subject_id = ?"
            args.append(subject_id)
        sql += " ORDER BY r.due_date, r.mastery"
        with conn() as c:
            return [{**row_to_question(r, conn=c), "due_date": r["due_date"], "mastery": r["mastery"],
                     "interval_days": r["interval_days"]} for r in c.execute(sql, args)]

    def today_seconds(c: sqlite3.Connection) -> int:
        """今日总投入 = 所有作答（含进行中）的 active_seconds + 阅读/终端 study_time。"""
        row = c.execute(
            """SELECT
                 (SELECT COALESCE(SUM(active_seconds),0) FROM attempt
                   WHERE date(started_at) = date('now','localtime'))
               + (SELECT COALESCE(SUM(seconds),0) FROM study_time
                   WHERE day = date('now','localtime')) AS n"""
        ).fetchone()
        return int(row["n"] or 0)

    @app.post("/api/activity")
    def record_activity(body: ActivityIn):
        """阅读 / 代码终端的计时增量。前端每 15 秒（或离开页面时）上报一次。"""
        with conn() as c:
            c.execute(
                """INSERT INTO study_time(day, source, ref, seconds, updated_at)
                   VALUES (date('now','localtime'), ?, ?, ?, ?)
                   ON CONFLICT(day, source, ref) DO UPDATE SET
                     seconds = seconds + excluded.seconds,
                     updated_at = excluded.updated_at""",
                (body.source, body.page_id or "", body.seconds, database.now_iso()),
            )
            total = today_seconds(c)
        return {"ok": True, "today_seconds": total}

    @app.get("/api/stats/today")
    def stats_today():
        with conn() as c:
            row = c.execute(
                """SELECT COALESCE(SUM(active_seconds),0) AS seconds,
                          COUNT(*) AS attempts,
                          COALESCE(SUM(CASE WHEN status='submitted' THEN score ELSE 0 END),0) AS score,
                          COALESCE(SUM(CASE WHEN status='submitted' THEN max_score ELSE 0 END),0) AS max_score
                   FROM attempt WHERE date(started_at) = date('now','localtime')"""
            ).fetchone()
            reading = c.execute(
                """SELECT COALESCE(SUM(seconds),0) AS seconds FROM study_time
                   WHERE day = date('now','localtime')"""
            ).fetchone()
            answered = c.execute(
                """SELECT COUNT(*) AS n, SUM(CASE WHEN a.correct=1 THEN 1 ELSE 0 END) AS ok
                   FROM answer a JOIN attempt t ON t.id = a.attempt_id
                   WHERE date(t.started_at) = date('now','localtime') AND a.correct IS NOT NULL"""
            ).fetchone()
            by_subject = c.execute(
                """SELECT q.subject_id, COUNT(*) AS n,
                          SUM(CASE WHEN a.correct=1 THEN 1 ELSE 0 END) AS ok
                   FROM answer a JOIN attempt t ON t.id = a.attempt_id JOIN question q ON q.id = a.question_id
                   WHERE date(t.started_at) = date('now','localtime') AND a.correct IS NOT NULL
                   GROUP BY q.subject_id"""
            ).fetchall()
        return {
            "date": date.today().isoformat(),
            "active_seconds": row["seconds"] + reading["seconds"],
            "attempts": row["attempts"],
            "score": row["score"],
            "max_score": row["max_score"],
            "answered": answered["n"] or 0,
            "correct": answered["ok"] or 0,
            "by_subject": [dict(r) for r in by_subject],
        }

    def stats_window(days: int) -> tuple[str, str]:
        end = date.today()
        start = end - timedelta(days=days - 1)
        return start.isoformat(), end.isoformat()

    def attempt_seconds_by_subject(c: sqlite3.Connection, start: str,
                                   end: str) -> tuple[dict[str, int], dict[str, int]]:
        """把整次作答的 active_seconds 按题目数分摊到科目，避免跨科重复计时。"""
        attempts = c.execute(
            """SELECT id, active_seconds FROM attempt
               WHERE date(started_at) BETWEEN ? AND ?""",
            (start, end),
        ).fetchall()
        if not attempts:
            return {}, {}
        counts = c.execute(
            """SELECT t.id AS attempt_id, q.subject_id, COUNT(*) AS n
               FROM attempt t
               JOIN quiz_item i ON i.quiz_id = t.quiz_id
               JOIN question q ON q.id = i.question_id
               WHERE date(t.started_at) BETWEEN ? AND ?
               GROUP BY t.id, q.subject_id""",
            (start, end),
        ).fetchall()
        per_attempt: dict[str, list[tuple[str, int]]] = {}
        for row in counts:
            per_attempt.setdefault(row["attempt_id"], []).append(
                (row["subject_id"], row["n"])
            )
        seconds: dict[str, float] = {}
        attempt_counts: dict[str, int] = {}
        for attempt in attempts:
            parts = per_attempt.get(attempt["id"], [])
            total = sum(n for _, n in parts)
            if not total:
                continue
            for subject_id, n in parts:
                seconds[subject_id] = seconds.get(subject_id, 0.0) + (
                    (attempt["active_seconds"] or 0) * n / total
                )
                attempt_counts[subject_id] = attempt_counts.get(subject_id, 0) + 1
        return ({k: int(round(v)) for k, v in seconds.items()}, attempt_counts)

    @app.get("/api/stats/subjects")
    def stats_subjects(days: int = Query(30, ge=1, le=365)):
        start, end = stats_window(days)
        with conn() as c:
            subjects = c.execute(
                "SELECT id, name, short, color, icon FROM subject ORDER BY sort, id"
            ).fetchall()
            answered = {
                r["subject_id"]: r
                for r in c.execute(
                    """SELECT q.subject_id, COUNT(*) AS n,
                              SUM(CASE WHEN a.correct = 1 THEN 1 ELSE 0 END) AS ok
                       FROM answer a
                       JOIN attempt t ON t.id = a.attempt_id
                       JOIN question q ON q.id = a.question_id
                       WHERE date(t.started_at) BETWEEN ? AND ?
                         AND a.correct IS NOT NULL
                       GROUP BY q.subject_id""",
                    (start, end),
                )
            }
            reading = {
                r["subject_id"]: r["seconds"]
                for r in c.execute(
                    """SELECT p.subject_id, COALESCE(SUM(st.seconds), 0) AS seconds
                       FROM study_time st JOIN page p ON p.id = st.ref
                       WHERE st.source = 'page' AND st.day BETWEEN ? AND ?
                         AND p.subject_id IS NOT NULL
                       GROUP BY p.subject_id""",
                    (start, end),
                )
            }
            attempt_seconds, attempt_counts = attempt_seconds_by_subject(c, start, end)

        out = []
        for subject in subjects:
            sid = subject["id"]
            row = answered.get(sid)
            out.append({
                "subject_id": sid,
                "name": subject["name"],
                "short": subject["short"],
                "color": subject["color"],
                "icon": subject["icon"],
                "answered": row["n"] if row else 0,
                "correct": (row["ok"] or 0) if row else 0,
                "seconds": attempt_seconds.get(sid, 0) + reading.get(sid, 0),
                "attempts": attempt_counts.get(sid, 0),
            })
        return out

    @app.get("/api/stats/heatmap")
    def stats_heatmap(days: int = Query(90, ge=1, le=365)):
        start, end = stats_window(days)
        with conn() as c:
            attempt_rows = {
                r["day"]: r["seconds"]
                for r in c.execute(
                    """SELECT date(started_at) AS day, COALESCE(SUM(active_seconds), 0) AS seconds
                       FROM attempt WHERE date(started_at) BETWEEN ? AND ?
                       GROUP BY date(started_at)""",
                    (start, end),
                )
            }
            reading_rows = {
                r["day"]: r["seconds"]
                for r in c.execute(
                    """SELECT day, COALESCE(SUM(seconds), 0) AS seconds
                       FROM study_time WHERE day BETWEEN ? AND ?
                       GROUP BY day""",
                    (start, end),
                )
            }
            answered_rows = {
                r["day"]: r["n"]
                for r in c.execute(
                    """SELECT date(t.started_at) AS day, COUNT(*) AS n
                       FROM answer a JOIN attempt t ON t.id = a.attempt_id
                       WHERE date(t.started_at) BETWEEN ? AND ?
                         AND a.correct IS NOT NULL
                       GROUP BY date(t.started_at)""",
                    (start, end),
                )
            }

        today = date.today()
        out = []
        for offset in range(days - 1, -1, -1):
            day = (today - timedelta(days=offset)).isoformat()
            out.append({
                "date": day,
                "seconds": attempt_rows.get(day, 0) + reading_rows.get(day, 0),
                "answered": answered_rows.get(day, 0),
            })
        return out

    @app.get("/api/stats/types")
    def stats_types(days: int = Query(30, ge=1, le=365)):
        start, end = stats_window(days)
        with conn() as c:
            rows = c.execute(
                """SELECT q.type, COUNT(*) AS n,
                          SUM(CASE WHEN a.correct = 1 THEN 1 ELSE 0 END) AS ok
                   FROM answer a
                   JOIN attempt t ON t.id = a.attempt_id
                   JOIN question q ON q.id = a.question_id
                   WHERE date(t.started_at) BETWEEN ? AND ?
                     AND a.correct IS NOT NULL
                   GROUP BY q.type""",
                (start, end),
            ).fetchall()
        labels = {item["id"]: item.get("label", item["id"])
                  for item in question_types.load_types()}
        return [
            {
                "type": row["type"],
                "label": labels.get(row["type"], row["type"]),
                "answered": row["n"],
                "correct": row["ok"] or 0,
            }
            for row in rows
        ]

    # -------- 备份：导出 / 导入（JSON body，不接受文件路径）

    @app.get("/api/export")
    def export_all(scope: Literal["content", "progress", "all"] = "content"):
        with conn() as c:
            data = export_data(c, scope)
        payload = {
            "format": "kaodian-export",
            "version": database.SCHEMA_VERSION,
            "exported_at": database.now_iso(),
            "scope": scope,
            "data": data,
        }
        filename = f"kaodian-export-{date.today():%Y%m%d}.json"
        return Response(
            json.dumps(payload, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/import")
    def import_all(body: ImportIn):
        c = conn()

        def rollback() -> None:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass

        try:
            c.isolation_level = None
            c.execute("BEGIN IMMEDIATE")
            result = import_data(c, body)
            c.execute("COMMIT")
            return result
        except HTTPException:
            rollback()
            raise
        except sqlite3.IntegrityError as exc:
            rollback()
            raise HTTPException(422, f"导入失败，已回滚：{exc}")
        except Exception:
            rollback()
            raise
        finally:
            c.close()


    # -------- 主观题评分（Agent 读库评分）

    @app.get("/api/grading/queue")
    def grading_queue(limit: int = Query(20, ge=1, le=100)):
        agent_types = question_types.agent_graded_ids()
        if not agent_types:
            return []
        marks = ",".join("?" * len(agent_types))
        with conn() as c:
            rows = c.execute(
                f"""SELECT a.attempt_id, a.question_id, a.response, a.self_grade, a.time_spent,
                          q.type, q.stem, q.rubric, q.reference_answer, q.score AS q_score,
                          q.outline_code, q.tags, z.title AS quiz_title, t.ended_at
                   FROM answer a
                   JOIN attempt t ON t.id = a.attempt_id
                   JOIN question q ON q.id = a.question_id
                   LEFT JOIN quiz z ON z.id = t.quiz_id
                   WHERE t.status = 'submitted'
                     AND q.type IN ({marks})
                     AND a.score IS NULL
                     AND a.response IS NOT NULL AND a.response != ''
                   ORDER BY t.ended_at ASC LIMIT ?""",
                (*agent_types, limit),
            ).fetchall()

        def load(value, fallback=None):
            if not value:
                return fallback
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

        return [{
            "attempt_id": r["attempt_id"],
            "question_id": r["question_id"],
            "quiz_title": r["quiz_title"],
            "ended_at": r["ended_at"],
            "response": load(r["response"], ""),
            "self_grade": load(r["self_grade"], None),
            "time_spent": r["time_spent"],
            "question": {
                "stem": r["stem"],
                "type": r["type"],
                "outline_code": r["outline_code"],
                "score": r["q_score"],
                "rubric": load(r["rubric"], []),
                "reference_answer": r["reference_answer"],
                "tags": load(r["tags"], []),
            },
        } for r in rows]

    @app.post("/api/grading/{attempt_id}/{question_id}")
    def grade_answer(attempt_id: str, question_id: str, body: GradeIn):
        agent_types = question_types.agent_graded_ids()
        with conn() as c:
            row = c.execute(
                """SELECT a.*, q.type, q.score AS q_score, q.outline_code
                   FROM answer a JOIN question q ON q.id = a.question_id
                   JOIN attempt t ON t.id = a.attempt_id
                   WHERE a.attempt_id = ? AND a.question_id = ?""",
                (attempt_id, question_id),
            ).fetchone()
            if not row:
                raise HTTPException(404, "作答记录不存在")
            if question_types.is_objective(row["type"]):
                raise HTTPException(422, "只有主观题需要 Agent 评分")
            max_score = float(row["q_score"])
            if body.score > max_score:
                raise HTTPException(422, f"分数不能超过 {max_score}")
            correct = body.correct if body.correct is not None else body.score >= max_score * 0.6
            first_grade = row["graded_by"] is None
            c.execute(
                """UPDATE answer SET score = ?, correct = ?, graded_by = 'agent', feedback = ?
                   WHERE attempt_id = ? AND question_id = ?""",
                (round(body.score, 2), 1 if correct else 0, body.feedback, attempt_id, question_id),
            )
            if first_grade:
                apply_result(c, question_id, correct)

            if agent_types:
                marks = ",".join("?" * len(agent_types))
                pending = c.execute(
                    f"""SELECT COUNT(*) AS n FROM answer a JOIN question q ON q.id = a.question_id
                       WHERE a.attempt_id = ? AND q.type IN ({marks})
                         AND a.score IS NULL AND a.response IS NOT NULL AND a.response != ''""",
                    (attempt_id, *agent_types),
                ).fetchone()["n"]
            else:
                pending = 0
            total = c.execute(
                """SELECT COALESCE(SUM(a.score), 0) AS s
                   FROM answer a
                   JOIN attempt t ON t.id = a.attempt_id
                   JOIN quiz_item i ON i.quiz_id = t.quiz_id AND i.question_id = a.question_id
                   WHERE a.attempt_id = ?""",
                (attempt_id,),
            ).fetchone()["s"]
            status = "pending" if pending else "done"
            c.execute("UPDATE attempt SET score = ?, grading_status = ? WHERE id = ?",
                      (round(float(total), 2), status, attempt_id))
            log_event(c, attempt_id, "answer.graded", {
                "question_id": question_id, "score": body.score, "correct": correct,
            })

        return {
            "attempt_id": attempt_id,
            "question_id": question_id,
            "score": round(body.score, 2),
            "max_score": max_score,
            "correct": correct,
            "attempt_score": round(float(total), 2),
            "grading_status": status,
        }

    # -------- pages（Agent 写入的学习页）

    @app.post("/api/pages", status_code=201)
    def create_page(body: PageIn):
        with conn() as c:
            if body.subject_id and not c.execute(
                "SELECT 1 FROM subject WHERE id = ?", (body.subject_id,)
            ).fetchone():
                raise HTTPException(422, f"subject_id {body.subject_id} 不存在")
            missing = [code for code in body.outline_codes
                       if not c.execute("SELECT 1 FROM outline_node WHERE code = ?", (code,)).fetchone()]
            if missing:
                raise HTTPException(422, f"考点编号不存在：{', '.join(missing)}")
            if body.blocks is None and not body.body.strip():
                raise HTTPException(422, "正文不能为空")
            errors = [
                *validate_layout(body.layout),
                *validate_theme(body.theme),
                *(validate_blocks(body.blocks) if body.blocks is not None else []),
            ]
            if errors:
                raise HTTPException(422, "；".join(errors))
            page_format = "blocks" if body.blocks is not None else "markdown"
            pid = database.new_id("p")
            now = database.now_iso()
            c.execute(
                """INSERT INTO page(id, subject_id, lesson_key, title, summary, body,
                                   blocks, layout, theme, format, outline_codes,
                                   kind, status, sort_order, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, body.subject_id, body.lesson_key, body.title, body.summary, body.body,
                 json.dumps(body.blocks, ensure_ascii=False) if body.blocks is not None else None,
                 body.layout,
                 json.dumps(body.theme, ensure_ascii=False) if body.theme is not None else None,
                 page_format,
                 json.dumps(body.outline_codes, ensure_ascii=False), body.kind, body.status,
                 body.sort_order, now, now),
            )
            row = c.execute("SELECT * FROM page WHERE id = ?", (pid,)).fetchone()
            return page_dict(row)

    @app.get("/api/pages")
    def list_pages(subject_id: str | None = None, status: str = "published",
                   limit: int = Query(50, ge=1, le=200)):
        sql = """SELECT p.*, pp.completed_at, COALESCE(pp.xp, 0) AS xp
                 FROM page p LEFT JOIN page_progress pp ON pp.page_id = p.id
                 WHERE p.status = ?"""
        args: list = [status]
        if subject_id:
            sql += " AND p.subject_id = ?"
            args.append(subject_id)
        sql += (" ORDER BY COALESCE(p.sort_order, 1000) ASC,"
                " COALESCE(p.lesson_key, 'ZZZ') ASC, p.created_at ASC LIMIT ?")
        args.append(limit)
        with conn() as c:
            return [page_dict(r, full=False) for r in c.execute(sql, args)]

    @app.get("/api/pages/{page_id}")
    def read_page(page_id: str):
        with conn() as c:
            row = c.execute(
                """SELECT p.*, pp.completed_at, COALESCE(pp.xp, 0) AS xp
                   FROM page p LEFT JOIN page_progress pp ON pp.page_id = p.id
                   WHERE p.id = ?""",
                (page_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "学习页不存在")
            return page_dict(row)

    @app.get("/api/pages/{page_id}/question-count")
    def page_question_count(page_id: str):
        """这一页挂的考点能练多少道 approved 题（去重）。"""
        with conn() as c:
            row = c.execute(
                "SELECT outline_codes FROM page WHERE id = ?", (page_id,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "学习页不存在")
            codes = json.loads(row["outline_codes"]) if row["outline_codes"] else []
            if not codes:
                return {"count": 0, "codes": []}
            marks = ",".join("?" * len(codes))
            count = c.execute(
                f"""SELECT COUNT(DISTINCT q.id) AS n FROM question q
                    WHERE q.status = 'approved'
                      AND (q.outline_code IN ({marks}) OR EXISTS (
                        SELECT 1 FROM question_outline qo
                        WHERE qo.question_id = q.id
                          AND qo.outline_code IN ({marks})))""",
                [*codes, *codes],
            ).fetchone()["n"]
        return {"count": count, "codes": codes}

    @app.delete("/api/pages/{page_id}")
    def delete_page(page_id: str):
        with conn() as c:
            row = c.execute("SELECT 1 FROM page WHERE id = ?", (page_id,)).fetchone()
            if not row:
                raise HTTPException(404, "学习页不存在")
            c.execute("DELETE FROM page WHERE id = ?", (page_id,))
        return {"ok": True}

    @app.patch("/api/pages/{page_id}")
    def update_page(page_id: str, body: PagePatch):
        with conn() as c:
            row = c.execute("SELECT * FROM page WHERE id = ?", (page_id,)).fetchone()
            if not row:
                raise HTTPException(404, "学习页不存在")
            data = body.model_dump(exclude_unset=True)
            if not data:
                return page_dict(row)
            errors: list[str] = []
            if "blocks" in data:
                if data["blocks"] is not None:
                    errors.extend(validate_blocks(data["blocks"]))
                data["format"] = "blocks" if data["blocks"] is not None else "markdown"
                data["blocks"] = (
                    json.dumps(data["blocks"], ensure_ascii=False)
                    if data["blocks"] is not None else None
                )
            if "layout" in data:
                data["layout"] = data["layout"] or "article"
                errors.extend(validate_layout(data["layout"]))
            if "theme" in data:
                errors.extend(validate_theme(data["theme"]))
                data["theme"] = (
                    json.dumps(data["theme"], ensure_ascii=False)
                    if data["theme"] is not None else None
                )
            if errors:
                raise HTTPException(422, "；".join(errors))
            if "outline_codes" in data and data["outline_codes"] is not None:
                missing = [code for code in data["outline_codes"]
                           if not c.execute("SELECT 1 FROM outline_node WHERE code = ?", (code,)).fetchone()]
                if missing:
                    raise HTTPException(422, f"考点编号不存在：{', '.join(missing)}")
                data["outline_codes"] = json.dumps(data["outline_codes"], ensure_ascii=False)
            fields = ", ".join(f"{k} = ?" for k in data)
            c.execute(f"UPDATE page SET {fields}, updated_at = ? WHERE id = ?",
                      [*data.values(), database.now_iso(), page_id])
            return page_dict(c.execute("SELECT * FROM page WHERE id = ?", (page_id,)).fetchone())

    # -------- 网页编辑：草稿与发布

    @app.get("/api/pages/{page_id}/draft")
    def get_page_draft(page_id: str):
        with conn() as c:
            return draft_payload(c, page_id)

    @app.put("/api/pages/{page_id}/draft")
    def save_page_draft(page_id: str, body: DraftIn):
        provided = body.model_dump(exclude_unset=True)
        base_version = provided.pop("base_version", None)
        with conn() as c:
            page = c.execute("SELECT * FROM page WHERE id = ?", (page_id,)).fetchone()
            if not page:
                raise HTTPException(404, "学习页不存在")
            existing = c.execute(
                "SELECT * FROM page_draft WHERE page_id = ?", (page_id,)
            ).fetchone()
            if existing:
                current = existing["version"]
                if base_version is not None and base_version != current:
                    raise HTTPException(409, f"草稿版本冲突：当前版本 {current}")
                merged = {
                    "body": existing["body"],
                    "blocks": _decode_json(existing["blocks"]),
                    "layout": existing["layout"],
                    "theme": _decode_json(existing["theme"]),
                }
                version = current + 1
            else:
                if base_version not in (None, 0):
                    raise HTTPException(409, "草稿版本冲突：当前没有草稿")
                merged = {
                    "body": page["body"],
                    "blocks": _decode_json(page["blocks"]),
                    "layout": page["layout"] if "layout" in page.keys() else "article",
                    "theme": _decode_json(page["theme"]),
                }
                version = 1

            for key in ("body", "blocks", "layout", "theme"):
                if key in provided:
                    merged[key] = provided[key]

            if not merged.get("layout"):
                merged["layout"] = "article"
            errors = [
                *validate_layout(merged["layout"]),
                *validate_theme(merged["theme"]),
                *(validate_blocks(merged["blocks"]) if merged["blocks"] is not None else []),
            ]
            if errors:
                raise HTTPException(422, "；".join(errors))

            now = database.now_iso()
            values = (
                merged["body"], _json_text(merged["blocks"]), merged["layout"],
                _json_text(merged["theme"]), version, now,
            )
            if existing:
                c.execute(
                    """UPDATE page_draft
                       SET body=?, blocks=?, layout=?, theme=?, version=?, updated_at=?
                       WHERE page_id=?""",
                    (*values, page_id),
                )
            else:
                c.execute(
                    """INSERT INTO page_draft
                       (body, blocks, layout, theme, version, updated_at, page_id)
                       VALUES (?,?,?,?,?,?,?)""",
                    (*values, page_id),
                )
            return draft_payload(c, page_id)

    @app.delete("/api/pages/{page_id}/draft")
    def discard_page_draft(page_id: str):
        with conn() as c:
            if not c.execute("SELECT 1 FROM page WHERE id = ?", (page_id,)).fetchone():
                raise HTTPException(404, "学习页不存在")
            c.execute("DELETE FROM page_draft WHERE page_id = ?", (page_id,))
        return {"ok": True, "page_id": page_id}

    @app.get("/api/pages/{page_id}/draft/stream")
    async def page_draft_stream(page_id: str, request: Request):
        with database.session(app.state.db_file) as c:
            if not c.execute("SELECT 1 FROM page WHERE id = ?", (page_id,)).fetchone():
                raise HTTPException(404, "学习页不存在")

        async def events():
            last: tuple[Any, Any] | None = None
            last_ping = time.monotonic()
            while True:
                if await request.is_disconnected():
                    break
                with database.session(app.state.db_file) as c:
                    row = c.execute(
                        "SELECT version, updated_at FROM page_draft WHERE page_id = ?",
                        (page_id,),
                    ).fetchone()
                version = row["version"] if row else None
                updated_at = row["updated_at"] if row else None
                if (version, updated_at) != last:
                    last = (version, updated_at)
                    yield "data: " + json.dumps(
                        {"version": version, "updated_at": updated_at},
                        ensure_ascii=False,
                    ) + "\n\n"
                    last_ping = time.monotonic()
                elif time.monotonic() - last_ping >= 15:
                    yield ": ping\n\n"
                    last_ping = time.monotonic()
                await asyncio.sleep(1)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/pages/{page_id}/publish")
    def publish_page_draft(page_id: str, body: PublishIn):
        content_dir = paths.content_dir()
        with conn() as c:
            page = c.execute("SELECT * FROM page WHERE id = ?", (page_id,)).fetchone()
            if not page:
                raise HTTPException(404, "学习页不存在")
            draft = c.execute(
                "SELECT * FROM page_draft WHERE page_id = ?", (page_id,)
            ).fetchone()
            if not draft:
                raise HTTPException(422, "没有草稿可发布")

            now = database.now_iso()
            # 本地页：没有内容文件，直接更新数据库。
            if not page["pack_id"]:
                blocks = _decode_json(draft["blocks"])
                page_format = "blocks" if blocks is not None else "markdown"
                c.execute(
                    """UPDATE page SET body=?, blocks=?, layout=?, theme=?,
                         format=?, updated_at=? WHERE id=?""",
                    (
                        draft["body"] or "", _json_text(blocks),
                        draft["layout"] or "article",
                        _json_text(_decode_json(draft["theme"])),
                        page_format, now, page_id,
                    ),
                )
                c.execute("DELETE FROM page_draft WHERE page_id = ?", (page_id,))
                updated = c.execute("SELECT * FROM page WHERE id = ?", (page_id,)).fetchone()
                return {"page": page_dict(updated), "file": None, "committed": False}

            file_value = page["file"]
            if not file_value:
                raise HTTPException(422, "页面没有内容文件，无法写回")

            errors = content_packs.validate_page_draft(content_dir, page, draft)
            if errors:
                raise HTTPException(422, {
                    "message": "发布前校验失败，文件未修改",
                    "errors": errors,
                })
            try:
                content_packs.write_lesson_file(content_dir, page, draft)
            except content_packs.PackError as exc:
                raise HTTPException(422, str(exc)) from exc

            try:
                content_packs.sync_content(c)
            except content_packs.PackError as exc:
                raise HTTPException(500, f"文件已写入，但同步失败：{exc}") from exc

            c.execute("DELETE FROM page_draft WHERE page_id = ?", (page_id,))
            updated = c.execute("SELECT * FROM page WHERE id = ?", (page_id,)).fetchone()

            committed = False
            commit_error: HTTPException | None = None
            if body.commit:
                message = body.message or f"更新 {page['lesson_key'] or page['title']}"
                try:
                    committed = _git_commit(content_dir, file_value, message)
                except HTTPException as exc:
                    # 文件与数据库都已更新，只把提交失败报告给调用方。
                    commit_error = exc
            result = {
                "page": page_dict(updated),
                "file": file_value,
                "committed": committed,
            }
        if commit_error is not None:
            raise commit_error
        return result

    @app.post("/api/content/validate")
    def validate_content():
        packs = content_packs.validate_all()
        return {
            "ok": all(pack["ok"] for pack in packs),
            "packs": [
                {"id": pack["id"], "ok": pack["ok"], "errors": pack["errors"]}
                for pack in packs
            ],
        }

    @app.post("/api/pages/{page_id}/complete")
    def complete_page(page_id: str, xp: int = 10):
        with conn() as c:
            if not c.execute("SELECT 1 FROM page WHERE id = ?", (page_id,)).fetchone():
                raise HTTPException(404, "学习页不存在")
            existing = c.execute("SELECT * FROM page_progress WHERE page_id = ?", (page_id,)).fetchone()
            if existing:
                return {"completed_at": existing["completed_at"], "xp": existing["xp"], "already": True}
            now = database.now_iso()
            c.execute("INSERT INTO page_progress(page_id, completed_at, xp) VALUES (?,?,?)",
                      (page_id, now, max(1, min(xp, 100))))
            return {"completed_at": now, "xp": max(1, min(xp, 100)), "already": False}

    @app.get("/api/progress")
    def progress():
        today = date.today()
        with conn() as c:
            attempts = {r["d"]: r["seconds"] for r in c.execute(
                """SELECT date(started_at) AS d, COALESCE(SUM(active_seconds), 0) AS seconds
                   FROM attempt GROUP BY date(started_at)"""
            )}
            reading = {r["d"]: r["seconds"] for r in c.execute(
                """SELECT day AS d, COALESCE(SUM(seconds), 0) AS seconds
                   FROM study_time GROUP BY day"""
            )}
            seconds_by_day = {
                d: attempts.get(d, 0) + reading.get(d, 0)
                for d in set(attempts) | set(reading)
            }
            completed = [r["d"] for r in c.execute(
                "SELECT date(completed_at) AS d FROM page_progress"
            )]
            active = set(seconds_by_day) | set(completed)
            today_minutes = round(seconds_by_day.get(today.isoformat(), 0) / 60)
            # 每日目标以画像为准；画像缺失时退回环境变量默认值。
            goal_row = c.execute("SELECT daily_minutes FROM profile WHERE id = 1").fetchone()
            goal = (
                int(goal_row["daily_minutes"])
                if goal_row and goal_row["daily_minutes"]
                else int(os.environ.get("KAODIAN_DAILY_GOAL_MINUTES", "30"))
            )

            cursor = today
            if cursor.isoformat() not in active:
                cursor = today - timedelta(days=1)
            streak = 0
            while cursor.isoformat() in active:
                streak += 1
                cursor -= timedelta(days=1)

            days = []
            for offset in range(6, -1, -1):
                d = today - timedelta(days=offset)
                minutes = round(seconds_by_day.get(d.isoformat(), 0) / 60)
                done = bool(minutes) or d.isoformat() in completed
                days.append({"date": d.isoformat(), "minutes": minutes, "done": done})

            xp_pages = c.execute("SELECT COALESCE(SUM(xp), 0) AS n FROM page_progress").fetchone()["n"]
            xp_answers = c.execute("SELECT COUNT(*) AS n FROM answer WHERE correct = 1").fetchone()["n"]
            pages_total = c.execute("SELECT COUNT(*) AS n FROM page WHERE status = 'published'").fetchone()["n"]
            pages_done = c.execute("SELECT COUNT(*) AS n FROM page_progress").fetchone()["n"]

        return {
            "streak": streak,
            "today_done": today.isoformat() in active,
            "today_minutes": today_minutes,
            "daily_goal_minutes": goal,
            "xp": xp_pages + xp_answers * 2,
            "completed_pages": pages_done,
            "total_pages": pages_total,
            "days": days,
        }

    # -------- 学习画像

    @app.get("/api/profile")
    def read_profile():
        with conn() as c:
            return profiles.get_profile(c)

    @app.put("/api/profile")
    def write_profile(body: ProfileIn):
        with conn() as c:
            try:
                return profiles.update_profile(c, body.model_dump(exclude_unset=True))
            except profiles.ProfileError as exc:
                raise HTTPException(422, str(exc)) from exc

    # -------- agent 协作

    @app.post("/api/agent/sessions", status_code=201)
    def create_agent_session(body: AgentSessionIn):
        sid = database.new_id("s")
        with conn() as c:
            c.execute("INSERT INTO agent_session(id, title, created_at) VALUES (?,?,?)",
                      (sid, body.title, database.now_iso()))
        return {"id": sid, "title": body.title}

    @app.post("/api/agent/events", status_code=201)
    def create_agent_event(body: AgentEventIn):
        with conn() as c:
            if not c.execute("SELECT 1 FROM agent_session WHERE id = ?", (body.session_id,)).fetchone():
                raise HTTPException(404, "Agent 会话不存在")
            eid = add_agent_event(c, body.session_id, body.kind, body.role, body.body)
        return {"id": eid}

    @app.get("/api/agent/feed")
    def agent_feed(session_id: str, after_id: int = 0, limit: int = Query(100, ge=1, le=200)):
        with conn() as c:
            rows = c.execute(
                "SELECT * FROM agent_event WHERE session_id = ? AND id > ? ORDER BY id LIMIT ?",
                (session_id, after_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # SSE：先补 after_id 之后的历史事件，再每秒轮询新事件；15 秒无事件发注释心跳。
    # 只允许本地单用户，不做鉴权；客户端断开后由 CancelledError / GeneratorExit 结束生成器。
    stream_poll_seconds = 1.0
    stream_ping_seconds = 15

    @app.get("/api/agent/stream")
    async def agent_stream(session_id: str, after_id: int = 0):
        def fetch(after: int) -> list[dict]:
            with conn() as c:
                rows = c.execute(
                    "SELECT * FROM agent_event WHERE session_id = ? AND id > ? "
                    "ORDER BY id LIMIT 100",
                    (session_id, after),
                ).fetchall()
            return [dict(r) for r in rows]

        def encode(event: dict) -> str:
            return (
                f"id: {event['id']}\n"
                f"event: {event['kind']}\n"
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            )

        async def events():
            last_id = after_id
            idle_seconds = 0.0
            try:
                while True:
                    rows = fetch(last_id)
                    if rows:
                        idle_seconds = 0.0
                        for row in rows:
                            last_id = row["id"]
                            yield encode(row)
                    else:
                        idle_seconds += stream_poll_seconds
                        if idle_seconds >= stream_ping_seconds:
                            idle_seconds = 0.0
                            yield ": ping\n\n"
                    await asyncio.sleep(stream_poll_seconds)
            except (asyncio.CancelledError, GeneratorExit):
                return

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/agent/inbox")
    def agent_inbox(after_id: int = 0, session_id: str | None = None,
                    limit: int = Query(50, ge=1, le=200)):
        sql = ("SELECT * FROM agent_event WHERE kind IN ('help', 'submitted') AND id > ?")
        params: list[Any] = [after_id]
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        sql += " ORDER BY id ASC LIMIT ?"
        params.append(limit)
        with conn() as c:
            rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    @app.post("/api/agent/help", status_code=201)
    def agent_help(body: HelpIn):
        with conn() as c:
            row = c.execute(
                """SELECT q.agent_session_id FROM attempt a JOIN quiz q ON q.id = a.quiz_id
                   WHERE a.id = ?""",
                (body.attempt_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "作答记录不存在")
            if not row["agent_session_id"]:
                raise HTTPException(409, "这个练习单没有关联 Agent 会话")
            eid = add_agent_event(c, row["agent_session_id"], "help", "user", body.body,
                                  body.question_id or body.attempt_id)
        return {"id": eid}


    # -------- 代码练习（gcc + bubblewrap 沙箱，默认关闭）

    def code_run_enabled() -> bool:
        return os.environ.get("KAODIAN_ALLOW_CODE_RUN") == "1"

    @app.get("/api/code/status")
    def code_status():
        return {
            "enabled": code_run_enabled(),
            "compiler": "gcc",
            "sandbox": "bubblewrap",
            "network": False,
        }

    @app.post("/api/code/run")
    def run_code(body: CodeRunIn):
        if body.language != "c":
            raise HTTPException(422, f"暂不支持 language={body.language}，当前只有 c")
        if not code_run_enabled():
            raise HTTPException(403, "代码运行未启用；启动时设置 KAODIAN_ALLOW_CODE_RUN=1")
        if not shutil.which("gcc") or not shutil.which("bwrap"):
            raise HTTPException(503, "服务器缺少 gcc 或 bubblewrap")

        work = Path(tempfile.mkdtemp(prefix="run-", dir=paths.sandbox_dir()))
        try:
            (work / "main.c").write_text(body.code, encoding="utf-8")
            bwrap = [
                "bwrap",
                "--ro-bind", "/usr", "/usr",
                "--ro-bind-try", "/lib", "/lib",
                "--ro-bind-try", "/lib64", "/lib64",
                "--ro-bind-try", "/etc/ld.so.cache", "/etc/ld.so.cache",
                "--dev", "/dev",
                "--proc", "/proc",
                "--tmpfs", "/tmp",
                "--bind", str(work), "/work",
                "--unshare-net",
                "--unshare-pid",
                "--die-with-parent",
                "--new-session",
                "--chdir", "/work",
            ]
            started = __import__("time").monotonic()
            try:
                sandbox_env = {"PATH": "/usr/local/bin:/usr/bin:/bin",
                               "LANG": "C.UTF-8", "HOME": "/tmp"}
                compile_proc = subprocess.run(
                    [*bwrap, "gcc", "main.c", "-o", "main", "-std=c11", "-O0"],
                    capture_output=True, text=True, timeout=20, env=sandbox_env,
                )
            except subprocess.TimeoutExpired:
                return {"ok": False, "stage": "compile", "output": "编译超时（20 秒）", "exit_code": None}

            compile_output = (compile_proc.stdout + compile_proc.stderr)[-8000:]
            if compile_proc.returncode != 0:
                return {
                    "ok": False, "stage": "compile", "output": compile_output,
                    "exit_code": compile_proc.returncode,
                    "hints": explain_diagnostics(compile_output),
                }

            out_path = work / "stdout.txt"
            try:
                # stdout 直接落盘，ulimit -f 64（64KB）限制写入；避免把无限输出读进 API 内存。
                with open(out_path, "w", encoding="utf-8") as out_file:
                    run_proc = subprocess.run(
                        [*bwrap, "bash", "-c",
                         "ulimit -v 262144 -u 64 -t 3 -f 64 2>/dev/null; exec ./main"],
                        input=body.stdin, stdout=out_file, stderr=subprocess.STDOUT,
                        text=True, timeout=6, env=sandbox_env,
                    )
            except subprocess.TimeoutExpired:
                return {
                    "ok": False, "stage": "run", "output": "运行超时（3 秒 CPU / 6 秒墙钟），检查是否有死循环。",
                    "exit_code": None,
                }

            output = out_path.read_text(encoding="utf-8", errors="replace")[-65536:]
            runtime_hints: list[dict] = []
            if run_proc.returncode in (124, 137) or run_proc.returncode < 0:
                output += "\n[进程被终止：可能是死循环、CPU 超时或内存超限]"
                runtime_hints = [{"line": None, "kind": "runtime", "message": "timeout",
                                  "reason": "程序 3 秒内没有结束，通常是死循环。", "fix": "检查 while/for 的退出条件。"}]
            elif run_proc.returncode in (139, -11):
                runtime_hints = [{"line": None, "kind": "runtime", "message": "segmentation fault",
                                  "reason": "段错误：访问了不该访问的内存。",
                                  "fix": "常见原因：数组越界、scanf 漏 &、使用未初始化的指针。"}]
            elif run_proc.returncode in (136, -8):
                runtime_hints = [{"line": None, "kind": "runtime", "message": "floating point exception",
                                  "reason": "整数除以 0（或对 0 取余）。", "fix": "在除法前检查除数是否为 0。"}]
            output = output[:65536]
            duration = int((__import__("time").monotonic() - started) * 1000)
            return {
                "ok": run_proc.returncode == 0,
                "stage": "run",
                "output": output,
                "exit_code": run_proc.returncode,
                "compile_output": compile_output,
                "hints": explain_diagnostics(compile_output) + runtime_hints,
                "duration_ms": duration,
            }
        finally:
            shutil.rmtree(work, ignore_errors=True)

    # -------- static (production build)

    if (WEB_DIST / "index.html").is_file() and (WEB_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            if path.startswith("api"):
                raise HTTPException(404, "Not Found")
            root = WEB_DIST.resolve()
            target = (root / path).resolve()
            # 只允许 dist 内的文件；禁止 ../ 逃逸到 runtime / 源码。
            if path and target.is_file() and target.is_relative_to(root):
                return FileResponse(target)
            return FileResponse(root / "index.html")

    return app


app = create_app()
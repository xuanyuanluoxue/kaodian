from __future__ import annotations

import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import tempfile
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db as database
from .grading import fingerprint, grade, validate_question
from .review import apply_result

ROOT = Path(__file__).resolve().parents[3]
WEB_DIST = ROOT / "apps" / "web" / "dist"


# ---------------------------------------------------------------- models

class QuestionIn(BaseModel):
    outline_code: str
    subject_id: str | None = None
    type: str
    stem: str
    options: list[str] | None = None
    answer: list[str] | None = None
    explanation: str = ""
    reference_answer: str | None = None
    rubric: list[dict] | None = None
    score: float = 1
    difficulty: int = 2
    source: dict | None = None
    tags: list[str] = Field(default_factory=list)
    verified: bool = False
    client_ref: str | None = None


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


class PageIn(BaseModel):
    subject_id: str | None = None
    lesson_key: str | None = Field(default=None, max_length=20)
    title: str = Field(min_length=1, max_length=120)
    summary: str | None = None
    body: str = Field(min_length=1)
    outline_codes: list[str] = Field(default_factory=list)
    kind: Literal["outline", "lesson", "daily", "note"] = "lesson"
    status: Literal["draft", "published"] = "published"


class PagePatch(BaseModel):
    lesson_key: str | None = Field(default=None, max_length=20)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    summary: str | None = None
    body: str | None = Field(default=None, min_length=1)
    outline_codes: list[str] | None = None
    kind: Literal["outline", "lesson", "daily", "note"] | None = None
    status: Literal["draft", "published"] | None = None


# ---------------------------------------------------------------- helpers

def row_to_question(row: sqlite3.Row, reveal: bool = True) -> dict:
    def load(value):
        if value is None:
            return None
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value

    item = {
        "id": row["id"],
        "subject_id": row["subject_id"],
        "outline_code": row["outline_code"],
        "type": row["type"],
        "stem": row["stem"],
        "options": load(row["options"]),
        "score": row["score"],
        "difficulty": row["difficulty"],
        "tags": load(row["tags"]) or [],
        "verified": bool(row["verified"]),
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


def page_dict(row: sqlite3.Row, full: bool = True) -> dict:
    item = {
        "id": row["id"],
        "subject_id": row["subject_id"],
        "title": row["title"],
        "summary": row["summary"],
        "lesson_key": row["lesson_key"] if "lesson_key" in row.keys() else None,
        "outline_codes": json.loads(row["outline_codes"]) if row["outline_codes"] else [],
        "kind": row["kind"],
        "status": row["status"],
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


def get_quiz(conn: sqlite3.Connection, quiz_id: str) -> dict:
    quiz = conn.execute("SELECT * FROM quiz WHERE id = ?", (quiz_id,)).fetchone()
    if not quiz:
        raise HTTPException(404, "练习单不存在")
    items = conn.execute(
        """SELECT q.* FROM quiz_item i JOIN question q ON q.id = i.question_id
           WHERE i.quiz_id = ? ORDER BY i.position""",
        (quiz_id,),
    ).fetchall()
    return {
        "id": quiz["id"],
        "title": quiz["title"],
        "mode": quiz["mode"],
        "time_limit": quiz["time_limit"],
        "agent_session_id": quiz["agent_session_id"],
        "created_at": quiz["created_at"],
        "question_count": len(items),
        "questions": [row_to_question(r, reveal=(quiz["mode"] == "practice")) for r in items],
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
                                   {"id", "subject_id", "outline_code", "type", "stem", "options", "score", "difficulty", "tags"}}
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
            "question": row_to_question(q, reveal=True),
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


# ---------------------------------------------------------------- app

def create_app(db_file: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.init_db(db_file)
        yield

    app = FastAPI(title="考点 Kaodian", version="0.1.0", lifespan=lifespan)
    app.state.db_file = db_file
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def cache_policy(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
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
        return {"ok": True, "version": app.version}

    @app.get("/api/subjects")
    def subjects():
        with conn() as c:
            rows = c.execute(
                """SELECT s.*, COUNT(n.code) AS node_count, COALESCE(SUM(n.hours),0) AS hours
                   FROM subject s LEFT JOIN outline_node n ON n.subject_id = s.id
                   GROUP BY s.id ORDER BY s.id"""
            ).fetchall()
            counts = {r["subject_id"]: r["n"] for r in c.execute(
                "SELECT subject_id, COUNT(*) AS n FROM question GROUP BY subject_id")}
        return [{**dict(r), "question_count": counts.get(r["id"], 0)} for r in rows]

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
        for column, value in (("subject_id", subject_id), ("outline_code", code), ("type", type)):
            if value:
                sql += f" AND {column} = ?"
                args.append(value)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with conn() as c:
            return [row_to_question(r) for r in c.execute(sql, args)]

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
            errors = []
            for i, q in enumerate(body.questions):
                errs = validate_question(q.model_dump(), outline)
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
                           (id, subject_id, outline_code, type, stem, options, answer, explanation,
                            reference_answer, rubric, score, difficulty, source, tags, verified, status, fingerprint, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            qid, subject_id, q.outline_code, q.type, q.stem,
                            json.dumps(q.options, ensure_ascii=False) if q.options is not None else None,
                            json.dumps(q.answer, ensure_ascii=False) if q.answer is not None else None,
                            q.explanation, q.reference_answer,
                            json.dumps(q.rubric, ensure_ascii=False) if q.rubric is not None else None,
                            q.score, q.difficulty,
                            json.dumps(q.source or {"kind": "ai"}, ensure_ascii=False),
                            json.dumps(q.tags, ensure_ascii=False),
                            1 if q.verified else 0, "pending", fp, database.now_iso(),
                        ),
                    )
                    created.append(qid)
                except sqlite3.IntegrityError:
                    skipped.append(q.stem[:40])
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
                    sql += f" AND q.outline_code IN ({','.join('?' * len(f.codes))})"
                    args += f.codes
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
                subjective = q["type"] in {"short", "calc", "code", "essay"}
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
                    "question": row_to_question(q, reveal=True),
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
            return [{**row_to_question(r), "due_date": r["due_date"], "mastery": r["mastery"],
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


    # -------- 主观题评分（Agent 读库评分）

    @app.get("/api/grading/queue")
    def grading_queue(limit: int = Query(20, ge=1, le=100)):
        with conn() as c:
            rows = c.execute(
                """SELECT a.attempt_id, a.question_id, a.response, a.self_grade, a.time_spent,
                          q.type, q.stem, q.rubric, q.reference_answer, q.score AS q_score,
                          q.outline_code, q.tags, z.title AS quiz_title, t.ended_at
                   FROM answer a
                   JOIN attempt t ON t.id = a.attempt_id
                   JOIN question q ON q.id = a.question_id
                   LEFT JOIN quiz z ON z.id = t.quiz_id
                   WHERE t.status = 'submitted'
                     AND q.type IN ('short', 'calc', 'code', 'essay')
                     AND a.score IS NULL
                     AND a.response IS NOT NULL AND a.response != ''
                   ORDER BY t.ended_at ASC LIMIT ?""",
                (limit,),
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
            if row["type"] not in {"short", "calc", "code", "essay"}:
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

            pending = c.execute(
                """SELECT COUNT(*) AS n FROM answer a JOIN question q ON q.id = a.question_id
                   WHERE a.attempt_id = ? AND q.type IN ('short', 'calc', 'code', 'essay')
                     AND a.score IS NULL AND a.response IS NOT NULL AND a.response != ''""",
                (attempt_id,),
            ).fetchone()["n"]
            total = c.execute(
                "SELECT COALESCE(SUM(score), 0) AS s FROM answer WHERE attempt_id = ?", (attempt_id,)
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
            pid = database.new_id("p")
            now = database.now_iso()
            c.execute(
                """INSERT INTO page(id, subject_id, lesson_key, title, summary, body, outline_codes, kind, status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, body.subject_id, body.lesson_key, body.title, body.summary, body.body,
                 json.dumps(body.outline_codes, ensure_ascii=False), body.kind, body.status, now, now),
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
        sql += " ORDER BY COALESCE(p.lesson_key, 'ZZZ') ASC, p.created_at ASC LIMIT ?"
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
            goal = int(os.environ.get("KAODIAN_DAILY_GOAL_MINUTES", "30"))

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

    @app.get("/api/agent/inbox")
    def agent_inbox(after_id: int = 0, limit: int = Query(50, ge=1, le=200)):
        with conn() as c:
            rows = c.execute(
                """SELECT * FROM agent_event WHERE kind IN ('help', 'submitted') AND id > ?
                   ORDER BY id DESC LIMIT ?""",
                (after_id, limit),
            ).fetchall()
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
        if not code_run_enabled():
            raise HTTPException(403, "代码运行未启用；启动时设置 KAODIAN_ALLOW_CODE_RUN=1")
        if not shutil.which("gcc") or not shutil.which("bwrap"):
            raise HTTPException(503, "服务器缺少 gcc 或 bubblewrap")

        work = Path(tempfile.mkdtemp(prefix="kaodian-run-", dir="/tmp/opencode"))
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
                compile_proc = subprocess.run(
                    [*bwrap, "gcc", "main.c", "-o", "main", "-std=c11", "-O0"],
                    capture_output=True, text=True, timeout=20,
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

            try:
                run_proc = subprocess.run(
                    [*bwrap, "bash", "-c", "ulimit -v 262144 -u 64 -t 3 -f 1024 2>/dev/null; exec ./main"],
                    input=body.stdin, capture_output=True, text=True, timeout=6,
                )
            except subprocess.TimeoutExpired:
                return {
                    "ok": False, "stage": "run", "output": "运行超时（3 秒 CPU / 6 秒墙钟），检查是否有死循环。",
                    "exit_code": None,
                }

            output = run_proc.stdout + run_proc.stderr
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

    if WEB_DIST.exists():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            if path.startswith("api"):
                raise HTTPException(404, "Not Found")
            target = WEB_DIST / path
            if path and target.is_file():
                return FileResponse(target)
            return FileResponse(WEB_DIST / "index.html")

    return app


app = create_app()
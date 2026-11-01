from __future__ import annotations

import json
import random
import sqlite3
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
        "source": load(row["source"]),
    }
    if reveal:
        item["answer"] = load(row["answer"])
        item["explanation"] = row["explanation"]
        item["reference_answer"] = row["reference_answer"]
        item["rubric"] = load(row["rubric"])
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
        "quiz": quiz if reveal or row["status"] == "submitted" else {
            **quiz, "questions": [{k: v for k, v in q.items() if k in
                                   {"id", "subject_id", "outline_code", "type", "stem", "options", "score", "difficulty", "tags"}}
                                  for q in quiz["questions"]],
        },
        "answers": answers,
    }



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
        limit: int = Query(50, ge=1, le=200),
    ):
        sql = "SELECT * FROM question WHERE 1=1"
        args: list = []
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
                            reference_answer, rubric, score, difficulty, source, tags, verified, fingerprint, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            qid, subject_id, q.outline_code, q.type, q.stem,
                            json.dumps(q.options, ensure_ascii=False) if q.options is not None else None,
                            json.dumps(q.answer, ensure_ascii=False) if q.answer is not None else None,
                            q.explanation, q.reference_answer,
                            json.dumps(q.rubric, ensure_ascii=False) if q.rubric is not None else None,
                            q.score, q.difficulty,
                            json.dumps(q.source or {"kind": "ai"}, ensure_ascii=False),
                            json.dumps(q.tags, ensure_ascii=False),
                            1 if q.verified else 0, fp, database.now_iso(),
                        ),
                    )
                    created.append(qid)
                except sqlite3.IntegrityError:
                    skipped.append(q.stem[:40])
            log_event(c, None, "questions.created", {"created": len(created), "skipped": len(skipped)})
        return {"created": len(created), "skipped": len(skipped), "ids": created}

    # -------- quizzes

    @app.post("/api/quizzes", status_code=201)
    def create_quiz(body: QuizIn):
        with conn() as c:
            if body.question_ids:
                placeholders = ",".join("?" * len(body.question_ids))
                rows = c.execute(f"SELECT * FROM question WHERE id IN ({placeholders})", body.question_ids).fetchall()
                by_id = {r["id"]: r for r in rows}
                rows = [by_id[i] for i in body.question_ids if i in by_id]
            else:
                sql = "SELECT q.* FROM question q WHERE 1=1"
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
            results = []
            for q in items:
                a = c.execute("SELECT * FROM answer WHERE attempt_id = ? AND question_id = ?",
                              (attempt_id, q["id"])).fetchone()
                response = json.loads(a["response"]) if a and a["response"] else None
                self_grade = json.loads(a["self_grade"]) if a and a["self_grade"] else None
                g = grade(dict(q), response, self_grade)
                if response is None and self_grade is None:
                    g = {"correct": None, "score": 0.0, "max_score": g["max_score"]}
                total += g["score"]
                max_total += g["max_score"]
                c.execute("UPDATE answer SET correct = ?, score = ? WHERE attempt_id = ? AND question_id = ?",
                          (None if g["correct"] is None else 1 if g["correct"] else 0, g["score"], attempt_id, q["id"]))
                if response is not None or self_grade is not None:
                    apply_result(c, q["id"], g["correct"])
                results.append({
                    "question": row_to_question(q, reveal=True),
                    "response": response,
                    "self_grade": self_grade,
                    "correct": g["correct"],
                    "score": g["score"],
                    "max_score": g["max_score"],
                    "time_spent": a["time_spent"] if a else 0,
                    "flagged": bool(a["flagged"]) if a else False,
                })

            active = max(body.active_seconds, attempt["active_seconds"] or 0)
            c.execute(
                "UPDATE attempt SET ended_at = ?, active_seconds = ?, status='submitted', score=?, max_score=? WHERE id = ?",
                (database.now_iso(), active, round(total, 2), round(max_total, 2), attempt_id),
            )
            log_event(c, attempt_id, "attempt.submitted", {"score": total, "max": max_total})
            quiz_row = c.execute("SELECT agent_session_id FROM quiz WHERE id = ?", (attempt["quiz_id"],)).fetchone()
            add_agent_event(
                c, quiz_row["agent_session_id"] if quiz_row else None, "submitted", "system",
                json.dumps(
                    {"attempt_id": attempt_id, "score": round(total, 2), "max_score": round(max_total, 2),
                     "question_count": len(items)},
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

    @app.get("/api/stats/today")
    def stats_today():
        with conn() as c:
            row = c.execute(
                """SELECT COALESCE(SUM(active_seconds),0) AS seconds,
                          COUNT(*) AS attempts, COALESCE(SUM(score),0) AS score,
                          COALESCE(SUM(max_score),0) AS max_score
                   FROM attempt WHERE date(started_at) = date('now','localtime') AND status='submitted'"""
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
            "active_seconds": row["seconds"],
            "attempts": row["attempts"],
            "score": row["score"],
            "max_score": row["max_score"],
            "answered": answered["n"] or 0,
            "correct": answered["ok"] or 0,
            "by_subject": [dict(r) for r in by_subject],
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
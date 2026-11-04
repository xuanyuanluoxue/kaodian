"""学习画像：静态目标存 `profile` 单行表，动态学情实时查询。

动态字段的口径与 `/api/progress`、`/api/stats/subjects` 保持一致：
- 时长 = `attempt.active_seconds` + `study_time.seconds`；
- 作答只统计 `answer.correct IS NOT NULL`，按 `attempt.started_at` 的本地日期归档；
- 科目时长按练习单内各科题目数分摊 `attempt.active_seconds`，阅读时长按
  `page.subject_id` 归属。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

DEFAULT_DAILY_MINUTES = 30
TEXT_LIMITS = {
    "notes": 2000,
    "preferred_tone": 200,
    "preferred_examples": 200,
}


class ProfileError(ValueError):
    """静态画像校验失败，由 API 转成 422。"""


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _subject_ids(conn: sqlite3.Connection) -> list[str]:
    return [
        row["id"]
        for row in conn.execute("SELECT id FROM subject ORDER BY sort, id").fetchall()
    ]


def ensure_profile(conn: sqlite3.Connection) -> None:
    """保证单行存在；已有画像绝不覆盖。"""
    if conn.execute("SELECT 1 FROM profile WHERE id = 1").fetchone():
        return
    conn.execute(
        """INSERT INTO profile(id, target_exam, target_date, target_score,
                               daily_minutes, subjects, notes, preferred_tone,
                               preferred_examples, updated_at)
           VALUES (1, NULL, NULL, NULL, ?, ?, '', '', '', ?)""",
        (
            DEFAULT_DAILY_MINUTES,
            json.dumps(_subject_ids(conn), ensure_ascii=False),
            _now_iso(),
        ),
    )


def _parse_subjects(value: str | None) -> list[str]:
    try:
        data = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def _parse_date(value: str) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ProfileError("target_date 必须是 YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ProfileError("target_date 必须是 YYYY-MM-DD") from exc


def _accuracy(answered: int, correct: int) -> float | None:
    if not answered:
        return None
    return round(correct / answered, 3)


def _daily_series(conn: sqlite3.Connection, days: int = 7) -> list[dict]:
    """近 N 天（含今天）每天的总时长与作答数，缺失补 0。"""
    today = date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    end = today.isoformat()
    attempts = {
        row["day"]: row["seconds"]
        for row in conn.execute(
            """SELECT date(started_at) AS day, COALESCE(SUM(active_seconds), 0) AS seconds
               FROM attempt WHERE date(started_at) BETWEEN ? AND ?
               GROUP BY date(started_at)""",
            (start, end),
        )
    }
    reading = {
        row["day"]: row["seconds"]
        for row in conn.execute(
            """SELECT day, COALESCE(SUM(seconds), 0) AS seconds
               FROM study_time WHERE day BETWEEN ? AND ?
               GROUP BY day""",
            (start, end),
        )
    }
    answered = {
        row["day"]: row["n"]
        for row in conn.execute(
            """SELECT date(t.started_at) AS day, COUNT(*) AS n
               FROM answer a JOIN attempt t ON t.id = a.attempt_id
               WHERE date(t.started_at) BETWEEN ? AND ?
                 AND a.correct IS NOT NULL
               GROUP BY date(t.started_at)""",
            (start, end),
        )
    }
    out = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        out.append({
            "date": day,
            "seconds": attempts.get(day, 0) + reading.get(day, 0),
            "answered": answered.get(day, 0),
        })
    return out


def _streak(conn: sqlite3.Connection) -> int:
    """与 `/api/progress` 一致：有计时或完成课页都算当天活跃。"""
    seconds_days = {
        row["d"]
        for row in conn.execute(
            """SELECT date(started_at) AS d FROM attempt
               UNION SELECT day AS d FROM study_time"""
        )
    }
    completed = {
        row["d"]
        for row in conn.execute("SELECT date(completed_at) AS d FROM page_progress")
    }
    active = seconds_days | completed
    cursor = date.today()
    if cursor.isoformat() not in active:
        cursor -= timedelta(days=1)
    count = 0
    while cursor.isoformat() in active:
        count += 1
        cursor -= timedelta(days=1)
    return count


def _attempt_seconds_by_subject(conn: sqlite3.Connection) -> dict[str, int]:
    attempts = conn.execute("SELECT id, active_seconds FROM attempt").fetchall()
    if not attempts:
        return {}
    counts = conn.execute(
        """SELECT t.id AS attempt_id, q.subject_id, COUNT(*) AS n
           FROM attempt t
           JOIN quiz_item i ON i.quiz_id = t.quiz_id
           JOIN question q ON q.id = i.question_id
           GROUP BY t.id, q.subject_id"""
    ).fetchall()
    per_attempt: dict[str, list[tuple[str, int]]] = {}
    for row in counts:
        per_attempt.setdefault(row["attempt_id"], []).append((row["subject_id"], row["n"]))
    seconds: dict[str, float] = {}
    for attempt in attempts:
        parts = per_attempt.get(attempt["id"], [])
        total = sum(n for _, n in parts)
        if not total:
            continue
        for subject_id, n in parts:
            seconds[subject_id] = seconds.get(subject_id, 0.0) + (
                (attempt["active_seconds"] or 0) * n / total
            )
    return {key: int(round(value)) for key, value in seconds.items()}


def _subject_stats(conn: sqlite3.Connection) -> list[dict]:
    subjects = conn.execute(
        "SELECT id, name, short, color FROM subject ORDER BY sort, id"
    ).fetchall()
    answered = {
        row["subject_id"]: row
        for row in conn.execute(
            """SELECT q.subject_id, COUNT(*) AS n,
                      SUM(CASE WHEN a.correct = 1 THEN 1 ELSE 0 END) AS ok
               FROM answer a
               JOIN attempt t ON t.id = a.attempt_id
               JOIN question q ON q.id = a.question_id
               WHERE a.correct IS NOT NULL
               GROUP BY q.subject_id"""
        )
    }
    reading = {
        row["subject_id"]: row["seconds"]
        for row in conn.execute(
            """SELECT p.subject_id, COALESCE(SUM(st.seconds), 0) AS seconds
               FROM study_time st JOIN page p ON p.id = st.ref
               WHERE st.source = 'page' AND p.subject_id IS NOT NULL
               GROUP BY p.subject_id"""
        )
    }
    attempt_seconds = _attempt_seconds_by_subject(conn)

    out = []
    for subject in subjects:
        sid = subject["id"]
        row = answered.get(sid)
        total = row["n"] if row else 0
        correct = (row["ok"] or 0) if row else 0
        out.append({
            "id": sid,
            "name": subject["name"],
            "short": subject["short"],
            "color": subject["color"],
            "answered": total,
            "correct": correct,
            "accuracy": _accuracy(total, correct),
            "seconds": attempt_seconds.get(sid, 0) + reading.get(sid, 0),
        })
    return out


def _weak_codes(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT q.outline_code AS code, COALESCE(n.title, q.outline_code) AS title,
                  COUNT(*) AS wrong
           FROM answer a
           JOIN question q ON q.id = a.question_id
           LEFT JOIN outline_node n ON n.code = q.outline_code
           WHERE a.correct = 0
           GROUP BY q.outline_code
           ORDER BY wrong DESC, code ASC
           LIMIT 5"""
    ).fetchall()
    return [{"code": row["code"], "title": row["title"], "wrong": row["wrong"]} for row in rows]


def _dynamic(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    today = date.today()
    target = row["target_date"]
    days_to_exam = None
    if target:
        try:
            days_to_exam = (date.fromisoformat(target) - today).days
        except ValueError:
            days_to_exam = None

    answered_row = conn.execute(
        """SELECT COUNT(*) AS n,
                  SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) AS ok
           FROM answer WHERE correct IS NOT NULL"""
    ).fetchone()
    answered = answered_row["n"] or 0
    correct = answered_row["ok"] or 0

    recent = _daily_series(conn)
    today_row = recent[-1]
    streak = _streak(conn)
    xp_pages = conn.execute(
        "SELECT COALESCE(SUM(xp), 0) AS n FROM page_progress"
    ).fetchone()["n"]
    completed_pages = conn.execute(
        "SELECT COUNT(*) AS n FROM page_progress"
    ).fetchone()["n"]
    due_reviews = conn.execute(
        "SELECT COUNT(*) AS n FROM review WHERE due_date <= ?",
        (today.isoformat(),),
    ).fetchone()["n"]

    return {
        "days_to_exam": days_to_exam,
        "today_minutes": round(today_row["seconds"] / 60),
        "streak": streak,
        "xp": xp_pages + correct * 2,
        "completed_pages": completed_pages,
        "answered": answered,
        "correct": correct,
        "accuracy": _accuracy(answered, correct),
        "due_reviews": due_reviews,
        "subjects": _subject_stats(conn),
        "weak_codes": _weak_codes(conn),
        "recent": recent,
    }


def get_profile(conn: sqlite3.Connection) -> dict:
    ensure_profile(conn)
    row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    return {
        "static": {
            "target_exam": row["target_exam"],
            "target_date": row["target_date"],
            "target_score": row["target_score"],
            "daily_minutes": int(row["daily_minutes"]),
            "subjects": _parse_subjects(row["subjects"]),
            "notes": row["notes"] or "",
            "preferred_tone": row["preferred_tone"] or "",
            "preferred_examples": row["preferred_examples"] or "",
        },
        "dynamic": _dynamic(conn, row),
    }


def update_profile(conn: sqlite3.Connection, fields: dict[str, Any]) -> dict:
    """只更新传入的静态字段；返回与 GET 相同的结构。"""
    ensure_profile(conn)
    updates: dict[str, Any] = {}

    if "target_exam" in fields:
        value = fields["target_exam"]
        updates["target_exam"] = None if value is None else str(value)

    if "target_date" in fields:
        value = fields["target_date"]
        if value is None or value == "":
            updates["target_date"] = None
        else:
            _parse_date(value)
            updates["target_date"] = value

    if "target_score" in fields:
        updates["target_score"] = fields["target_score"]

    if "daily_minutes" in fields:
        value = fields["daily_minutes"]
        if value is None or not (1 <= int(value) <= 600):
            raise ProfileError("daily_minutes 必须在 1–600 之间")
        updates["daily_minutes"] = int(value)

    if "subjects" in fields:
        value = fields["subjects"]
        if value is None or not isinstance(value, list):
            raise ProfileError("subjects 必须是科目 id 数组")
        existing = set(_subject_ids(conn))
        unknown = [item for item in value if item not in existing]
        if unknown:
            raise ProfileError("subjects 含不存在的科目：" + ", ".join(unknown))
        seen: set[str] = set()
        unique = []
        for item in value:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        updates["subjects"] = json.dumps(unique, ensure_ascii=False)

    for name, limit in TEXT_LIMITS.items():
        if name in fields:
            value = fields[name]
            text = "" if value is None else str(value)
            if len(text) > limit:
                raise ProfileError(f"{name} 不能超过 {limit} 字")
            updates[name] = text

    if updates:
        updates["updated_at"] = _now_iso()
        assignments = ", ".join(f"{name} = ?" for name in updates)
        conn.execute(
            f"UPDATE profile SET {assignments} WHERE id = 1",
            list(updates.values()),
        )
    return get_profile(conn)

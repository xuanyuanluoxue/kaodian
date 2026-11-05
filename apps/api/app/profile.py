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
DEFAULT_EXAM_TOTAL = 500
MAX_TARGETS = 8
TIERS = ("冲", "稳", "保", "兜底")
PHASES = ("P1", "P2", "P3")
REQUIRED_FIELDS = [
    "target_exam",
    "target_date",
    "target_score",
    "targets",
    "target_major",
    "daily_minutes",
    "subjects",
    "motivation",
]
OPTIONAL_FIELDS = [
    "target_region",
    "exam_total",
    "subject_targets",
    "hard_lines",
    "plan_phase",
    "phase_start",
    "phase_end",
    "phase_daily_minutes",
    "phase_goal",
    "total_hours",
    "backup_school",
    "backup_major",
    "exam_type",
    "current_education",
    "graduation_year",
    "study_window",
    "constraints",
    "strengths",
    "weaknesses",
]
# 空文本落库为 NULL 的字段；notes / ai_summary 保持空字符串，避免前端出现 null。
NULLABLE_TEXT_FIELDS = {
    "target_school",
    "target_major",
    "target_region",
    "backup_school",
    "backup_major",
    "exam_type",
    "current_education",
    "study_window",
    "constraints",
    "strengths",
    "weaknesses",
    "motivation",
    "hard_lines",
    "phase_goal",
}
TEXT_LIMITS = {
    "target_school": 100,
    "target_major": 100,
    "backup_school": 100,
    "backup_major": 100,
    "target_region": 50,
    "exam_type": 100,
    "current_education": 100,
    "study_window": 200,
    "constraints": 1000,
    "strengths": 1000,
    "weaknesses": 1000,
    "motivation": 1000,
    "ai_summary": 2000,
    "notes": 2000,
    "preferred_tone": 200,
    "preferred_examples": 200,
    "hard_lines": 200,
    "phase_goal": 500,
}

QUESTIONS = {
    "target_exam": "你要参加哪场考试？例如「2028 广东专升本」。",
    "targets": "志愿表定了吗？冲 / 稳 / 保 / 兜底各是哪所学校？",
    "target_date": "考试日期大概是哪一天？用 YYYY-MM-DD 回答。",
    "target_score": "目标分数是多少？还没定的话给个大概区间也行。",
    "target_school": "你想冲哪所学校？有保底吗？",
    "target_major": "目标专业是什么？",
    "daily_minutes": "每天大概能挤出多少分钟学习？",
    "subjects": "这次主要准备哪些科目？",
    "motivation": "你为什么要考这个本科？",
    "target_region": "目标院校在哪个地区？",
    "backup_school": "保底院校定了吗？",
    "backup_major": "保底专业是什么？",
    "exam_type": "你走的是哪种升学路径？专升本、自考还是考研？",
    "current_education": "你现在的学历是什么？",
    "graduation_year": "你哪一年毕业？",
    "study_window": "你一般什么时段能学习？比如工作日晚上加周末。",
    "constraints": "目前有哪些时间、工作或家庭上的限制？",
    "strengths": "你觉得自己哪方面比较有优势？",
    "weaknesses": "目前最薄弱的环节是什么？",
    "exam_total": "这场考试满分是多少？",
    "subject_targets": "各科目标分大概是多少？比如高数 85、英语 55。",
    "hard_lines": "有没有硬性分数线要求？比如「三科 105 / 专业综合课 60」。",
    "plan_phase": "现在处在哪个阶段？P1 打基础、P2 强化、P3 冲刺。",
    "phase_start": "当前阶段从哪天开始？用 YYYY-MM-DD 回答。",
    "phase_end": "当前阶段到哪天结束？用 YYYY-MM-DD 回答。",
    "phase_daily_minutes": "这个阶段每天计划学多少分钟？",
    "phase_goal": "这个阶段想达成什么目标？",
    "total_hours": "全程大概计划投入多少小时？",
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


def _parse_targets(value: str | None) -> list[dict]:
    """读库时宽松：坏数据返回空数组，不影响 GET。"""
    try:
        data = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _parse_subject_targets(value: str | None) -> dict[str, int]:
    try:
        data = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, int] = {}
    for key, raw in data.items():
        number = _as_int(raw)
        if number is not None:
            out[str(key)] = number
    return out


def _as_int(value: Any) -> int | None:
    """接受整数、整数值浮点与纯数字字符串；其余返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text and text.lstrip("+-").isdigit():
            return int(text)
    return None


def _parse_date(value: str, name: str = "target_date") -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ProfileError(f"{name} 必须是 YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ProfileError(f"{name} 必须是 YYYY-MM-DD") from exc


def _target_text(value: Any, name: str, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ProfileError(f"{name} 必须是字符串")
    text = value.strip()
    if len(text) > limit:
        raise ProfileError(f"{name} 不能超过 {limit} 字")
    return text


def _target_score(value: Any, name: str, exam_total: int) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileError(f"{name} 必须是 0–{exam_total} 的数字")
    if value < 0 or value > exam_total:
        raise ProfileError(f"{name} 必须在 0–{exam_total} 之间")
    return int(value) if float(value).is_integer() else float(value)


def _target_rank(value: Any, name: str) -> int | None:
    if value is None or value == "":
        return None
    rank = _as_int(value)
    if rank is None or rank < 0 or rank > 1_000_000:
        raise ProfileError(f"{name} 必须是 0–1000000 的整数")
    return rank


def _clean_targets(value: Any, exam_total: int) -> list[dict] | None:
    """校验并规范化志愿表；None 表示清空。"""
    if value is None:
        return None
    if not isinstance(value, list):
        raise ProfileError("targets 必须是数组")
    if len(value) > MAX_TARGETS:
        raise ProfileError(f"targets 最多 {MAX_TARGETS} 条")
    out: list[dict] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ProfileError(f"targets 第 {index} 条必须是对象")
        prefix = f"targets 第 {index} 条"
        tier = item.get("tier")
        if tier not in TIERS:
            raise ProfileError(f"{prefix}的 tier 只能是 冲 / 稳 / 保 / 兜底")
        school = _target_text(item.get("school"), f"{prefix}的 school", 100)
        if not school:
            raise ProfileError(f"{prefix}缺少 school")
        out.append({
            "tier": tier,
            "school": school,
            "major": _target_text(item.get("major"), f"{prefix}的 major", 100),
            "score": _target_score(item.get("score"), f"{prefix}的 score", exam_total),
            "rank": _target_rank(item.get("rank"), f"{prefix}的 rank"),
            "location": _target_text(item.get("location"), f"{prefix}的 location", 100),
            "note": _target_text(item.get("note"), f"{prefix}的 note", 200),
        })
    return out


def _clean_subject_targets(
    conn: sqlite3.Connection, value: Any, exam_total: int
) -> dict[str, int] | None:
    """校验分科目标分；None 表示清空。"""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProfileError("subject_targets 必须是科目到分数的对象")
    existing = set(_subject_ids(conn))
    out: dict[str, int] = {}
    for key, raw in value.items():
        name = str(key)
        if name not in existing:
            raise ProfileError(f"subject_targets 含不存在的科目：{name}")
        if raw is None:
            continue
        score = _as_int(raw)
        if score is None or score < 0 or score > exam_total:
            raise ProfileError(
                f"subject_targets.{name} 必须是 0–{exam_total} 的整数"
            )
        out[name] = score
    return out


def _effective_exam_total(row: sqlite3.Row) -> int:
    value = row["exam_total"] if "exam_total" in row.keys() else None
    try:
        return int(value) if value is not None else DEFAULT_EXAM_TOTAL
    except (TypeError, ValueError):
        return DEFAULT_EXAM_TOTAL


def _phase(row: sqlite3.Row) -> dict | None:
    """当前执行阶段；没有阶段信息返回 None。"""
    name = row["plan_phase"]
    start = row["phase_start"]
    end = row["phase_end"]
    if not name and not start and not end:
        return None
    today = date.today()
    days_left = None
    if end:
        try:
            days_left = (date.fromisoformat(end) - today).days
        except ValueError:
            days_left = None
    progress = None
    if start and end:
        try:
            begin = date.fromisoformat(start)
            finish = date.fromisoformat(end)
        except ValueError:
            begin = finish = None
        if begin is not None and finish is not None:
            total = max((finish - begin).days, 1)
            elapsed = (today - begin).days
            progress = round(min(max(elapsed / total, 0.0), 1.0), 3)
    daily = row["phase_daily_minutes"]
    return {
        "name": name,
        "goal": row["phase_goal"],
        "start": start,
        "end": end,
        "daily_minutes": int(daily) if daily is not None else None,
        "days_left": days_left,
        "progress": progress,
    }


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


def _is_filled(row: sqlite3.Row, name: str) -> bool:
    if name == "subjects":
        return bool(_parse_subjects(row["subjects"]))
    if name == "targets":
        # 兼容 v2：志愿表为空但有首选院校也算已填。
        return bool(_parse_targets(row["targets"])) or bool(row["target_school"])
    if name == "subject_targets":
        return bool(_parse_subject_targets(row["subject_targets"]))
    if name in {"target_score", "graduation_year", "exam_total", "total_hours"}:
        return row[name] is not None
    if name == "phase_daily_minutes":
        return row[name] is not None
    if name == "daily_minutes":
        return row[name] is not None and int(row[name]) > 0
    if name == "target_date":
        return bool(row["target_date"])
    return bool(row[name])


def _completeness(row: sqlite3.Row) -> tuple[float, list[str]]:
    filled = sum(1 for name in REQUIRED_FIELDS if _is_filled(row, name))
    missing = [name for name in REQUIRED_FIELDS if not _is_filled(row, name)]
    return round(filled / len(REQUIRED_FIELDS), 3), missing


def _next_questions(row: sqlite3.Row) -> list[dict]:
    """必填优先、选填在后，最多 6 条中文问题。"""
    questions: list[dict] = []
    for name in REQUIRED_FIELDS:
        if not _is_filled(row, name):
            questions.append({"field": name, "question": QUESTIONS[name]})
            if len(questions) >= 6:
                return questions
    for name in OPTIONAL_FIELDS:
        if not _is_filled(row, name):
            questions.append({"field": name, "question": QUESTIONS[name]})
            if len(questions) >= 6:
                return questions
    return questions


def _static(row: sqlite3.Row) -> dict:
    daily = row["phase_daily_minutes"]
    total_hours = row["total_hours"]
    return {
        "target_exam": row["target_exam"],
        "target_date": row["target_date"],
        "target_score": row["target_score"],
        "targets": _parse_targets(row["targets"]),
        "exam_total": _effective_exam_total(row),
        "target_school": row["target_school"],
        "target_major": row["target_major"],
        "target_region": row["target_region"],
        "backup_school": row["backup_school"],
        "backup_major": row["backup_major"],
        "exam_type": row["exam_type"],
        "current_education": row["current_education"],
        "graduation_year": row["graduation_year"],
        "hard_lines": row["hard_lines"],
        "daily_minutes": int(row["daily_minutes"]),
        "subjects": _parse_subjects(row["subjects"]),
        "subject_targets": _parse_subject_targets(row["subject_targets"]),
        "study_window": row["study_window"],
        "constraints": row["constraints"],
        "strengths": row["strengths"],
        "weaknesses": row["weaknesses"],
        "motivation": row["motivation"],
        "notes": row["notes"] or "",
        "ai_summary": row["ai_summary"] or "",
        "preferred_tone": row["preferred_tone"] or "",
        "preferred_examples": row["preferred_examples"] or "",
        "plan_phase": row["plan_phase"],
        "phase_start": row["phase_start"],
        "phase_end": row["phase_end"],
        "phase_daily_minutes": int(daily) if daily is not None else None,
        "phase_goal": row["phase_goal"],
        "total_hours": int(total_hours) if total_hours is not None else None,
        "updated_by": row["updated_by"] or "user",
    }


def get_profile(conn: sqlite3.Connection) -> dict:
    ensure_profile(conn)
    row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    completeness, missing = _completeness(row)
    return {
        "static": _static(row),
        "dynamic": _dynamic(conn, row),
        "completeness": completeness,
        "missing": missing,
        "next_questions": _next_questions(row),
        "phase": _phase(row),
    }


def update_profile(conn: sqlite3.Connection, fields: dict[str, Any]) -> dict:
    """只更新传入的静态字段；返回与 GET 相同的结构。"""
    ensure_profile(conn)
    row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    data = dict(fields)
    source = "agent" if data.pop("source", "user") == "agent" else "user"
    updates: dict[str, Any] = {}

    if "target_exam" in data:
        value = data["target_exam"]
        updates["target_exam"] = None if value is None else str(value)

    if "target_date" in data:
        value = data["target_date"]
        if value is None or value == "":
            updates["target_date"] = None
        else:
            _parse_date(value)
            updates["target_date"] = value

    if "target_score" in data:
        updates["target_score"] = data["target_score"]

    if "exam_total" in data:
        value = data["exam_total"]
        if value is None or value == "":
            updates["exam_total"] = None
        else:
            exam_total = _as_int(value)
            if exam_total is None or not 1 <= exam_total <= 1000:
                raise ProfileError("exam_total 必须在 1–1000 之间")
            updates["exam_total"] = exam_total
    if "exam_total" in updates:
        exam_total = (
            int(updates["exam_total"])
            if updates["exam_total"] is not None
            else DEFAULT_EXAM_TOTAL
        )
    else:
        exam_total = _effective_exam_total(row)

    if "targets" in data:
        targets = _clean_targets(data["targets"], exam_total)
        updates["targets"] = (
            None if targets is None else json.dumps(targets, ensure_ascii=False)
        )
        if targets:
            first = targets[0]
            backup = next(
                (item for item in reversed(targets) if item["tier"] == "兜底"),
                targets[-1],
            )
            # 显式传值优先：后面的 TEXT_LIMITS 会覆盖这里的同步结果。
            if "target_school" not in data:
                updates["target_school"] = first["school"] or None
            if "backup_school" not in data:
                updates["backup_school"] = backup["school"] or None
            if "backup_major" not in data:
                updates["backup_major"] = backup["major"] or None
        elif targets == []:
            # 清空志愿表时同步清空派生的首选/兜底，避免页面残留旧学校。
            if "target_school" not in data:
                updates["target_school"] = None
            if "backup_school" not in data:
                updates["backup_school"] = None
            if "backup_major" not in data:
                updates["backup_major"] = None

    if "subject_targets" in data:
        subject_targets = _clean_subject_targets(conn, data["subject_targets"], exam_total)
        updates["subject_targets"] = (
            None
            if subject_targets is None
            else json.dumps(subject_targets, ensure_ascii=False, sort_keys=True)
        )

    if "plan_phase" in data:
        value = data["plan_phase"]
        phase = "" if value is None else str(value).strip()
        if phase and phase not in PHASES:
            raise ProfileError("plan_phase 只能是 P1 / P2 / P3")
        updates["plan_phase"] = phase or None

    for name in ("phase_start", "phase_end"):
        if name not in data:
            continue
        value = data[name]
        if value is None or value == "":
            updates[name] = None
        else:
            _parse_date(value, name)
            updates[name] = value

    if "phase_start" in data or "phase_end" in data:
        start = updates.get("phase_start", row["phase_start"])
        end = updates.get("phase_end", row["phase_end"])
        if start and end and end < start:
            raise ProfileError("phase_end 不能早于 phase_start")

    if "phase_daily_minutes" in data:
        value = data["phase_daily_minutes"]
        if value is None or value == "":
            updates["phase_daily_minutes"] = None
        else:
            minutes = _as_int(value)
            if minutes is None or not 1 <= minutes <= 600:
                raise ProfileError("phase_daily_minutes 必须在 1–600 之间")
            updates["phase_daily_minutes"] = minutes

    if "total_hours" in data:
        value = data["total_hours"]
        if value is None or value == "":
            updates["total_hours"] = None
        else:
            hours = _as_int(value)
            if hours is None or not 0 <= hours <= 100000:
                raise ProfileError("total_hours 必须在 0–100000 之间")
            updates["total_hours"] = hours

    if "graduation_year" in data:
        value = data["graduation_year"]
        if value is None or value == "":
            updates["graduation_year"] = None
        else:
            try:
                year = int(value)
            except (TypeError, ValueError) as exc:
                raise ProfileError("graduation_year 必须是 1950–2100 的整数") from exc
            if not 1950 <= year <= 2100:
                raise ProfileError("graduation_year 必须在 1950–2100 之间")
            updates["graduation_year"] = year

    if "daily_minutes" in data:
        value = data["daily_minutes"]
        try:
            minutes = int(value)
        except (TypeError, ValueError) as exc:
            raise ProfileError("daily_minutes 必须在 1–600 之间") from exc
        if not 1 <= minutes <= 600:
            raise ProfileError("daily_minutes 必须在 1–600 之间")
        updates["daily_minutes"] = minutes

    if "subjects" in data:
        value = data["subjects"]
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
        if name not in data:
            continue
        value = data[name]
        text = "" if value is None else str(value)
        if len(text) > limit:
            raise ProfileError(f"{name} 不能超过 {limit} 字")
        if not text and name in NULLABLE_TEXT_FIELDS:
            updates[name] = None
        else:
            updates[name] = text

    if updates:
        updates["updated_by"] = source
        updates["updated_at"] = _now_iso()
        assignments = ", ".join(f"{name} = ?" for name in updates)
        conn.execute(
            f"UPDATE profile SET {assignments} WHERE id = 1",
            list(updates.values()),
        )
    return get_profile(conn)

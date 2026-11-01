from __future__ import annotations

import sqlite3
from datetime import date, timedelta

INTERVALS = {0: 1, 1: 1, 2: 3, 3: 7, 4: 15, 5: 30}


def apply_result(conn: sqlite3.Connection, question_id: str, correct: bool | None) -> dict:
    """按 README 的复习算法更新：连对 3 次 +1，答错 -1（不低于 0）。"""
    row = conn.execute("SELECT * FROM review WHERE question_id = ?", (question_id,)).fetchone()
    mastery = row["mastery"] if row else 0
    streak = row["streak"] if row else 0
    lapses = row["lapses"] if row else 0

    if correct is None:  # 主观题未自评，不动记忆状态
        return {"mastery": mastery, "streak": streak, "interval_days": INTERVALS.get(mastery, 1)}

    if correct:
        streak += 1
        if streak >= 3:
            mastery = min(5, mastery + 1)
            streak = 0
    else:
        mastery = max(0, mastery - 1)
        streak = 0
        lapses += 1

    interval = INTERVALS.get(mastery, 1)
    due = (date.today() + timedelta(days=interval)).isoformat()
    conn.execute(
        """INSERT INTO review(question_id, due_date, interval_days, mastery, streak, lapses, last_result, updated_at)
           VALUES (?,?,?,?,?,?,?,datetime('now','localtime'))
           ON CONFLICT(question_id) DO UPDATE SET
             due_date=excluded.due_date, interval_days=excluded.interval_days,
             mastery=excluded.mastery, streak=excluded.streak, lapses=excluded.lapses,
             last_result=excluded.last_result, updated_at=excluded.updated_at""",
        (question_id, due, interval, mastery, streak, lapses, "correct" if correct else "wrong"),
    )
    return {"mastery": mastery, "streak": streak, "interval_days": interval, "due_date": due}
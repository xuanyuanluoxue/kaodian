from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = Path(__file__).with_name("schema.sql")
DEFAULT_DB = ROOT / "data" / "kaodian.db"


def db_path() -> Path:
    return Path(os.environ.get("KAODIAN_DB", DEFAULT_DB))


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: Path | None = None) -> None:
    path = path or db_path()
    with session(path) as conn:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        seed_subjects(conn)
        seed_questions(conn)


def seed_subjects(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM subject LIMIT 1").fetchone():
        return
    for file in sorted((ROOT / "config" / "subjects").glob("*.json")):
        data = json.loads(file.read_text(encoding="utf-8"))
        exam = data.get("exam", {})
        conn.execute(
            "INSERT INTO subject(id, name, short, exam_score, exam_minutes) VALUES (?,?,?,?,?)",
            (data["id"], data["name"], data["short"], exam.get("score", 100), exam.get("minutes", 120)),
        )
        for index, node in enumerate(data["nodes"]):
            conn.execute(
                """INSERT INTO outline_node
                   (code, subject_id, section, title, requirement, frequency, hours, stage, assessment, kind, sort)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    node["code"], data["id"], node.get("section"), node["title"],
                    node.get("requirement"), node.get("frequency"), node.get("hours"),
                    node.get("stage"), node.get("assessment"), node.get("kind", "point"), index,
                ),
            )


def seed_questions(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM question LIMIT 1").fetchone():
        return
    from .grading import fingerprint

    for file in sorted((ROOT / "config" / "questions").glob("*.json")):
        items = json.loads(file.read_text(encoding="utf-8"))
        for item in items:
            subject_id = item.get("subject_id") or subject_for(item["outline_code"])
            conn.execute(
                """INSERT OR IGNORE INTO question
                   (id, subject_id, outline_code, type, stem, options, answer, explanation,
                    reference_answer, rubric, score, difficulty, source, tags, verified, fingerprint, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item.get("id") or new_id("q"),
                    subject_id,
                    item["outline_code"],
                    item["type"],
                    item["stem"],
                    json.dumps(item.get("options"), ensure_ascii=False) if item.get("options") is not None else None,
                    json.dumps(item.get("answer"), ensure_ascii=False) if item.get("answer") is not None else None,
                    item["explanation"],
                    item.get("reference_answer"),
                    json.dumps(item.get("rubric"), ensure_ascii=False) if item.get("rubric") is not None else None,
                    item.get("score", 1),
                    item.get("difficulty", 2),
                    json.dumps(item.get("source", {"kind": "seed"}), ensure_ascii=False),
                    json.dumps(item.get("tags", []), ensure_ascii=False),
                    1 if item.get("verified") else 0,
                    fingerprint(item["stem"]),
                    now_iso(),
                ),
            )


PREFIX_SUBJECT = {"C": "computer", "D": "computer", "M": "math", "E": "english", "P": "politics"}


def subject_for(code: str) -> str:
    return PREFIX_SUBJECT.get(code[:1], "computer")


def new_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = Path(__file__).with_name("schema.sql")
DEFAULT_DB = ROOT / "user-data" / "kaodian.db"
SCHEMA_VERSION = 2


def db_path() -> Path:
    return Path(os.environ.get("KAODIAN_DB", DEFAULT_DB))


def config_dir() -> Path:
    """内容配置根目录；测试或自定义部署可用 KAODIAN_CONFIG_DIR 覆盖。"""
    return Path(os.environ.get("KAODIAN_CONFIG_DIR", ROOT / "config"))


def now_iso() -> str:
    # 本地朴素时间：单机应用不需要时区，也避免 SQLite date() 把凌晨算到前一天
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
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
    existing = _has_schema(path)
    version = _user_version(path) if existing else 0
    if existing and version < SCHEMA_VERSION:
        _backup(path, version)

    with session(path) as conn:
        if not existing:
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        migrate(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        sync_content(conn)


def _has_schema(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='subject'"
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _user_version(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def _backup(path: Path, version: int) -> None:
    """迁移前用 SQLite backup API 复制（包含 WAL），失败则中止迁移。"""
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    target = path.with_name(f"{path.name}.bak-v{version}-{stamp}")
    src = sqlite3.connect(path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def migrate(conn: sqlite3.Connection) -> None:
    """增量迁移：只加列/索引，不重建表。旧库和新库都会经过这里。"""
    _add_columns(conn, "quiz", {
        "agent_session_id": "TEXT",
    })
    _add_columns(conn, "question", {
        "status": "TEXT NOT NULL DEFAULT 'approved'",
        "reviewed_at": "TEXT",
        "review_note": "TEXT",
        "language": "TEXT",
    })
    _add_columns(conn, "answer", {
        "graded_by": "TEXT",
        "feedback": "TEXT",
    })
    _add_columns(conn, "page", {
        "lesson_key": "TEXT",
        "sort_order": "INTEGER NOT NULL DEFAULT 1000",
    })
    _add_columns(conn, "attempt", {
        "grading_status": "TEXT NOT NULL DEFAULT 'none'",
    })
    _add_columns(conn, "subject", {
        "color": "TEXT",
        "icon": "TEXT",
        "sort": "INTEGER NOT NULL DEFAULT 0",
        "code_language": "TEXT",
    })
    _add_columns(conn, "outline_node", {
        "parent_code": "TEXT",
        "depth": "INTEGER NOT NULL DEFAULT 0",
    })
    conn.execute("CREATE INDEX IF NOT EXISTS idx_page_status ON page(status, subject_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_page_order ON page(subject_id, sort_order, created_at)"
    )


def _add_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def sync_content(conn: sqlite3.Connection) -> None:
    """把 config/ 同步进库：upsert 科目/大纲，题库只补新题，不覆盖用户改动。"""
    base = config_dir()
    subjects = base / "subjects"
    if not subjects.is_dir():
        raise RuntimeError(f"找不到科目配置目录：{subjects}")

    for file in sorted(subjects.glob("*.json")):
        data = json.loads(file.read_text(encoding="utf-8"))
        _validate_subject(file, data)
        exam = data.get("exam", {})
        conn.execute(
            """INSERT INTO subject(id, name, short, exam_score, exam_minutes,
                                   color, icon, sort, code_language)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, short=excluded.short,
                 exam_score=excluded.exam_score, exam_minutes=excluded.exam_minutes,
                 color=excluded.color, icon=excluded.icon, sort=excluded.sort,
                 code_language=excluded.code_language""",
            (
                data["id"], data["name"], data["short"],
                exam.get("score", 100), exam.get("minutes", 120),
                data.get("color"), data.get("icon"), data.get("sort", 0),
                data.get("code_language"),
            ),
        )
        for index, node in enumerate(data["nodes"]):
            conn.execute(
                """INSERT INTO outline_node
                   (code, subject_id, section, title, requirement, frequency, hours,
                    stage, assessment, kind, sort, parent_code)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(code) DO UPDATE SET
                     subject_id=excluded.subject_id, section=excluded.section,
                     title=excluded.title, requirement=excluded.requirement,
                     frequency=excluded.frequency, hours=excluded.hours,
                     stage=excluded.stage, assessment=excluded.assessment,
                     kind=excluded.kind, sort=excluded.sort,
                     parent_code=excluded.parent_code""",
                (
                    node["code"], data["id"], node.get("section"), node["title"],
                    node.get("requirement"), node.get("frequency"), node.get("hours"),
                    node.get("stage"), node.get("assessment"), node.get("kind", "point"),
                    node.get("sort", index), node.get("parent"),
                ),
            )
        _update_depths(conn, data["id"])

    questions = base / "questions"
    if questions.is_dir():
        for file in sorted(questions.glob("*.json")):
            items = json.loads(file.read_text(encoding="utf-8"))
            for index, item in enumerate(items):
                _insert_seed_question(conn, file, index, item)


def _validate_subject(file: Path, data: dict[str, Any]) -> None:
    for key in ("id", "name", "short", "nodes"):
        if not data.get(key):
            raise RuntimeError(f"{file} 缺少字段 {key}")
    codes = [n.get("code") for n in data["nodes"]]
    if any(not c for c in codes):
        raise RuntimeError(f"{file} 有节点缺少 code")
    if len(set(codes)) != len(codes):
        raise RuntimeError(f"{file} 有重复的考点编号")


def _update_depths(conn: sqlite3.Connection, subject_id: str) -> None:
    rows = conn.execute(
        "SELECT code, parent_code FROM outline_node WHERE subject_id = ?", (subject_id,)
    ).fetchall()
    parents = {row["code"]: row["parent_code"] for row in rows}
    cache: dict[str, int] = {}

    def depth(code: str, seen: set[str]) -> int:
        if code in cache:
            return cache[code]
        parent = parents.get(code)
        if not parent or parent not in parents or parent in seen:
            cache[code] = 0
        else:
            cache[code] = depth(parent, seen | {code}) + 1
        return cache[code]

    for code in parents:
        conn.execute(
            "UPDATE outline_node SET depth = ? WHERE code = ?", (depth(code, set()), code)
        )


def _insert_seed_question(
    conn: sqlite3.Connection, file: Path, index: int, item: dict[str, Any]
) -> None:
    from .grading import fingerprint
    from .question_types import get_type

    code = item.get("outline_code")
    if not code:
        raise RuntimeError(f"{file}[{index}] 缺少 outline_code")
    outline = conn.execute(
        "SELECT subject_id FROM outline_node WHERE code = ?", (code,)
    ).fetchone()
    if not outline:
        raise RuntimeError(f"{file}[{index}] 的 outline_code {code} 不在大纲里")
    qtype = item.get("type")
    spec = get_type(qtype)
    if not spec:
        raise RuntimeError(f"{file}[{index}] 的题型 {qtype} 不在 question_types.json 里")

    conn.execute(
        """INSERT OR IGNORE INTO question
           (id, subject_id, outline_code, type, stem, options, answer, explanation,
            reference_answer, rubric, score, difficulty, source, tags, verified,
            language, fingerprint, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            item.get("id") or new_id("q"),
            item.get("subject_id") or outline["subject_id"],
            code,
            qtype,
            item["stem"],
            _json(item.get("options")),
            _json(item.get("answer")),
            item.get("explanation", ""),
            item.get("reference_answer"),
            _json(item.get("rubric")),
            item.get("score", 1),
            item.get("difficulty", 2),
            _json(item.get("source", {"kind": "seed"})),
            _json(item.get("tags", [])),
            1 if item.get("verified") else 0,
            item.get("language") or spec.get("language"),
            fingerprint(item["stem"]),
            now_iso(),
        ),
    )


def _json(value: Any) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def new_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"

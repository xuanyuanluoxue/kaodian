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
SCHEMA_VERSION = 3

_QUESTION_GROUP_DDL = """
CREATE TABLE IF NOT EXISTS question_group (
    id          TEXT PRIMARY KEY,
    subject_id  TEXT REFERENCES subject(id) ON DELETE CASCADE,
    title       TEXT,
    material    TEXT NOT NULL DEFAULT '',
    media       TEXT,
    source_key  TEXT,
    created_at  TEXT NOT NULL
)"""

_QUESTION_OUTLINE_DDL = """
CREATE TABLE IF NOT EXISTS question_outline (
    question_id  TEXT NOT NULL REFERENCES question(id) ON DELETE CASCADE,
    outline_code TEXT NOT NULL REFERENCES outline_node(code) ON DELETE CASCADE,
    weight       REAL NOT NULL DEFAULT 1,
    PRIMARY KEY (question_id, outline_code)
)"""


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
        # migrate 只负责加列/建表；这里补齐索引与后续新增的 DDL（幂等）。
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
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
    """增量迁移：只加列/建表/索引，不重建表。旧库和新库都会经过这里。"""
    conn.execute(_QUESTION_GROUP_DDL)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_question_group_source "
        "ON question_group(subject_id, source_key)"
    )
    _add_columns(conn, "quiz", {
        "agent_session_id": "TEXT",
    })
    _add_columns(conn, "question", {
        "status": "TEXT NOT NULL DEFAULT 'approved'",
        "reviewed_at": "TEXT",
        "review_note": "TEXT",
        "language": "TEXT",
        "group_id": "TEXT REFERENCES question_group(id) ON DELETE SET NULL",
        "group_position": "INTEGER NOT NULL DEFAULT 0",
        "media": "TEXT",
    })
    conn.execute(_QUESTION_OUTLINE_DDL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_question_outline_code "
        "ON question_outline(outline_code, question_id)"
    )
    # v2 的题只有主考点，升级后回填，保证组卷按考点过滤不漏老题。
    conn.execute(
        """INSERT OR IGNORE INTO question_outline(question_id, outline_code)
           SELECT id, outline_code FROM question WHERE outline_code IS NOT NULL"""
    )
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
    """把 config/ 同步进库：upsert 科目/大纲/材料组，题库只补新题，不覆盖用户改动。"""
    from .grading import validate_media

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
            data = json.loads(file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                groups: list[dict[str, Any]] = []
                items = data
            elif isinstance(data, dict):
                groups = data.get("groups") or []
                items = data.get("questions") or []
            else:
                raise RuntimeError(f"{file} 必须是数组或 {{groups, questions}} 对象")

            # 组本身可能没写 subject_id，用挂在其下题目的考点反推。
            inferred: dict[str, str] = {}
            for item in items:
                key = item.get("group_key")
                if key and key not in inferred:
                    subject = _outline_subject(conn, item.get("outline_code"))
                    if subject:
                        inferred[key] = subject

            group_map: dict[str, str] = {}
            for index, group in enumerate(groups):
                if not isinstance(group, dict):
                    raise RuntimeError(f"{file}.groups[{index}] 必须是对象")
                key = (
                    group.get("key")
                    or group.get("source_key")
                    or group.get("title")
                    or f"{file.stem}:{index}"
                )
                subject_id = group.get("subject_id") or inferred.get(key)
                errors = validate_media(group.get("media"), f"groups[{index}].media")
                if errors:
                    raise RuntimeError(f"{file} " + "；".join(errors))
                gid = _upsert_group(conn, subject_id, key, group)
                group_map[key] = gid
                if group.get("key"):
                    group_map[group["key"]] = gid

            for index, item in enumerate(items):
                _insert_seed_question(conn, file, index, item, group_map)


def _outline_subject(conn: sqlite3.Connection, code: Any) -> str | None:
    if not code:
        return None
    row = conn.execute(
        "SELECT subject_id FROM outline_node WHERE code = ?", (code,)
    ).fetchone()
    return row["subject_id"] if row else None


def _upsert_group(
    conn: sqlite3.Connection,
    subject_id: str | None,
    source_key: str,
    data: dict[str, Any],
) -> str:
    """配置里的 group 按 (subject_id, source_key) 幂等 upsert。"""
    if subject_id and not conn.execute(
        "SELECT 1 FROM subject WHERE id = ?", (subject_id,)
    ).fetchone():
        raise RuntimeError(f"question_group {source_key} 的 subject_id {subject_id} 不存在")
    existing = conn.execute(
        "SELECT id FROM question_group WHERE source_key = ? AND subject_id IS ?",
        (source_key, subject_id),
    ).fetchone()
    media = _json(data.get("media")) if data.get("media") else None
    if existing:
        conn.execute(
            "UPDATE question_group SET title = ?, material = ?, media = ? WHERE id = ?",
            (data.get("title"), data.get("material") or "", media, existing["id"]),
        )
        return existing["id"]
    gid = new_id("g")
    conn.execute(
        """INSERT INTO question_group(id, subject_id, title, material, media, source_key, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (gid, subject_id, data.get("title"), data.get("material") or "",
         media, source_key, now_iso()),
    )
    return gid


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
    conn: sqlite3.Connection,
    file: Path,
    index: int,
    item: dict[str, Any],
    group_map: dict[str, str] | None = None,
) -> None:
    from .grading import fingerprint, validate_media
    from .question_types import get_type

    code = item.get("outline_code")
    if not code:
        raise RuntimeError(f"{file}[{index}] 缺少 outline_code")
    outline = conn.execute(
        "SELECT subject_id FROM outline_node WHERE code = ?", (code,)
    ).fetchone()
    if not outline:
        raise RuntimeError(f"{file}[{index}] 的 outline_code {code} 不在大纲里")
    subject_id = item.get("subject_id") or outline["subject_id"]

    extra_codes = item.get("outline_codes") or []
    for extra in extra_codes:
        node = conn.execute(
            "SELECT subject_id FROM outline_node WHERE code = ?", (extra,)
        ).fetchone()
        if not node:
            raise RuntimeError(f"{file}[{index}] 的 outline_codes {extra} 不在大纲里")
        if node["subject_id"] != subject_id:
            raise RuntimeError(
                f"{file}[{index}] 的 outline_codes {extra} 不属于科目 {subject_id}"
            )
    errors = validate_media(item.get("media"), "media")
    if errors:
        raise RuntimeError(f"{file}[{index}] " + "；".join(errors))

    group_id = item.get("group_id")
    group_key = item.get("group_key")
    if group_key:
        if not group_map or group_key not in group_map:
            raise RuntimeError(f"{file}[{index}] 的 group_key {group_key} 没有对应 group")
        group_id = group_map[group_key]
    if group_id and not conn.execute(
        "SELECT 1 FROM question_group WHERE id = ?", (group_id,)
    ).fetchone():
        raise RuntimeError(f"{file}[{index}] 的 group_id {group_id} 不存在")

    qtype = item.get("type")
    spec = get_type(qtype)
    if not spec:
        raise RuntimeError(f"{file}[{index}] 的题型 {qtype} 不在 question_types.json 里")
    fp = fingerprint(item["stem"])

    conn.execute(
        """INSERT OR IGNORE INTO question
           (id, subject_id, outline_code, group_id, group_position, type, stem, options,
            answer, explanation, reference_answer, rubric, score, difficulty, source, tags,
            verified, language, media, fingerprint, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            item.get("id") or new_id("q"),
            subject_id,
            code,
            group_id,
            item.get("group_position", 0),
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
            _json(item.get("media")) if item.get("media") else None,
            fp,
            now_iso(),
        ),
    )
    row = conn.execute("SELECT id FROM question WHERE fingerprint = ?", (fp,)).fetchone()
    if row:
        for linked in [code, *extra_codes]:
            conn.execute(
                "INSERT OR IGNORE INTO question_outline(question_id, outline_code) VALUES (?,?)",
                (row["id"], linked),
            )


def _json(value: Any) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def new_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"

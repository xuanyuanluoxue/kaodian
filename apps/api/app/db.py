from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from . import paths

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 8

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

_CONTENT_PACK_DDL = """
CREATE TABLE IF NOT EXISTS content_pack (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    version    TEXT NOT NULL,
    schema     INTEGER NOT NULL,
    path       TEXT,
    synced_at  TEXT NOT NULL
)"""

_PAGE_DRAFT_DDL = """
CREATE TABLE IF NOT EXISTS page_draft (
    page_id    TEXT PRIMARY KEY REFERENCES page(id) ON DELETE CASCADE,
    body       TEXT,
    blocks     TEXT,
    layout     TEXT,
    theme      TEXT,
    version    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
)"""

_PROFILE_DDL = """
CREATE TABLE IF NOT EXISTS profile (
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    target_exam        TEXT,
    target_date        TEXT,
    target_score       REAL,
    target_school      TEXT,
    target_major       TEXT,
    target_region      TEXT,
    backup_school      TEXT,
    backup_major       TEXT,
    exam_type          TEXT,
    current_education  TEXT,
    graduation_year    INTEGER,
    daily_minutes      INTEGER NOT NULL DEFAULT 30,
    subjects           TEXT NOT NULL DEFAULT '[]',
    study_window       TEXT,
    constraints        TEXT,
    strengths          TEXT,
    weaknesses         TEXT,
    motivation         TEXT,
    notes              TEXT NOT NULL DEFAULT '',
    ai_summary         TEXT,
    preferred_tone     TEXT NOT NULL DEFAULT '',
    preferred_examples TEXT NOT NULL DEFAULT '',
    updated_by         TEXT NOT NULL DEFAULT 'user',
    updated_at         TEXT
)"""

_PROFILE_V8_COLUMNS = {
    "target_school": "TEXT",
    "target_major": "TEXT",
    "target_region": "TEXT",
    "backup_school": "TEXT",
    "backup_major": "TEXT",
    "exam_type": "TEXT",
    "current_education": "TEXT",
    "graduation_year": "INTEGER",
    "study_window": "TEXT",
    "constraints": "TEXT",
    "strengths": "TEXT",
    "weaknesses": "TEXT",
    "motivation": "TEXT",
    "ai_summary": "TEXT",
    "updated_by": "TEXT NOT NULL DEFAULT 'user'",
}


def db_path() -> Path:
    return paths.db_path()


def config_dir() -> Path:
    """框架自身的配置目录（题型注册表等）；内容在 content_dir()。"""
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
        from .profile import ensure_profile

        ensure_profile(conn)


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
    backups = path.parent / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    target = backups / f"{path.name}.bak-v{version}-{stamp}"
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
    conn.execute(_CONTENT_PACK_DDL)
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
    # v4：内容包归属。partial unique index 只约束 pack 内的自然键，
    # 本地运行时创建的页面/题目（pack_id IS NULL）保持自由。
    _add_columns(conn, "subject", {"pack_id": "TEXT", "source_key": "TEXT"})
    _add_columns(conn, "outline_node", {"pack_id": "TEXT"})
    _add_columns(conn, "question", {"pack_id": "TEXT", "source_key": "TEXT"})
    _add_columns(conn, "page", {"pack_id": "TEXT", "source_key": "TEXT"})
    # v5：讲义块页。旧 Markdown 页保持 format='markdown'、blocks 为空。
    _add_columns(conn, "page", {
        "blocks": "TEXT",
        "layout": "TEXT NOT NULL DEFAULT 'article'",
        "theme": "TEXT",
        "format": "TEXT NOT NULL DEFAULT 'markdown'",
    })
    # v6：网页编辑草稿。page.file 记录内容文件相对 content/ 的路径。
    _add_columns(conn, "page", {"file": "TEXT"})
    conn.execute(_PAGE_DRAFT_DDL)
    # v7：学习画像单行表；动态学情不落库。
    conn.execute(_PROFILE_DDL)
    # v8：画像补升学目标、学习条件、自我评估与 AI 摘要；旧库只加列。
    _add_columns(conn, "profile", _PROFILE_V8_COLUMNS)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_subject_pack_source "
        "ON subject(pack_id, source_key) WHERE pack_id IS NOT NULL"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_question_pack_source "
        "ON question(pack_id, source_key) WHERE pack_id IS NOT NULL"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_page_pack_source "
        "ON page(pack_id, source_key) WHERE pack_id IS NOT NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_outline_pack ON outline_node(pack_id)"
    )
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
    """把内容仓库同步进库（自然键 UPSERT，不删除本地内容）。"""
    from .content import sync_content as _sync

    _sync(conn)


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


def new_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"

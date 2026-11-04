"""独立内容包：读取、校验与同步。

契约见 ``docs/dev/content-packs.md``。这里不引入 PyYAML：Markdown frontmatter
只支持契约里列出的简单字段（标量、内联数组、true/false/null）。
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from . import paths
from .grading import fingerprint, validate_media, validate_question

PACK_SCHEMA = 1
KINDS = {"lesson", "outline", "note", "daily"}
STATUSES = {"draft", "published", "archived"}
LESSON_FIELDS = {
    "lesson_key", "title", "summary", "kind", "status", "sort_order", "outline_codes",
}
_MEDIA_RE = re.compile(r"/media/([A-Za-z0-9._-]+)/([^\s)\]\}\"'<>]+)")


class PackError(RuntimeError):
    """内容包结构错误。"""


# ---------------------------------------------------------------- frontmatter

def _scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered in {"null", "none", "~"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    if value[0] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise PackError(f"frontmatter 字符串格式错误：{value}") from exc
    if value[0] == "'" and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [_scalar(part) for part in inner.split(",") if part.strip()]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """返回 ``(meta, body)``；没有 frontmatter 时 meta 为空。"""
    text = text.lstrip("\ufeff")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        raise PackError("frontmatter 没有结束的 --- 行")

    meta: dict[str, Any] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if line[:1].isspace() or line.lstrip().startswith("- "):
            raise PackError("frontmatter 不支持嵌套或块状列表")
        if ":" not in line:
            raise PackError(f"frontmatter 行缺少冒号：{line.strip()}")
        key, raw = line.split(":", 1)
        key = key.strip()
        if not key:
            raise PackError("frontmatter 键不能为空")
        if key in meta:
            raise PackError(f"frontmatter 键重复：{key}")
        meta[key] = _scalar(raw)

    body = "".join(lines[end + 1:])
    return meta, body.lstrip("\r\n")


# ---------------------------------------------------------------- load

def _read_json(file: Path) -> Any:
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackError(f"无法读取 {file}：{exc}") from exc


def _question_items(file: Path, data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("questions"), list):
        if data.get("groups"):
            raise PackError(f"{file} 不支持 groups；内容包只收题目数组")
        return data["questions"]
    raise PackError(f"{file} 必须是题目数组或 {{questions: [...]}} 对象")


def load_pack(entry: dict[str, Any]) -> dict[str, Any]:
    """读取一个 pack 为结构化 dict（不做业务校验）。"""
    root = Path(entry["path"])
    pack_file = root / "pack.json"
    if not pack_file.is_file():
        raise PackError(f"找不到 {pack_file}")
    meta = _read_json(pack_file)
    if not isinstance(meta, dict):
        raise PackError(f"{pack_file} 必须是对象")

    outline_file = root / "outline.json"
    nodes = _read_json(outline_file) if outline_file.is_file() else []
    if not isinstance(nodes, list):
        raise PackError(f"{outline_file} 必须是数组")

    lessons: list[dict[str, Any]] = []
    for file in sorted((root / "lessons").glob("*.md")):
        meta_lesson, body = parse_frontmatter(file.read_text(encoding="utf-8"))
        lessons.append({
            **meta_lesson,
            "body": body,
            "file": file,
            "source_key": meta_lesson.get("lesson_key") or file.stem,
        })

    questions: list[dict[str, Any]] = []
    for file in sorted((root / "questions").glob("*.json")):
        for item in _question_items(file, _read_json(file)):
            if not isinstance(item, dict):
                raise PackError(f"{file} 里有非对象题目")
            questions.append({**item, "file": file})

    assets_dir = root / "assets"
    assets = sorted(
        str(path.relative_to(assets_dir)).replace("\\", "/")
        for path in assets_dir.rglob("*")
        if path.is_file()
    ) if assets_dir.is_dir() else []

    return {
        "id": meta.get("id") or entry["id"],
        "name": meta.get("name"),
        "version": meta.get("version"),
        "schema": meta.get("schema"),
        "path": root,
        "subject": meta.get("subject") or {},
        "nodes": nodes,
        "lessons": lessons,
        "questions": questions,
        "assets": assets,
    }


def load_all() -> list[dict[str, Any]]:
    return [load_pack(entry) for entry in paths.packs()]


# ---------------------------------------------------------------- validate

def _outline_map(pack: dict[str, Any], errors: list[str]) -> dict[str, str]:
    subject_id = (pack.get("subject") or {}).get("id")
    mapping: dict[str, str] = {}
    for index, node in enumerate(pack.get("nodes") or []):
        if not isinstance(node, dict):
            errors.append(f"outline[{index}] 必须是对象")
            continue
        code = node.get("code")
        if not code or not isinstance(code, str):
            errors.append(f"outline[{index}] 缺少 code")
            continue
        if code in mapping:
            errors.append(f"考点编号重复：{code}")
            continue
        if not node.get("title"):
            errors.append(f"outline {code} 缺少 title")
        mapping[code] = subject_id or ""
    if not mapping:
        errors.append("outline.json 至少要有一个考点")
    return mapping


def _check_media(
    pack: dict[str, Any], text: Any, label: str, errors: list[str],
) -> None:
    if not isinstance(text, str):
        return
    assets = set(pack.get("assets") or [])
    for match in _MEDIA_RE.finditer(text):
        pack_id, rel = match.group(1), match.group(2)
        rel = rel.split("?", 1)[0].split("#", 1)[0].rstrip(".,;:!?，。；：！？")
        if pack_id != pack["id"]:
            errors.append(f"{label} 引用了其它内容包：/media/{pack_id}/{rel}")
        elif rel not in assets:
            errors.append(f"{label} 引用的素材不存在：/media/{pack_id}/{rel}")


def validate_pack(pack: dict[str, Any]) -> list[str]:
    """校验单个 pack，返回错误列表（空表示通过）。"""
    errors: list[str] = []
    for key in ("id", "name", "version"):
        if not pack.get(key):
            errors.append(f"pack.json 缺少 {key}")
    if pack.get("schema") != PACK_SCHEMA:
        errors.append(f"schema 必须是 {PACK_SCHEMA}，当前是 {pack.get('schema')!r}")

    subject = pack.get("subject") or {}
    if not isinstance(subject, dict):
        errors.append("subject 必须是对象")
        subject = {}
    for key in ("id", "name", "short"):
        if not subject.get(key):
            errors.append(f"subject 缺少 {key}")
    exam = subject.get("exam") or {}
    if not isinstance(exam, dict):
        errors.append("subject.exam 必须是对象")

    outline = _outline_map(pack, errors)

    lesson_keys: set[str] = set()
    for index, lesson in enumerate(pack.get("lessons") or []):
        label = f"lesson[{index}]"
        file = lesson.get("file")
        if file:
            label = str(file.relative_to(pack["path"])) if file.is_relative_to(pack["path"]) else str(file)
        unknown = set(lesson) - LESSON_FIELDS - {"body", "file", "source_key"}
        if unknown:
            errors.append(f"{label} 含不支持的 frontmatter 字段：{', '.join(sorted(unknown))}")
        for key in ("title", "kind", "status", "sort_order", "outline_codes"):
            if lesson.get(key) in (None, "", []):
                errors.append(f"{label} 缺少 {key}")
        kind = lesson.get("kind")
        if kind and kind not in KINDS:
            errors.append(f"{label} 的 kind 必须是 {'/'.join(sorted(KINDS))}")
        status = lesson.get("status")
        if status and status not in STATUSES:
            errors.append(f"{label} 的 status 必须是 {'/'.join(sorted(STATUSES))}")
        order = lesson.get("sort_order")
        if order is not None and (not isinstance(order, int) or isinstance(order, bool)):
            errors.append(f"{label} 的 sort_order 必须是整数")
        codes = lesson.get("outline_codes")
        if codes is not None and not isinstance(codes, list):
            errors.append(f"{label} 的 outline_codes 必须是数组")
            codes = []
        for code in codes or []:
            if code not in outline:
                errors.append(f"{label} 的 outline_codes {code} 不在大纲里")
        lesson_key = lesson.get("lesson_key")
        if kind in {"lesson", "note", "daily"} and not lesson_key:
            errors.append(f"{label} 缺少 lesson_key")
        if lesson_key:
            if not isinstance(lesson_key, str):
                errors.append(f"{label} 的 lesson_key 必须是字符串")
            elif lesson_key in lesson_keys:
                errors.append(f"lesson_key 重复：{lesson_key}")
            else:
                lesson_keys.add(lesson_key)
        _check_media(pack, lesson.get("body"), f"{label} 正文", errors)

    question_ids: set[str] = set()
    for index, item in enumerate(pack.get("questions") or []):
        label = f"question[{index}]"
        if item.get("id"):
            label = f"question {item['id']}"
            if item["id"] in question_ids:
                errors.append(f"题目 id 重复：{item['id']}")
            question_ids.add(item["id"])
        else:
            errors.append(f"{label} 缺少 id")
        errors.extend(f"{label}: {err}" for err in validate_question(item, outline))
        for code in item.get("outline_codes") or []:
            if code not in outline:
                errors.append(f"{label} 的 outline_codes {code} 不在大纲里")
        _check_media(pack, item.get("stem"), f"{label} 题干", errors)
        _check_media(pack, item.get("explanation"), f"{label} 解析", errors)
        for media_index, media in enumerate(item.get("media") or []):
            if isinstance(media, dict) and isinstance(media.get("url"), str):
                _check_media(
                    pack, media["url"], f"{label} media[{media_index}]", errors,
                )
        errors.extend(f"{label}: {err}" for err in validate_media(
            item.get("media"), f"{label}.media",
        ))

    return errors


def validate_all() -> list[dict[str, Any]]:
    """校验全部 pack，供 CLI 使用。"""
    results: list[dict[str, Any]] = []
    for entry in paths.packs():
        try:
            pack = load_pack(entry)
        except PackError as exc:
            results.append({"id": entry["id"], "ok": False, "errors": [str(exc)]})
            continue
        errors = validate_pack(pack)
        results.append({
            "id": pack.get("id") or entry["id"],
            "ok": not errors,
            "errors": errors,
            "nodes": len(pack["nodes"]),
            "lessons": len(pack["lessons"]),
            "questions": len(pack["questions"]),
        })
    return results


# ---------------------------------------------------------------- sync

def _json(value: Any) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _sync_subject(conn: sqlite3.Connection, pack: dict[str, Any]) -> str:
    subject = pack["subject"]
    exam = subject.get("exam") or {}
    conn.execute(
        """INSERT INTO subject(id, name, short, exam_score, exam_minutes,
                               color, icon, sort, code_language, pack_id, source_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name, short=excluded.short,
             exam_score=excluded.exam_score, exam_minutes=excluded.exam_minutes,
             color=excluded.color, icon=excluded.icon, sort=excluded.sort,
             code_language=excluded.code_language,
             pack_id=excluded.pack_id, source_key=excluded.source_key""",
        (
            subject["id"], subject["name"], subject["short"],
            exam.get("score", 100), exam.get("minutes", 120),
            subject.get("color"), subject.get("icon"), subject.get("sort", 0),
            subject.get("code_language"), pack["id"], subject["id"],
        ),
    )
    return subject["id"]


def _sync_outline(
    conn: sqlite3.Connection, pack: dict[str, Any], subject_id: str,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for index, node in enumerate(pack["nodes"]):
        mapping[node["code"]] = subject_id
        conn.execute(
            """INSERT INTO outline_node
               (code, subject_id, section, title, requirement, frequency, hours,
                stage, assessment, kind, sort, parent_code, pack_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(code) DO UPDATE SET
                 subject_id=excluded.subject_id, section=excluded.section,
                 title=excluded.title, requirement=excluded.requirement,
                 frequency=excluded.frequency, hours=excluded.hours,
                 stage=excluded.stage, assessment=excluded.assessment,
                 kind=excluded.kind, sort=excluded.sort,
                 parent_code=excluded.parent_code, pack_id=excluded.pack_id""",
            (
                node["code"], subject_id, node.get("section"), node["title"],
                node.get("requirement"), node.get("frequency"), node.get("hours"),
                node.get("stage"), node.get("assessment"),
                node.get("kind", "point"), node.get("sort", index),
                node.get("parent"), pack["id"],
            ),
        )
    _update_depths(conn, subject_id)
    return mapping


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
            "UPDATE outline_node SET depth = ? WHERE code = ?",
            (depth(code, set()), code),
        )


def _sync_question(
    conn: sqlite3.Connection, pack: dict[str, Any], subject_id: str,
    item: dict[str, Any], outline: dict[str, str],
) -> None:
    source_key = str(item.get("id") or fingerprint(item["stem"]))
    fp = fingerprint(item["stem"])
    existing = None
    if item.get("id"):
        existing = conn.execute(
            "SELECT id FROM question WHERE id = ?", (item["id"],)
        ).fetchone()
    if not existing:
        existing = conn.execute(
            "SELECT id FROM question WHERE fingerprint = ?", (fp,)
        ).fetchone()

    values = (
        item.get("subject_id") or outline[item["outline_code"]],
        item["outline_code"], item.get("group_position", 0), item["type"],
        item["stem"], _json(item.get("options")), _json(item.get("answer")),
        item.get("explanation", ""), item.get("reference_answer"),
        _json(item.get("rubric")), item.get("score", 1),
        item.get("difficulty", 2), _json(item.get("source", {"kind": "seed"})),
        _json(item.get("tags", [])), 1 if item.get("verified") else 0,
        item.get("language"), _json(item.get("media")) if item.get("media") else None,
        fp, pack["id"], source_key,
    )
    if existing:
        conn.execute(
            """UPDATE question SET
                 subject_id=?, outline_code=?, group_position=?, type=?, stem=?,
                 options=?, answer=?, explanation=?, reference_answer=?, rubric=?,
                 score=?, difficulty=?, source=?, tags=?, verified=?, language=?,
                 media=?, fingerprint=?, pack_id=?, source_key=?
               WHERE id=?""",
            (*values, existing["id"]),
        )
        question_id = existing["id"]
    else:
        question_id = item["id"] or f"q_{fp}"
        conn.execute(
            """INSERT INTO question
               (id, subject_id, outline_code, group_position, type, stem, options,
                answer, explanation, reference_answer, rubric, score, difficulty,
                source, tags, verified, language, media, fingerprint, pack_id,
                source_key, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                question_id, *values,
                item.get("status", "approved"), _now(),
            ),
        )

    linked = [item["outline_code"], *(item.get("outline_codes") or [])]
    for code in dict.fromkeys(linked):
        conn.execute(
            "INSERT OR IGNORE INTO question_outline(question_id, outline_code) VALUES (?,?)",
            (question_id, code),
        )


def _sync_page(
    conn: sqlite3.Connection, pack: dict[str, Any], subject_id: str,
    lesson: dict[str, Any],
) -> None:
    kind = lesson.get("kind") or "lesson"
    lesson_key = lesson.get("lesson_key")
    if kind == "outline":
        source_key = lesson_key or "outline"
        existing = conn.execute(
            """SELECT id FROM page
               WHERE subject_id = ? AND kind = 'outline'
               ORDER BY CASE WHEN pack_id = ? THEN 0 WHEN pack_id IS NULL THEN 1 ELSE 2 END
               LIMIT 1""",
            (subject_id, pack["id"]),
        ).fetchone()
    else:
        source_key = str(lesson_key or lesson["file"].stem)
        existing = conn.execute(
            """SELECT id FROM page
               WHERE subject_id = ? AND lesson_key = ?
               ORDER BY CASE WHEN pack_id = ? THEN 0 WHEN pack_id IS NULL THEN 1 ELSE 2 END
               LIMIT 1""",
            (subject_id, source_key, pack["id"]),
        ).fetchone()

    values = (
        subject_id, lesson.get("title"), lesson.get("summary"),
        lesson["body"], source_key, _json(lesson.get("outline_codes") or []),
        kind, lesson.get("status") or "published",
        lesson.get("sort_order", 1000), pack["id"], source_key,
    )
    if existing:
        conn.execute(
            """UPDATE page SET subject_id=?, title=?, summary=?, body=?,
                 lesson_key=?, outline_codes=?, kind=?, status=?, sort_order=?,
                 pack_id=?, source_key=?, updated_at=?
               WHERE id=?""",
            (*values, _now(), existing["id"]),
        )
        return

    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", source_key).strip("-") or "page"
    page_id = f"p_{pack['id']}_{slug}"
    now = _now()
    conn.execute(
        """INSERT INTO page(id, subject_id, title, summary, body, lesson_key,
                            outline_codes, kind, status, sort_order, created_at,
                            updated_at, pack_id, source_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            page_id, subject_id, lesson.get("title"), lesson.get("summary"),
            lesson["body"], source_key, _json(lesson.get("outline_codes") or []),
            kind, lesson.get("status") or "published",
            lesson.get("sort_order", 1000), now, now, pack["id"], source_key,
        ),
    )


def _sync_pack(conn: sqlite3.Connection, pack: dict[str, Any]) -> dict[str, int]:
    conn.execute(
        """INSERT INTO content_pack(id, name, version, schema, path, synced_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name, version=excluded.version, schema=excluded.schema,
             path=excluded.path, synced_at=excluded.synced_at""",
        (
            pack["id"], pack.get("name") or pack["id"], str(pack.get("version") or ""),
            pack.get("schema") or PACK_SCHEMA, str(pack["path"]), _now(),
        ),
    )
    subject_id = _sync_subject(conn, pack)
    outline = _sync_outline(conn, pack, subject_id)
    for item in pack["questions"]:
        _sync_question(conn, pack, subject_id, item, outline)
    for lesson in pack["lessons"]:
        _sync_page(conn, pack, subject_id, lesson)
    return {
        "nodes": len(pack["nodes"]),
        "lessons": len(pack["lessons"]),
        "questions": len(pack["questions"]),
    }


def sync_content(conn: sqlite3.Connection) -> list[dict[str, int]]:
    """把内容仓库同步进库；只 upsert，不删除本地内容。"""
    totals: list[dict[str, int]] = []
    for entry in paths.packs():
        pack = load_pack(entry)
        errors = validate_pack(pack)
        if errors:
            raise PackError(f"内容包 {entry['id']} 校验失败：\n" + "\n".join(errors))
        totals.append({"id": pack["id"], **_sync_pack(conn, pack)})
    return totals
